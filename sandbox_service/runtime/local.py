from __future__ import annotations

import asyncio
import hashlib
import os
import shlex
from pathlib import Path

from sandbox_service.models import SessionLimits
from sandbox_service.path_guard import normalize_sandbox_path
from sandbox_service.runtime.base import ExecResult, SandboxRuntime
from sandbox_service.workspace import ensure_workspace


def build_sandbox_name(session_id: str) -> str:
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
    return f"sbox-{digest}"


class LocalRuntime:
    name = "local"

    def __init__(self, *, scratch_root: Path, guest_workspace_path: str) -> None:
        self._scratch_root = scratch_root
        self._guest_workspace_path = guest_workspace_path

    def is_available(self) -> bool:
        return True

    async def create_session(
        self,
        *,
        session_id: str,
        sandbox_name: str,
        image: str,
        root_path: str,
        limits: SessionLimits,
    ) -> None:
        ensure_workspace(self._scratch_root, session_id)

    async def stop_session(self, *, sandbox_name: str) -> None:
        return None

    async def delete_session(self, *, sandbox_name: str) -> None:
        return None

    async def list_sandboxes(self) -> list[str]:
        return []

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
    ) -> ExecResult:
        workspace = Path(root_path)
        normalized_cwd = normalize_sandbox_path(cwd)
        workdir = workspace if not normalized_cwd else (workspace / normalized_cwd).resolve()
        env_vars = {**os.environ, **env, "HOME": str(workdir)}
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(workdir),
            env=env_vars,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=float(timeout_seconds)
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            return ExecResult(exit_code=124, stdout=b"", stderr=b"", timed_out=True)

        if len(stdout) > max_output_bytes:
            stdout = stdout[:max_output_bytes]
        if len(stderr) > max_output_bytes:
            stderr = stderr[:max_output_bytes]
        return ExecResult(
            exit_code=process.returncode or 0,
            stdout=stdout,
            stderr=stderr,
        )


def guest_cwd(guest_workspace_path: str, cwd: str) -> str:
    normalized = normalize_sandbox_path(cwd)
    base = guest_workspace_path.rstrip("/")
    if not normalized:
        return base
    return f"{base}/{normalized.lstrip('/')}"


def build_shell_command(
    *,
    guest_workspace_path: str,
    command: str,
    cwd: str,
    env: dict[str, str],
) -> str:
    target_cwd = guest_cwd(guest_workspace_path, cwd)
    env_assignments = " ".join(
        shlex.quote(f"{key}={value}")
        for key, value in sorted(env.items())
        if key
    )
    env_prefix = f"env {env_assignments} " if env_assignments else ""
    return (
        f"cd {shlex.quote(target_cwd)} && "
        f"{env_prefix}{command}"
    )
