from __future__ import annotations

import uuid
from pathlib import Path

from sandbox_service.db import get_connection

from .models import ArtifactRecord, _iso, _parse_iso, _utcnow


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
