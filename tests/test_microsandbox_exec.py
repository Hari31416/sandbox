from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sandbox_service.models import SessionLimits
from sandbox_service.runtime.base import ExecResult
from sandbox_service.runtime.microsandbox import MicrosandboxRuntime
from microsandbox.types import Stdin


class _FakeHandle:
    def __init__(self, events: list[Any]) -> None:
        self._events = list(events)
        self.kill = AsyncMock()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._events:
            # Simulate a stuck native stream that never raises StopAsyncIteration.
            # Without break-on-exited, exec_command would hang here.
            await __import__("asyncio").sleep(3600)
            raise StopAsyncIteration
        return self._events.pop(0)


@pytest.mark.asyncio
async def test_exec_breaks_on_exited_without_waiting_for_stream_end(
    tmp_path, monkeypatch
) -> None:
    runtime = MicrosandboxRuntime(
        scratch_root=tmp_path,
        guest_workspace_path="/workspace",
    )
    root = tmp_path / "ws"
    root.mkdir()
    sandbox_name = "sbox-test"

    fake_sandbox = MagicMock()
    fake_handle = _FakeHandle(
        [
            SimpleNamespace(event_type="stdout", data=b"hello\n"),
            SimpleNamespace(event_type="exited", code=0),
        ]
    )
    fake_sandbox.shell_stream = AsyncMock(return_value=fake_handle)
    runtime._sandboxes[sandbox_name] = fake_sandbox

    monkeypatch.setattr(
        runtime,
        "create_session",
        AsyncMock(return_value=None),
    )

    result = await runtime.exec_command(
        sandbox_name=sandbox_name,
        image="test:latest",
        root_path=str(root),
        command="python -c 'print(1)'",
        cwd="/workspace",
        timeout_seconds=5,
        env={},
        limits=SessionLimits(),
        max_output_bytes=1024,
    )

    assert isinstance(result, ExecResult)
    assert result.exit_code == 0
    assert result.stdout == b"hello\n"
    assert result.timed_out is False

    kwargs = fake_sandbox.shell_stream.await_args.kwargs
    assert kwargs["stdin"] == Stdin.null()
    assert kwargs["env"]["MPLBACKEND"] == "Agg"
    assert "PYTHONUNBUFFERED" in kwargs["env"]
