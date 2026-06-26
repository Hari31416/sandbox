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


class SandboxRuntime(Protocol):
    @property
    def name(self) -> str: ...

    def is_available(self) -> bool: ...

    async def create_session(
        self,
        *,
        session_id: str,
        sandbox_name: str,
        image: str,
        root_path: str,
        limits: SessionLimits,
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
    ) -> ExecResult: ...
