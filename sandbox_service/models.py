from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


SessionStatus = Literal["creating", "active", "stopping", "stopped", "expired"]
ExecStatus = Literal["running", "completed", "failed", "timed_out"]
BackendName = Literal["local", "microsandbox"]


class SessionLimits(BaseModel):
    cpu: int = 1
    memory_mb: int = 1024
    disk_mb: int = 2048
    timeout_seconds: int = 300
    network: Literal["disabled", "public", "allowlist"] = "disabled"
    allowed_hosts: list[str] = Field(default_factory=list)


class CreateSessionRequest(BaseModel):
    workspace_id: str
    run_id: str | None = None
    image: str | None = None
    backend: BackendName | None = None
    limits: SessionLimits = Field(default_factory=SessionLimits)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    id: str
    workspace_id: str
    run_id: str | None
    image: str
    status: SessionStatus
    backend: BackendName
    root_path: str
    limits: SessionLimits
    metadata: dict[str, Any]
    created_at: datetime
    expires_at: datetime
    last_heartbeat_at: datetime | None
    stopped_at: datetime | None


class HeartbeatRequest(BaseModel):
    extend_seconds: int | None = None


class ExecRequest(BaseModel):
    command: str
    cwd: str = "/workspace"
    timeout_seconds: int | None = None
    env: dict[str, str] = Field(default_factory=dict)


class ExecResponse(BaseModel):
    id: str
    session_id: str
    command: str
    cwd: str
    status: ExecStatus
    exit_code: int | None
    started_at: datetime
    finished_at: datetime | None
    timeout_seconds: int


class WriteFileRequest(BaseModel):
    path: str
    content_base64: str
    mode: str = "0644"


class FileInfo(BaseModel):
    path: str
    size_bytes: int
    sha256: str
    updated_at: datetime


class FileListEntry(BaseModel):
    path: str
    is_dir: bool
    size_bytes: int
    updated_at: datetime


class SyncArtifactsRequest(BaseModel):
    paths: list[str]
    destination_prefix: str
    include_globs: list[str] = Field(default_factory=lambda: ["**/*"])
    exclude_globs: list[str] = Field(
        default_factory=lambda: [".venv/**", "__pycache__/**"]
    )


class ArtifactInfo(BaseModel):
    id: str
    session_id: str
    source_path: str
    artifact_uri: str
    size_bytes: int
    sha256: str
    created_at: datetime


class BackendCapabilities(BaseModel):
    name: BackendName
    available: bool
    supports_network_policy: bool
    supports_streaming: bool


class BackendsResponse(BaseModel):
    backends: list[BackendCapabilities]
    default_backend: BackendName


class GcResponse(BaseModel):
    sessions_removed: int
    exec_logs_removed: int


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    backend: BackendName
    sqlite_ok: bool
