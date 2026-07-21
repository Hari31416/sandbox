from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sandbox_service.db import get_connection
from sandbox_service.models import SessionLimits

from .models import SessionRecord, _iso, _parse_iso, _utcnow


def _row_to_session(row) -> SessionRecord:
    return SessionRecord(
        id=row["id"],
        workspace_id=row["workspace_id"],
        run_id=row["run_id"],
        image=row["image"],
        status=row["status"],
        backend=row["backend"],
        root_path=row["root_path"],
        sandbox_name=row["sandbox_name"],
        limits=SessionLimits.model_validate_json(row["limits_json"]),
        metadata=json.loads(row["metadata_json"]),
        created_at=_parse_iso(row["created_at"]),
        expires_at=_parse_iso(row["expires_at"]),
        last_heartbeat_at=_parse_iso(row["last_heartbeat_at"]),
        stopped_at=_parse_iso(row["stopped_at"]),
    )


class SessionRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def create(
        self,
        *,
        workspace_id: str,
        run_id: str | None,
        image: str,
        backend: str,
        root_path: str,
        sandbox_name: str | None,
        limits: SessionLimits,
        metadata: dict,
        ttl_seconds: int,
    ) -> SessionRecord:
        session_id = f"sess_{uuid.uuid4().hex}"
        now = _utcnow()
        expires_at = now + timedelta(seconds=ttl_seconds)
        with get_connection(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO sandbox_sessions (
                    id, workspace_id, run_id, image, status, backend, root_path,
                    sandbox_name, limits_json, metadata_json, created_at, expires_at,
                    last_heartbeat_at, stopped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    workspace_id,
                    run_id,
                    image,
                    "active",
                    backend,
                    root_path,
                    sandbox_name,
                    limits.model_dump_json(),
                    json.dumps(metadata),
                    _iso(now),
                    _iso(expires_at),
                    _iso(now),
                    None,
                ),
            )
        return self.get(session_id)

    def get(self, session_id: str) -> SessionRecord:
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM sandbox_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return _row_to_session(row)

    def list_sessions(
        self,
        *,
        workspace_id: str | None = None,
        run_id: str | None = None,
        status: str | None = None,
    ) -> list[SessionRecord]:
        clauses: list[str] = []
        params: list[str] = []
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            params.append(workspace_id)
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM sandbox_sessions {where} ORDER BY created_at DESC",
                params,
            ).fetchall()
        return [_row_to_session(row) for row in rows]

    def count_active(self) -> int:
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM sandbox_sessions WHERE status = 'active'"
            ).fetchone()
        return int(row["n"] if row is not None else 0)

    def heartbeat(self, session_id: str, extend_seconds: int) -> SessionRecord:
        record = self.get(session_id)
        now = _utcnow()
        proposed = now + timedelta(seconds=max(1, extend_seconds))
        # Never extend past the policy/session lifetime from create.
        max_expires = record.created_at + timedelta(
            seconds=max(1, int(record.limits.timeout_seconds))
        )
        expires_at = min(proposed, max_expires)
        if expires_at < now:
            expires_at = now
        with get_connection(self._db_path) as conn:
            conn.execute(
                """
                UPDATE sandbox_sessions
                SET last_heartbeat_at = ?, expires_at = ?
                WHERE id = ?
                """,
                (_iso(now), _iso(expires_at), session_id),
            )
        return self.get(session_id)

    def update_status(self, session_id: str, status: str) -> SessionRecord:
        stopped_at = _iso(_utcnow()) if status in {"stopped", "expired"} else None
        with get_connection(self._db_path) as conn:
            conn.execute(
                """
                UPDATE sandbox_sessions
                SET status = ?, stopped_at = COALESCE(?, stopped_at)
                WHERE id = ?
                """,
                (status, stopped_at, session_id),
            )
        return self.get(session_id)

    def delete(self, session_id: str) -> None:
        with get_connection(self._db_path) as conn:
            conn.execute("DELETE FROM execs WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM files WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM artifacts WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sandbox_sessions WHERE id = ?", (session_id,))

    def update_runtime_paths(
        self, session_id: str, *, root_path: str, sandbox_name: str | None
    ) -> SessionRecord:
        with get_connection(self._db_path) as conn:
            conn.execute(
                """
                UPDATE sandbox_sessions
                SET root_path = ?, sandbox_name = ?
                WHERE id = ?
                """,
                (root_path, sandbox_name, session_id),
            )
        return self.get(session_id)

    def list_expired(self, now: datetime | None = None) -> list[SessionRecord]:
        now = now or _utcnow()
        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM sandbox_sessions
                WHERE status = 'active' AND expires_at < ?
                """,
                (_iso(now),),
            ).fetchall()
        return [_row_to_session(row) for row in rows]
