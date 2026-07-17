from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from pathlib import Path
from typing import Any

from microsandbox import Image, Sandbox, Snapshot, Volume, is_installed
from microsandbox.events import ExitedEvent, StderrEvent, StdoutEvent
from microsandbox.types import Stdin

from sandbox_service.models import SessionLimits
from sandbox_service.policies import build_network
from sandbox_service.runtime.base import ExecResult, SnapshotInfo
from sandbox_service.runtime.exec_env import GUEST_DEFAULT_EXEC_ENV, merge_exec_env
from sandbox_service.runtime.local import build_shell_command

logger = logging.getLogger(__name__)

_STOP_TIMEOUT_SECONDS = 10.0
_KILL_TIMEOUT_SECONDS = 10.0
_EXEC_KILL_TIMEOUT_SECONDS = 5.0


class MicrosandboxRuntime:
    name = "microsandbox"

    def __init__(self, *, scratch_root: Path, guest_workspace_path: str) -> None:
        self._scratch_root = scratch_root
        self._guest_workspace_path = guest_workspace_path
        self._sandboxes: dict[str, Sandbox] = {}
        self._active_execs: dict[str, Any] = {}

    def is_available(self) -> bool:
        return is_installed()

    def supports_snapshots(self) -> bool:
        return self.is_available()

    def _build_create_config(
        self,
        *,
        sandbox_name: str,
        image: str,
        root_path: str,
        limits: SessionLimits,
        snapshot: str | None,
    ) -> dict:
        network_mode = limits.network
        allowed_hosts = limits.allowed_hosts
        config: dict = {
            "name": sandbox_name,
            "memoryMib": limits.memory_mb,
            "cpus": limits.cpu,
            "workdir": self._guest_workspace_path,
            "replace": True,
            "env": dict(GUEST_DEFAULT_EXEC_ENV),
            "volumes": {
                self._guest_workspace_path: Volume.bind(root_path),
            },
            "network": build_network(network_mode, allowed_hosts),
            # Hard VM lifetime matching usage-policy sandbox_timeout_seconds.
            "maxDurationSecs": max(1, int(limits.timeout_seconds)),
        }
        if snapshot is not None:
            config["snapshot"] = snapshot
        else:
            # Writable OCI overlay size — enforces sandbox_disk_mb for rootfs writes.
            config["image"] = Image.oci(image, upper_size_mib=max(512, int(limits.disk_mb)))
        return config

    async def _attach_existing_sandbox(self, sandbox_name: str) -> Sandbox:
        handle = await Sandbox.get(sandbox_name)
        status = str(handle.status).lower()
        if status == "running":
            return await handle.connect()
        if status in {"stopped", "paused", "crashed"}:
            return await Sandbox.start(sandbox_name, detached=True)
        return await handle.connect()

    async def _get_sandbox_handle(self, sandbox_name: str):
        try:
            return await Sandbox.get(sandbox_name)
        except Exception:
            handles = {handle.name: handle for handle in await Sandbox.list()}
            handle = handles.get(sandbox_name)
            if handle is None:
                raise RuntimeError(f"sandbox not found: {sandbox_name}") from None
            return handle

    async def _kill_active_exec(self, sandbox_name: str) -> None:
        handle = self._active_execs.pop(sandbox_name, None)
        if handle is None:
            return
        with suppress(Exception):
            await asyncio.wait_for(handle.kill(), timeout=_EXEC_KILL_TIMEOUT_SECONDS)

    async def _force_stop_connected(self, sandbox: Sandbox, sandbox_name: str) -> None:
        try:
            await asyncio.wait_for(sandbox.stop_and_wait(), timeout=_STOP_TIMEOUT_SECONDS)
            return
        except Exception:
            logger.warning(
                "graceful stop timed out or failed for sandbox %s; forcing kill",
                sandbox_name,
                exc_info=True,
            )
        try:
            await asyncio.wait_for(sandbox.kill(), timeout=_KILL_TIMEOUT_SECONDS)
        except Exception:
            logger.exception("forced kill failed for sandbox %s", sandbox_name)

    async def _ensure_sandbox_stopped(self, sandbox_name: str) -> None:
        await self._kill_active_exec(sandbox_name)
        connected = self._sandboxes.pop(sandbox_name, None)
        if connected is not None:
            await self._force_stop_connected(connected, sandbox_name)
            return

        try:
            handle = await self._get_sandbox_handle(sandbox_name)
        except RuntimeError:
            return
        status = str(handle.status).lower()
        if status not in {"running", "paused"}:
            return
        try:
            await asyncio.wait_for(handle.stop(), timeout=_STOP_TIMEOUT_SECONDS)
            await asyncio.wait_for(handle.wait_until_stopped(), timeout=_STOP_TIMEOUT_SECONDS)
        except Exception:
            logger.warning(
                "catalog stop failed for sandbox %s; forcing kill",
                sandbox_name,
                exc_info=True,
            )
            with suppress(Exception):
                await asyncio.wait_for(handle.kill(), timeout=_KILL_TIMEOUT_SECONDS)

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
        if not self.is_available():
            raise RuntimeError("microsandbox runtime is not installed")

        # Bind-mount source must exist before VM create; use root_path (not
        # session_id) so exec re-attach does not create a spurious scratch dir.
        Path(root_path).mkdir(parents=True, exist_ok=True)
        existing = self._sandboxes.get(sandbox_name)
        if existing is not None:
            return

        handles = {handle.name: handle for handle in await Sandbox.list()}
        if sandbox_name in handles:
            sandbox = await self._attach_existing_sandbox(sandbox_name)
            self._sandboxes[sandbox_name] = sandbox
            return

        config = self._build_create_config(
            sandbox_name=sandbox_name,
            image=image,
            root_path=root_path,
            limits=limits,
            snapshot=snapshot,
        )
        name = config.pop("name")
        sandbox = await Sandbox.create(name, **config)
        self._sandboxes[sandbox_name] = sandbox

    async def stop_session(self, *, sandbox_name: str) -> None:
        await self._ensure_sandbox_stopped(sandbox_name)

    async def delete_session(self, *, sandbox_name: str) -> None:
        await self._kill_active_exec(sandbox_name)
        sandbox = self._sandboxes.pop(sandbox_name, None)
        if sandbox is not None:
            await self._stop_and_remove(sandbox, sandbox_name)
            return

        handles = {handle.name: handle for handle in await Sandbox.list()}
        handle = handles.get(sandbox_name)
        if handle is None:
            return
        try:
            await asyncio.wait_for(handle.stop(), timeout=_STOP_TIMEOUT_SECONDS)
        except Exception:
            with suppress(Exception):
                await asyncio.wait_for(handle.kill(), timeout=_KILL_TIMEOUT_SECONDS)
        with suppress(Exception):
            await handle.remove()

    async def list_sandboxes(self) -> list[str]:
        if not self.is_available():
            return []
        try:
            return [handle.name for handle in await Sandbox.list()]
        except Exception:
            return []

    async def create_snapshot(
        self,
        *,
        sandbox_name: str,
        name: str,
        labels: dict[str, str],
    ) -> SnapshotInfo:
        if not self.is_available():
            raise RuntimeError("microsandbox runtime is not installed")

        await self._ensure_sandbox_stopped(sandbox_name)

        snap = await Snapshot.create(
            source_sandbox=sandbox_name,
            name=name,
            labels=labels or None,
        )
        return SnapshotInfo(
            msb_name=name,
            digest=snap.digest,
            image_ref=snap.image_ref,
            size_bytes=snap.size_bytes,
        )

    async def delete_snapshot(self, *, msb_name: str) -> None:
        if not self.is_available():
            raise RuntimeError("microsandbox runtime is not installed")
        await Snapshot.remove(msb_name)

    async def list_snapshots(self) -> list[SnapshotInfo]:
        if not self.is_available():
            return []
        handles = await Snapshot.list()
        results: list[SnapshotInfo] = []
        for handle in handles:
            name = handle.name or handle.digest
            results.append(
                SnapshotInfo(
                    msb_name=name,
                    digest=handle.digest,
                    image_ref=handle.image_ref,
                    size_bytes=handle.size_bytes or 0,
                )
            )
        return results

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
        await self.create_session(
            session_id=sandbox_name,
            sandbox_name=sandbox_name,
            image=image,
            root_path=root_path,
            limits=limits,
            snapshot=snapshot,
        )
        sandbox = self._sandboxes[sandbox_name]
        exec_env = merge_exec_env(env)
        shell_command = build_shell_command(
            guest_workspace_path=self._guest_workspace_path,
            command=command,
            cwd=cwd,
            env=exec_env,
        )
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        exit_code: int | None = None
        handle = None
        try:
            # Pass timeout to the SDK as well as asyncio.timeout: native
            # iterators can ignore CancelledError, leaving guest/CPU stuck.
            # Stdin.null() prevents interactive/GUI probes from blocking forever.
            handle = await sandbox.shell_stream(
                shell_command,
                env=exec_env,
                timeout=float(timeout_seconds),
                stdin=Stdin.null(),
            )
            self._active_execs[sandbox_name] = handle
            async with asyncio.timeout(float(timeout_seconds) + 5.0):
                async for event in handle:
                    kind = _exec_event_kind(event)
                    data = getattr(event, "data", None)
                    if kind == "stdout" and data:
                        stdout_chunks.append(data)
                    elif kind == "stderr" and data:
                        stderr_chunks.append(data)
                    elif kind == "exited":
                        code = getattr(event, "code", None)
                        exit_code = code if code is not None else 1
                        # Exited is terminal; do not keep iterating the native
                        # stream (can busy-spin / hold msb at 100% CPU).
                        break
        except TimeoutError:
            if handle is not None:
                with suppress(Exception):
                    await asyncio.wait_for(
                        handle.kill(),
                        timeout=_EXEC_KILL_TIMEOUT_SECONDS,
                    )
            # Drop cached handle so the next exec re-attaches cleanly after kill.
            self._sandboxes.pop(sandbox_name, None)
            timeout_note = b"command timed out\n"
            return ExecResult(
                exit_code=124,
                stdout=_truncate(b"".join(stdout_chunks), max_output_bytes),
                stderr=_truncate(timeout_note + b"".join(stderr_chunks), max_output_bytes),
                timed_out=True,
            )
        except Exception as exc:
            return ExecResult(
                exit_code=1,
                stdout=_truncate(b"".join(stdout_chunks), max_output_bytes),
                stderr=_truncate(str(exc).encode("utf-8"), max_output_bytes),
            )
        finally:
            if self._active_execs.get(sandbox_name) is handle:
                self._active_execs.pop(sandbox_name, None)

        stdout = _truncate(b"".join(stdout_chunks), max_output_bytes)
        stderr = _truncate(b"".join(stderr_chunks), max_output_bytes)
        return ExecResult(
            exit_code=exit_code if exit_code is not None else 1,
            stdout=stdout,
            stderr=stderr,
        )

    async def _stop_and_remove(self, sandbox: Sandbox, sandbox_name: str) -> None:
        await self._force_stop_connected(sandbox, sandbox_name)
        with suppress(Exception):
            await Sandbox.remove(sandbox_name)


def _exec_event_kind(event: object) -> str | None:
    """Normalize SDK exec events.

    microsandbox 0.5.10 yields builtin ``ExecEvent`` objects where
    ``isinstance(..., StdoutEvent)`` is False; prefer ``event_type``.
    """
    event_type = getattr(event, "event_type", None)
    if isinstance(event_type, str) and event_type:
        return event_type
    if isinstance(event, StdoutEvent):
        return "stdout"
    if isinstance(event, StderrEvent):
        return "stderr"
    if isinstance(event, ExitedEvent):
        return "exited"
    return None


def _truncate(data: bytes, max_bytes: int) -> bytes:
    if len(data) <= max_bytes:
        return data
    return data[:max_bytes]
