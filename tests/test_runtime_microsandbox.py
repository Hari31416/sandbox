from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
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


class SuccessExecHandle:
    def __init__(self, events: list[object] | None = None) -> None:
        self.killed = False
        self._events = list(
            events
            or [
                SimpleNamespace(event_type="stdout", data=b"ok\n"),
                SimpleNamespace(event_type="exited", code=0),
            ]
        )

    async def kill(self) -> None:
        self.killed = True

    def __aiter__(self) -> SuccessExecHandle:
        return self

    async def __anext__(self) -> object:
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)


@dataclass
class FakeSandbox:
    handles: list[object]
    stop_calls: int = 0
    _index: int = 0

    async def shell_stream(self, *args: object, **kwargs: object) -> object:
        handle = self.handles[min(self._index, len(self.handles) - 1)]
        self._index += 1
        return handle

    async def stop_and_wait(self) -> None:
        self.stop_calls += 1

    async def kill(self) -> None:
        return None


@dataclass
class CatalogHandle:
    name: str
    status: str
    stop: AsyncMock = field(default_factory=AsyncMock)
    kill: AsyncMock = field(default_factory=AsyncMock)
    remove: AsyncMock = field(default_factory=AsyncMock)
    connect: AsyncMock = field(default_factory=AsyncMock)


def _runtime(tmp_path) -> MicrosandboxRuntime:
    runtime = MicrosandboxRuntime(
        scratch_root=tmp_path,
        guest_workspace_path="/workspace",
    )
    runtime.is_available = lambda: True  # type: ignore[method-assign]
    return runtime


@pytest.mark.asyncio
async def test_exec_timeout_keeps_sandbox(monkeypatch, tmp_path) -> None:
    exec_handle = TimeoutExecHandle()
    sandbox = FakeSandbox(handles=[exec_handle])
    remove = AsyncMock()
    monkeypatch.setattr(microsandbox.Sandbox, "remove", remove)

    runtime = _runtime(tmp_path)
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
    assert sandbox.stop_calls == 0
    remove.assert_not_awaited()
    assert runtime._sandboxes["sbox"] is sandbox
    assert "sbox" not in runtime._active_execs


@pytest.mark.asyncio
async def test_exec_timeout_preserves_overlay_for_next_command(
    monkeypatch, tmp_path
) -> None:
    timeout_handle = TimeoutExecHandle()
    success_handle = SuccessExecHandle(
        [
            SimpleNamespace(event_type="stdout", data=b"numpy-ok\n"),
            SimpleNamespace(event_type="exited", code=0),
        ]
    )
    sandbox = FakeSandbox(handles=[timeout_handle, success_handle])
    remove = AsyncMock()
    monkeypatch.setattr(microsandbox.Sandbox, "remove", remove)

    runtime = _runtime(tmp_path)
    runtime._sandboxes["sbox"] = sandbox
    kwargs = {
        "sandbox_name": "sbox",
        "image": "python:3.12",
        "root_path": str(tmp_path / "workspace"),
        "cwd": "/workspace",
        "env": {},
        "limits": SessionLimits(),
        "max_output_bytes": 1024,
    }

    timed_out = await runtime.exec_command(
        command="python3 -c 'import time; time.sleep(30)'",
        timeout_seconds=1,
        **kwargs,
    )
    assert timed_out.timed_out is True
    assert timed_out.exit_code == 124

    follow_up = await runtime.exec_command(
        command="python3 -c 'import numpy; print(\"numpy-ok\")'",
        timeout_seconds=5,
        **kwargs,
    )
    assert follow_up.timed_out is False
    assert follow_up.exit_code == 0
    assert follow_up.stdout == b"numpy-ok\n"
    remove.assert_not_awaited()
    assert runtime._sandboxes["sbox"] is sandbox


@pytest.mark.asyncio
async def test_create_session_replaces_crashed_sandbox(monkeypatch, tmp_path) -> None:
    crashed = CatalogHandle(name="sbox", status="crashed")
    created = object()
    list_mock = AsyncMock(side_effect=[[crashed], [crashed], []])
    create_mock = AsyncMock(return_value=created)
    start_mock = AsyncMock()
    get_mock = AsyncMock(return_value=crashed)
    monkeypatch.setattr(microsandbox.Sandbox, "list", list_mock)
    monkeypatch.setattr(microsandbox.Sandbox, "create", create_mock)
    monkeypatch.setattr(microsandbox.Sandbox, "start", start_mock)
    monkeypatch.setattr(microsandbox.Sandbox, "get", get_mock)
    monkeypatch.setattr(microsandbox.Sandbox, "remove", AsyncMock())

    runtime = _runtime(tmp_path)
    await runtime.create_session(
        session_id="sbox",
        sandbox_name="sbox",
        image="python:3.12",
        root_path=str(tmp_path / "workspace"),
        limits=SessionLimits(),
    )

    start_mock.assert_not_awaited()
    create_mock.assert_awaited_once()
    assert runtime._sandboxes["sbox"] is created


@pytest.mark.asyncio
async def test_create_session_reuses_running_sandbox(monkeypatch, tmp_path) -> None:
    running = CatalogHandle(name="sbox", status="running")
    connected = object()
    running.connect = AsyncMock(return_value=connected)
    monkeypatch.setattr(microsandbox.Sandbox, "list", AsyncMock(return_value=[running]))
    monkeypatch.setattr(microsandbox.Sandbox, "get", AsyncMock(return_value=running))
    create_mock = AsyncMock()
    start_mock = AsyncMock()
    monkeypatch.setattr(microsandbox.Sandbox, "create", create_mock)
    monkeypatch.setattr(microsandbox.Sandbox, "start", start_mock)

    runtime = _runtime(tmp_path)
    await runtime.create_session(
        session_id="sbox",
        sandbox_name="sbox",
        image="python:3.12",
        root_path=str(tmp_path / "workspace"),
        limits=SessionLimits(),
    )

    running.connect.assert_awaited_once()
    create_mock.assert_not_awaited()
    start_mock.assert_not_awaited()
    assert runtime._sandboxes["sbox"] is connected
