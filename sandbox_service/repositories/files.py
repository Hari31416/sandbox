from __future__ import annotations

import hashlib
from pathlib import Path

from sandbox_service.db import get_connection

from .models import _iso, _utcnow


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
