from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path
from time import perf_counter

from microsandbox import Sandbox, Volume, is_installed

from sandbox_service.models import SessionLimits
from sandbox_service.policies import build_network
from sandbox_service.runtime.base import ExecResult, SandboxRuntime
from sandbox_service.runtime.local import build_shell_command, guest_cwd
from sandbox_service.workspace import ensure_workspace


class MicrosandboxRuntime:
    name = "microsandbox"

    def __init__(self, *, scratch_root: Path, guest_workspace_path: str) -> None:
        self._scratch_root = scratch_root
        self._guest_workspace_path = guest_workspace_path
        self._sandboxes: dict[str, Sandbox] = {}

    def is_available(self) -> bool:
        return is_installed()

    async def create_session(
        self,
        *,
        session_id: str,
        sandbox_name: str,
        image: str,
        root_path: str,
        limits: SessionLimits,
    ) -> None:
        if not self.is_available():
            raise RuntimeError("microsandbox runtime is not installed")

        ensure_workspace(self._scratch_root, session_id)
        existing = self._sandboxes.get(sandbox_name)
        if existing is not None:
            return

        handles = {handle.name: handle for handle in await Sandbox.list()}
        if sandbox_name in handles:
            sandbox = await handles[sandbox_name].connect()
            self._sandboxes[sandbox_name] = sandbox
            return

        network_mode = limits.network
        allowed_hosts = limits.allowed_hosts
        sandbox = await Sandbox.create(
            {
                "name": sandbox_name,
                "image": image,
                "memoryMib": limits.memory_mb,
                "cpus": limits.cpu,
                "workdir": self._guest_workspace_path,
                "replace": True,
                "env": {"PYTHONUNBUFFERED": "1"},
                "volumes": {
                    self._guest_workspace_path: Volume.bind(root_path),
                },
                "network": build_network(network_mode, allowed_hosts),
            }
        )
        self._sandboxes[sandbox_name] = sandbox

    async def stop_session(self, *, sandbox_name: str) -> None:
        sandbox = self._sandboxes.get(sandbox_name)
        if sandbox is None:
            handles = {handle.name: handle for handle in await Sandbox.list()}
            handle = handles.get(sandbox_name)
            if handle is not None:
                await handle.stop()
            return
        await sandbox.stop_and_wait()

    async def delete_session(self, *, sandbox_name: str) -> None:
        sandbox = self._sandboxes.pop(sandbox_name, None)
        if sandbox is not None:
            await self._stop_and_remove(sandbox, sandbox_name)
            return

        handles = {handle.name: handle for handle in await Sandbox.list()}
        handle = handles.get(sandbox_name)
        if handle is None:
            return
        try:
            await handle.stop()
        except Exception:
            await handle.kill()
        await handle.remove()

    async def list_sandboxes(self) -> list[str]:
        if not self.is_available():
            return []
        return [handle.name for handle in await Sandbox.list()]

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
        await self.create_session(
            session_id=sandbox_name,
            sandbox_name=sandbox_name,
            image=image,
            root_path=root_path,
            limits=limits,
        )
        sandbox = self._sandboxes[sandbox_name]
        shell_command = build_shell_command(
            guest_workspace_path=self._guest_workspace_path,
            command=command,
            cwd=cwd,
            env=env,
        )
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        exit_code: int | None = None
        handle = None
        started = perf_counter()
        try:
            handle = await sandbox.shell_stream(shell_command)
            async with asyncio.timeout(float(timeout_seconds)):
                async for event in handle:
                    if event.event_type == "stdout" and event.data:
                        stdout_chunks.append(event.data)
                    elif event.event_type == "stderr" and event.data:
                        stderr_chunks.append(event.data)
                    elif event.event_type == "exited":
                        exit_code = event.code if event.code is not None else 1
        except TimeoutError:
            if handle is not None:
                with suppress(Exception):
                    await handle.kill()
            return ExecResult(exit_code=124, stdout=b"", stderr=b"", timed_out=True)
        except Exception as exc:
            return ExecResult(
                exit_code=1,
                stdout=b"".join(stdout_chunks),
                stderr=str(exc).encode("utf-8"),
            )
        finally:
            _ = started

        stdout = _truncate(b"".join(stdout_chunks), max_output_bytes)
        stderr = _truncate(b"".join(stderr_chunks), max_output_bytes)
        return ExecResult(
            exit_code=exit_code if exit_code is not None else 1,
            stdout=stdout,
            stderr=stderr,
        )

    async def _stop_and_remove(self, sandbox: Sandbox, sandbox_name: str) -> None:
        try:
            await sandbox.stop_and_wait()
        except Exception:
            await sandbox.kill()
        await Sandbox.remove(sandbox_name)


def _truncate(data: bytes, max_bytes: int) -> bytes:
    if len(data) <= max_bytes:
        return data
    return data[:max_bytes]
