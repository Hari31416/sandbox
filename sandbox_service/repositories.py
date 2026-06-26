from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sandbox_service.db import get_connection
from sandbox_service.models import SessionLimits


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


@dataclass(frozen=True)
class SessionRecord:
    id: str
    workspace_id: str
    run_id: str | None
    image: str
    status: str
    backend: str
    root_path: str
    sandbox_name: str | None
    limits: SessionLimits
    metadata: dict
    created_at: datetime
    expires_at: datetime
    last_heartbeat_at: datetime | None
    stopped_at: datetime | None


@dataclass(frozen=True)
class ExecRecord:
    id: str
    session_id: str
    command: str
    cwd: str
    status: str
    exit_code: int | None
    stdout_path: str | None
    stderr_path: str | None
    started_at: datetime
    finished_at: datetime | None
    timeout_seconds: int


@dataclass(frozen=True)
class ArtifactRecord:
    id: str
    session_id: str
    source_path: str
    artifact_uri: str
    size_bytes: int
    sha256: str
    created_at: datetime


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

    def heartbeat(self, session_id: str, extend_seconds: int) -> SessionRecord:
        now = _utcnow()
        expires_at = now + timedelta(seconds=extend_seconds)
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


class ExecRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def create(
        self,
        *,
        session_id: str,
        command: str,
        cwd: str,
        timeout_seconds: int,
        stdout_path: str,
        stderr_path: str,
    ) -> ExecRecord:
        exec_id = f"exec_{uuid.uuid4().hex}"
        now = _utcnow()
        with get_connection(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO execs (
                    id, session_id, command, cwd, status, exit_code,
                    stdout_path, stderr_path, started_at, finished_at, timeout_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exec_id,
                    session_id,
                    command,
                    cwd,
                    "running",
                    None,
                    stdout_path,
                    stderr_path,
                    _iso(now),
                    None,
                    timeout_seconds,
                ),
            )
        return self.get(exec_id)

    def get(self, exec_id: str) -> ExecRecord:
        with get_connection(self._db_path) as conn:
            row = conn.execute("SELECT * FROM execs WHERE id = ?", (exec_id,)).fetchone()
        if row is None:
            raise KeyError(exec_id)
        return _row_to_exec(row)

    def finish(
        self,
        exec_id: str,
        *,
        status: str,
        exit_code: int | None,
    ) -> ExecRecord:
        with get_connection(self._db_path) as conn:
            conn.execute(
                """
                UPDATE execs
                SET status = ?, exit_code = ?, finished_at = ?
                WHERE id = ?
                """,
                (status, exit_code, _iso(_utcnow()), exec_id),
            )
        return self.get(exec_id)

    def list_for_session(self, session_id: str) -> list[ExecRecord]:
        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM execs WHERE session_id = ? ORDER BY started_at DESC",
                (session_id,),
            ).fetchall()
        return [_row_to_exec(row) for row in rows]

    def delete_older_than(self, cutoff: datetime) -> int:
        with get_connection(self._db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM execs WHERE finished_at IS NOT NULL AND finished_at < ?",
                (_iso(cutoff),),
            )
        return cursor.rowcount


class FileMetadataRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def upsert(
        self,
        *,
        session_id: str,
        path: str,
        size_bytes: int,
        sha256: str,
    ) -> None:
        file_id = hashlib.sha256(f"{session_id}:{path}".encode()).hexdigest()[:32]
        with get_connection(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO files (id, session_id, path, size_bytes, sha256, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, path) DO UPDATE SET
                    size_bytes = excluded.size_bytes,
                    sha256 = excluded.sha256,
                    updated_at = excluded.updated_at
                """,
                (file_id, session_id, path, size_bytes, sha256, _iso(_utcnow())),
            )

    def delete(self, session_id: str, path: str) -> None:
        with get_connection(self._db_path) as conn:
            conn.execute(
                "DELETE FROM files WHERE session_id = ? AND path = ?",
                (session_id, path),
            )


class ArtifactRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def create(
        self,
        *,
        session_id: str,
        source_path: str,
        artifact_uri: str,
        size_bytes: int,
        sha256: str,
    ) -> ArtifactRecord:
        artifact_id = f"art_{uuid.uuid4().hex}"
        now = _utcnow()
        with get_connection(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO artifacts (
                    id, session_id, source_path, artifact_uri, size_bytes, sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    session_id,
                    source_path,
                    artifact_uri,
                    size_bytes,
                    sha256,
                    _iso(now),
                ),
            )
        return self.get(artifact_id)

    def get(self, artifact_id: str) -> ArtifactRecord:
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM artifacts WHERE id = ?", (artifact_id,)
            ).fetchone()
        if row is None:
            raise KeyError(artifact_id)
        return _row_to_artifact(row)

    def list_for_session(self, session_id: str) -> list[ArtifactRecord]:
        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE session_id = ? ORDER BY created_at DESC",
                (session_id,),
            ).fetchall()
        return [_row_to_artifact(row) for row in rows]


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


def _row_to_exec(row) -> ExecRecord:
    return ExecRecord(
        id=row["id"],
        session_id=row["session_id"],
        command=row["command"],
        cwd=row["cwd"],
        status=row["status"],
        exit_code=row["exit_code"],
        stdout_path=row["stdout_path"],
        stderr_path=row["stderr_path"],
        started_at=_parse_iso(row["started_at"]),
        finished_at=_parse_iso(row["finished_at"]),
        timeout_seconds=row["timeout_seconds"],
    )


def _row_to_artifact(row) -> ArtifactRecord:
    return ArtifactRecord(
        id=row["id"],
        session_id=row["session_id"],
        source_path=row["source_path"],
        artifact_uri=row["artifact_uri"],
        size_bytes=row["size_bytes"],
        sha256=row["sha256"],
        created_at=_parse_iso(row["created_at"]),
    )
