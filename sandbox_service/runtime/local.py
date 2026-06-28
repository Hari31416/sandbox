from __future__ import annotations

import asyncio
import hashlib
import os
import shlex
from pathlib import Path

from sandbox_service.models import SessionLimits
from sandbox_service.path_guard import (
    normalize_sandbox_path,
    rewrite_guest_workspace_command,
)
from sandbox_service.runtime.base import ExecResult, SandboxRuntime, SnapshotInfo
from sandbox_service.workspace import ensure_workspace


def _isolated_exec_env(workdir: Path, extra: dict[str, str]) -> dict[str, str]:
    """Build a minimal subprocess environment for local sandbox exec."""
    tmpdir = workdir / ".tmp"
    tmpdir.mkdir(parents=True, exist_ok=True)

    if "PATH" in extra:
        sandbox_path = extra["PATH"]
    else:
        host_path = os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
        filtered = [
            part
            for part in host_path.split(":")
            if part and "/opt/homebrew" not in part and "/homebrew/" not in part.lower()
        ]
        sandbox_path = ":".join(filtered) if filtered else "/usr/bin:/bin"

    venv_bin = workdir / ".venv" / "bin"
    if venv_bin.is_dir() and "PATH" not in extra:
        sandbox_path = f"{venv_bin}:{sandbox_path}"

    return {
        "HOME": str(workdir),
        "PWD": str(workdir),
        "TMPDIR": str(tmpdir),
        "PATH": sandbox_path,
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        **extra,
    }


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

    def supports_snapshots(self) -> bool:
        return False

    async def create_session(
        self,
        *,
        session_id: str,
        sandbox_name: str,
        image: str,
        root_path: str,
        limits: SessionLimits,
        snapshot: str | None = None,
    ) -> None:
        if snapshot is not None:
            raise NotImplementedError("local backend does not support snapshots")
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
        snapshot: str | None = None,
    ) -> ExecResult:
        if snapshot is not None:
            raise NotImplementedError("local backend does not support snapshots")
        workspace = Path(root_path)
        normalized_cwd = normalize_sandbox_path(cwd)
        workdir = workspace if not normalized_cwd else (workspace / normalized_cwd).resolve()
        rewritten_command = rewrite_guest_workspace_command(command)
        env_vars = _isolated_exec_env(workdir, env)
        process = await asyncio.create_subprocess_shell(
            rewritten_command,
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

    async def create_snapshot(
        self,
        *,
        sandbox_name: str,
        name: str,
        labels: dict[str, str],
    ) -> SnapshotInfo:
        raise NotImplementedError("local backend does not support snapshots")

    async def delete_snapshot(self, *, msb_name: str) -> None:
        raise NotImplementedError("local backend does not support snapshots")

    async def list_snapshots(self) -> list[SnapshotInfo]:
        return []


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
