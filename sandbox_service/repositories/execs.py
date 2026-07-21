from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from sandbox_service.db import get_connection

from .models import ExecRecord, _iso, _parse_iso, _utcnow


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
            row = conn.execute(
                "SELECT * FROM execs WHERE id = ?", (exec_id,)
            ).fetchone()
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
