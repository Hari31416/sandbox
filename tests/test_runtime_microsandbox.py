from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from sandbox_service.models import SessionLimits
from sandbox_service.runtime import microsandbox
from sandbox_service.runtime.microsandbox import MicrosandboxRuntime


class TimeoutExecHandle:
    def __init__(self) -> None:
        self.killed = False

    async def kill(self) -> None:
        self.killed = True

    def __aiter__(self) -> TimeoutExecHandle:
        return self

    async def __anext__(self) -> object:
        raise TimeoutError


@dataclass
class FakeSandbox:
    exec_handle: TimeoutExecHandle
    stop_calls: int = 0

    async def shell_stream(self, *args: object, **kwargs: object) -> TimeoutExecHandle:
        return self.exec_handle

    async def stop_and_wait(self) -> None:
        self.stop_calls += 1

    async def kill(self) -> None:
        return None


@pytest.mark.anyio
async def test_exec_timeout_removes_stale_sandbox(monkeypatch, tmp_path) -> None:
    exec_handle = TimeoutExecHandle()
    sandbox = FakeSandbox(exec_handle=exec_handle)
    remove = AsyncMock()
    monkeypatch.setattr(microsandbox.Sandbox, "remove", remove)

    runtime = MicrosandboxRuntime(
        scratch_root=tmp_path,
        guest_workspace_path="/workspace",
    )
    runtime.is_available = lambda: True  # type: ignore[method-assign]
    runtime._sandboxes["sbox"] = sandbox

    result = await runtime.exec_command(
        sandbox_name="sbox",
        image="python:3.12",
        root_path=str(tmp_path / "workspace"),
        command="python3 script.py",
        cwd="/workspace",
        timeout_seconds=1,
        env={},
        limits=SessionLimits(),
        max_output_bytes=1024,
    )

    assert result.exit_code == 124
    assert result.timed_out is True
    assert exec_handle.killed is True
    assert sandbox.stop_calls == 1
    remove.assert_awaited_once_with("sbox")
    assert "sbox" not in runtime._sandboxes
    assert "sbox" not in runtime._active_execs
