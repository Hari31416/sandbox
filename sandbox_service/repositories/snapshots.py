from __future__ import annotations

import json
import uuid
from pathlib import Path

from sandbox_service.db import get_connection

from .models import SnapshotRecord, _iso, _parse_iso, _utcnow


def _row_to_snapshot(row) -> SnapshotRecord:
    keys = row.keys()
    return SnapshotRecord(
        id=row["id"],
        workspace_id=row["workspace_id"],
        source_session_id=row["source_session_id"],
        name=row["name"],
        msb_name=row["msb_name"],
        digest=row["digest"],
        image_ref=row["image_ref"],
        size_bytes=row["size_bytes"],
        include_workspace=(
            bool(row["include_workspace"]) if "include_workspace" in keys else False
        ),
        workspace_bytes=row["workspace_bytes"] if "workspace_bytes" in keys else 0,
        workspace_archive_path=(
            row["workspace_archive_path"] if "workspace_archive_path" in keys else None
        ),
        metadata=json.loads(row["metadata_json"]),
        created_at=_parse_iso(row["created_at"]),
    )


class SnapshotRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def create(
        self,
        *,
        workspace_id: str,
        source_session_id: str | None,
        name: str,
        msb_name: str,
        digest: str,
        image_ref: str,
        size_bytes: int,
        include_workspace: bool = False,
        workspace_bytes: int = 0,
        workspace_archive_path: str | None = None,
        metadata: dict,
    ) -> SnapshotRecord:
        snapshot_id = f"snap_{uuid.uuid4().hex}"
        now = _utcnow()
        with get_connection(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO snapshots (
                    id, workspace_id, source_session_id, name, msb_name,
                    digest, image_ref, size_bytes, include_workspace,
                    workspace_bytes, workspace_archive_path, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    workspace_id,
                    source_session_id,
                    name,
                    msb_name,
                    digest,
                    image_ref,
                    size_bytes,
                    int(include_workspace),
                    workspace_bytes,
                    workspace_archive_path,
                    json.dumps(metadata),
                    _iso(now),
                ),
            )
        return self.get(snapshot_id)

    def update_workspace_bundle(
        self,
        snapshot_id: str,
        *,
        workspace_bytes: int,
        workspace_archive_path: str,
    ) -> SnapshotRecord:
        with get_connection(self._db_path) as conn:
            conn.execute(
                """
                UPDATE snapshots
                SET workspace_bytes = ?, workspace_archive_path = ?
                WHERE id = ?
                """,
                (workspace_bytes, workspace_archive_path, snapshot_id),
            )
        return self.get(snapshot_id)

    def get(self, snapshot_id: str) -> SnapshotRecord:
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)
            ).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        return _row_to_snapshot(row)

    def list_snapshots(
        self,
        *,
        workspace_id: str | None = None,
    ) -> list[SnapshotRecord]:
        if workspace_id is None:
            with get_connection(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT * FROM snapshots ORDER BY created_at DESC"
                ).fetchall()
        else:
            with get_connection(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT * FROM snapshots WHERE workspace_id = ? ORDER BY created_at DESC",
                    (workspace_id,),
                ).fetchall()
        return [_row_to_snapshot(row) for row in rows]

    def delete(self, snapshot_id: str) -> SnapshotRecord:
        record = self.get(snapshot_id)
        with get_connection(self._db_path) as conn:
            conn.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
        return record
