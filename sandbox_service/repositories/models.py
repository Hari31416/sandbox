from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

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


@dataclass(frozen=True)
class SnapshotRecord:
    id: str
    workspace_id: str
    source_session_id: str | None
    name: str
    msb_name: str
    digest: str
    image_ref: str
    size_bytes: int
    include_workspace: bool
    workspace_bytes: int
    workspace_archive_path: str | None
    metadata: dict
    created_at: datetime
