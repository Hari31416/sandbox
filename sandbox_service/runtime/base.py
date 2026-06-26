from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sandbox_service.models import SessionLimits


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: bytes
    stderr: bytes
    timed_out: bool = False


@dataclass(frozen=True)
class SnapshotInfo:
    msb_name: str
    digest: str
    image_ref: str
    size_bytes: int


class SandboxRuntime(Protocol):
    @property
    def name(self) -> str: ...

    def is_available(self) -> bool: ...

    def supports_snapshots(self) -> bool: ...

    async def create_session(
        self,
        *,
        session_id: str,
        sandbox_name: str,
        image: str,
        root_path: str,
        limits: SessionLimits,
        snapshot: str | None = None,
    ) -> None: ...

    async def stop_session(self, *, sandbox_name: str) -> None: ...

    async def delete_session(self, *, sandbox_name: str) -> None: ...

    async def list_sandboxes(self) -> list[str]: ...

    async def exec_command(
        self,
        *,
        sandbox_name: str,
        image: str,
        root_path: str,
        command: str,
        cwd: str,
        timeout_seconds: int,
        env: dict[str, str],
        limits: SessionLimits,
        max_output_bytes: int,
        snapshot: str | None = None,
    ) -> ExecResult: ...

    async def create_snapshot(
        self,
        *,
        sandbox_name: str,
        name: str,
        labels: dict[str, str],
    ) -> SnapshotInfo: ...

    async def delete_snapshot(self, *, msb_name: str) -> None: ...

    async def list_snapshots(self) -> list[SnapshotInfo]: ...
