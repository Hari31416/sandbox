from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from sandbox import HttpSandboxBackend
from sandbox_service.app_state import build_app_state
from sandbox_service.config import get_settings
from sandbox_service.db import init_database
from sandbox_service.main import create_app
from sandbox_service.models import SessionLimits
from sandbox_service.runtime.base import ExecResult, SnapshotInfo


@dataclass
class FakeMicrosandboxRuntime:
    name: str = "microsandbox"
    snapshots_created: list[dict] = field(default_factory=list)
    sessions_created: list[dict] = field(default_factory=list)
    deleted_snapshots: list[str] = field(default_factory=list)
    stopped_sandboxes: list[str] = field(default_factory=list)

    def is_available(self) -> bool:
        return True

    def supports_snapshots(self) -> bool:
        return True

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
        self.sessions_created.append(
            {
                "session_id": session_id,
                "sandbox_name": sandbox_name,
                "image": image,
                "root_path": root_path,
                "snapshot": snapshot,
                "limits": limits,
            }
        )

    async def stop_session(self, *, sandbox_name: str) -> None:
        self.stopped_sandboxes.append(sandbox_name)

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
        return ExecResult(exit_code=0, stdout=b"ok\n", stderr=b"")

    async def create_snapshot(
        self,
        *,
        sandbox_name: str,
        name: str,
        labels: dict[str, str],
    ) -> SnapshotInfo:
        self.snapshots_created.append(
            {"sandbox_name": sandbox_name, "name": name, "labels": labels}
        )
        return SnapshotInfo(
            msb_name=name,
            digest=f"digest-{name}",
            image_ref="python:3.12",
            size_bytes=1024,
        )

    async def delete_snapshot(self, *, msb_name: str) -> None:
        self.deleted_snapshots.append(msb_name)

    async def list_snapshots(self) -> list[SnapshotInfo]:
        return []


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    settings = get_settings()
    init_database(settings.resolved_sqlite_path)
    app = create_app()
    state = build_app_state(settings)
    app.state.sandbox = state

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        yield http_client
    get_settings.cache_clear()


@pytest.fixture
async def mock_msb_client(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    settings = get_settings()
    init_database(settings.resolved_sqlite_path)
    app = create_app()
    state = build_app_state(settings)
    fake_runtime = FakeMicrosandboxRuntime()
    state.runtimes["microsandbox"] = fake_runtime
    app.state.sandbox = state

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        yield http_client, fake_runtime
    get_settings.cache_clear()


async def _create_microsandbox_session(
    client: httpx.AsyncClient,
    *,
    workspace_id: str = "ws_msb",
    status: str = "active",
) -> dict:
    create = await client.post(
        "/v1/sessions",
        json={
            "workspace_id": workspace_id,
            "run_id": "run_msb",
            "image": "python:3.12",
            "backend": "microsandbox",
            "limits": {"network": "disabled"},
        },
    )
    assert create.status_code == 201
    session = create.json()
    if status == "stopped":
        stop = await client.post(f"/v1/sessions/{session['id']}/stop")
        assert stop.status_code == 200
        session = stop.json()
    return session


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    settings = get_settings()
    init_database(settings.resolved_sqlite_path)
    app = create_app()
    state = build_app_state(settings)
    app.state.sandbox = state

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        yield http_client
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_backends_include_snapshot_capability(client: httpx.AsyncClient):
    response = await client.get("/v1/backends")
    assert response.status_code == 200
    backends = {item["name"]: item for item in response.json()["backends"]}
    assert "supports_snapshots" in backends["local"]
    assert backends["local"]["supports_snapshots"] is False


@pytest.mark.asyncio
async def test_local_snapshot_not_supported(client: httpx.AsyncClient):
    create = await client.post(
        "/v1/sessions",
        json={
            "workspace_id": "ws_local_snap",
            "backend": "local",
            "limits": {"network": "disabled"},
        },
    )
    assert create.status_code == 201
    session_id = create.json()["id"]
    await client.post(f"/v1/sessions/{session_id}/stop")

    response = await client.post(f"/v1/sessions/{session_id}/snapshots", json={})
    assert response.status_code == 400
    assert response.json()["detail"] == "snapshots_not_supported"

    await client.delete(f"/v1/sessions/{session_id}")


@pytest.mark.asyncio
async def test_create_snapshot_on_stopped_session(mock_msb_client):
    client, fake_runtime = mock_msb_client
    session = await _create_microsandbox_session(client, status="stopped")

    response = await client.post(
        f"/v1/sessions/{session['id']}/snapshots",
        json={"name": "my-snapshot"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "my-snapshot"
    assert body["digest"] == "digest-my-snapshot"
    assert body["source_session_id"] == session["id"]
    assert body["include_workspace"] is True
    assert len(fake_runtime.snapshots_created) == 1

    listed = await client.get("/v1/snapshots", params={"workspace_id": "ws_msb"})
    assert listed.status_code == 200
    assert len(listed.json()) == 1


@pytest.mark.asyncio
async def test_create_snapshot_stops_active_session(mock_msb_client):
    client, fake_runtime = mock_msb_client
    session = await _create_microsandbox_session(client, status="active")

    response = await client.post(
        f"/v1/sessions/{session['id']}/snapshots",
        json={"stop_session": True},
    )
    assert response.status_code == 201
    assert fake_runtime.stopped_sandboxes

    refreshed = await client.get(f"/v1/sessions/{session['id']}")
    assert refreshed.json()["status"] == "stopped"


@pytest.mark.asyncio
async def test_create_snapshot_requires_stop_when_active(mock_msb_client):
    client, _fake_runtime = mock_msb_client
    session = await _create_microsandbox_session(client, status="active")

    response = await client.post(
        f"/v1/sessions/{session['id']}/snapshots",
        json={"stop_session": False},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "session_not_stopped"


@pytest.mark.asyncio
async def test_snapshot_list_get_delete_lifecycle(mock_msb_client):
    client, fake_runtime = mock_msb_client
    session = await _create_microsandbox_session(client, status="stopped")

    created = await client.post(f"/v1/sessions/{session['id']}/snapshots", json={})
    snapshot_id = created.json()["id"]

    got = await client.get(f"/v1/snapshots/{snapshot_id}")
    assert got.status_code == 200

    deleted = await client.delete(f"/v1/snapshots/{snapshot_id}")
    assert deleted.status_code == 204
    assert fake_runtime.deleted_snapshots == [created.json()["name"]]

    missing = await client.get(f"/v1/snapshots/{snapshot_id}")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_create_session_from_snapshot(mock_msb_client):
    client, fake_runtime = mock_msb_client
    session = await _create_microsandbox_session(client, status="stopped")
    created = await client.post(f"/v1/sessions/{session['id']}/snapshots", json={})
    snapshot_id = created.json()["id"]

    restore = await client.post(
        "/v1/sessions",
        json={
            "workspace_id": "ws_msb",
            "snapshot_id": snapshot_id,
            "limits": {"network": "disabled"},
        },
    )
    assert restore.status_code == 201
    restored = restore.json()
    assert restored["backend"] == "microsandbox"
    assert restored["image"] == "python:3.12"
    assert fake_runtime.sessions_created[-1]["snapshot"] == created.json()["name"]


@pytest.mark.asyncio
async def test_create_snapshot_with_workspace_files(mock_msb_client, tmp_path):
    client, _fake_runtime = mock_msb_client
    session = await _create_microsandbox_session(client, status="stopped")
    workspace = Path(session["root_path"])
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "notes.txt").write_text("checkpoint\n")

    response = await client.post(
        f"/v1/sessions/{session['id']}/snapshots",
        json={"include_workspace": True},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["include_workspace"] is True
    assert body["workspace_bytes"] > 0

    archive = tmp_path / "snapshot-workspaces" / body["id"] / "workspace.tar.gz"
    assert archive.exists()


@pytest.mark.asyncio
async def test_create_snapshot_without_workspace_files(mock_msb_client, tmp_path):
    client, _fake_runtime = mock_msb_client
    session = await _create_microsandbox_session(client, status="stopped")
    workspace = Path(session["root_path"])
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "notes.txt").write_text("checkpoint\n")

    response = await client.post(
        f"/v1/sessions/{session['id']}/snapshots",
        json={"include_workspace": False},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["include_workspace"] is False
    assert body["workspace_bytes"] == 0

    archive_dir = tmp_path / "snapshot-workspaces" / body["id"]
    assert not archive_dir.exists()


@pytest.mark.asyncio
async def test_restore_session_from_snapshot_with_workspace_files(mock_msb_client):
    client, fake_runtime = mock_msb_client
    session = await _create_microsandbox_session(client, status="stopped")
    workspace = Path(session["root_path"])
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "main.py").write_text("print('resume')\n")

    created = await client.post(
        f"/v1/sessions/{session['id']}/snapshots",
        json={"include_workspace": True},
    )
    snapshot_id = created.json()["id"]

    restore = await client.post(
        "/v1/sessions",
        json={
            "workspace_id": "ws_msb",
            "snapshot_id": snapshot_id,
            "limits": {"network": "disabled"},
        },
    )
    assert restore.status_code == 201
    restored_workspace = Path(restore.json()["root_path"])
    assert (restored_workspace / "main.py").read_text() == "print('resume')\n"
    assert fake_runtime.sessions_created[-1]["snapshot"] == created.json()["name"]


@pytest.mark.asyncio
async def test_healthz(client: httpx.AsyncClient):
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_local_session_lifecycle(client: httpx.AsyncClient):
    create = await client.post(
        "/v1/sessions",
        json={
            "workspace_id": "ws_test",
            "run_id": "run_test",
            "image": "python:3.12",
            "backend": "local",
            "limits": {"network": "disabled"},
        },
    )
    assert create.status_code == 201
    session = create.json()
    session_id = session["id"]

    write = await client.put(
        f"/v1/sessions/{session_id}/files",
        json={
            "path": "/workspace/main.py",
            "content_base64": "cHJpbnQoJ2hlbGxvJykK",
        },
    )
    assert write.status_code == 200

    exec_response = await client.post(
        f"/v1/sessions/{session_id}/execs",
        json={"command": "python main.py", "cwd": "/workspace", "timeout_seconds": 30},
    )
    assert exec_response.status_code == 200
    assert exec_response.json()["exit_code"] == 0

    stop = await client.post(f"/v1/sessions/{session_id}/stop")
    assert stop.status_code == 200

    delete = await client.delete(f"/v1/sessions/{session_id}")
    assert delete.status_code == 204


@pytest.mark.asyncio
async def test_sync_artifacts_includes_workspace_root_files(client: httpx.AsyncClient):
    create = await client.post(
        "/v1/sessions",
        json={
            "workspace_id": "ws_artifacts",
            "run_id": "run_artifacts",
            "image": "python:3.12",
            "backend": "local",
            "limits": {"network": "disabled"},
        },
    )
    assert create.status_code == 201
    session_id = create.json()["id"]

    for path, content in (
        ("/workspace/main.py", "cHJpbnQoJ29rJykK"),
        ("/workspace/output.txt", "ZG9uZQo="),
    ):
        write = await client.put(
            f"/v1/sessions/{session_id}/files",
            json={"path": path, "content_base64": content},
        )
        assert write.status_code == 200

    sync = await client.post(
        f"/v1/sessions/{session_id}/artifacts/sync",
        json={
            "paths": ["/workspace"],
            "destination_prefix": "runs/run_artifacts/artifacts",
        },
    )
    assert sync.status_code == 200
    artifacts = sync.json()
    assert len(artifacts) == 2
    exported_paths = {item["source_path"] for item in artifacts}
    assert exported_paths == {"main.py", "output.txt"}

    await client.delete(f"/v1/sessions/{session_id}")


@pytest.mark.asyncio
async def test_exec_timeout_marks_timed_out_and_preserves_partial_output(
    client: httpx.AsyncClient,
):
    create = await client.post(
        "/v1/sessions",
        json={
            "workspace_id": "ws_timeout",
            "image": "python:3.12",
            "backend": "local",
            "limits": {"network": "disabled"},
        },
    )
    assert create.status_code == 201
    session_id = create.json()["id"]

    exec_response = await client.post(
        f"/v1/sessions/{session_id}/execs",
        json={
            "command": "python -c \"import time; print('before', flush=True); time.sleep(5)\"",
            "cwd": "/workspace",
            "timeout_seconds": 1,
        },
    )
    assert exec_response.status_code == 200
    payload = exec_response.json()
    assert payload["status"] == "timed_out"
    assert payload["exit_code"] == 124
    assert payload["timeout_seconds"] == 1

    stderr = await client.get(f"/v1/sessions/{session_id}/execs/{payload['id']}/stderr")
    assert stderr.status_code == 200
    assert b"timed out" in stderr.content

    await client.delete(f"/v1/sessions/{session_id}")


@pytest.mark.asyncio
async def test_exec_timeout_is_clamped_to_max(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SANDBOX_MAX_EXEC_TIMEOUT_SECONDS", "2")
    get_settings.cache_clear()
    settings = get_settings()
    init_database(settings.resolved_sqlite_path)
    app = create_app()
    app.state.sandbox = build_app_state(settings)

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        create = await http_client.post(
            "/v1/sessions",
            json={
                "workspace_id": "ws_clamp",
                "image": "python:3.12",
                "backend": "local",
                "limits": {"network": "disabled"},
            },
        )
        session_id = create.json()["id"]
        exec_response = await http_client.post(
            f"/v1/sessions/{session_id}/execs",
            json={
                "command": 'python -c "import time; time.sleep(10)"',
                "timeout_seconds": 9999,
            },
        )
        assert exec_response.status_code == 200
        payload = exec_response.json()
        assert payload["timeout_seconds"] == 2
        assert payload["status"] == "timed_out"
        await http_client.delete(f"/v1/sessions/{session_id}")
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_cleanup_expired_sessions_does_not_raise_after_delete(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SANDBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SANDBOX_SESSION_TTL_SECONDS", "1")
    get_settings.cache_clear()
    settings = get_settings()
    init_database(settings.resolved_sqlite_path)
    state = build_app_state(settings)
    state.runtimes["microsandbox"] = FakeMicrosandboxRuntime()

    session = state.sessions.create(
        workspace_id="ws_expired",
        run_id=None,
        image="python:3.12",
        backend="local",
        root_path=str(tmp_path / "scratch" / "sess_test" / "workspace"),
        sandbox_name=None,
        limits=SessionLimits(),
        metadata={},
        ttl_seconds=0,
    )
    (tmp_path / "scratch" / session.id / "workspace").mkdir(parents=True, exist_ok=True)
    state.sessions.update_runtime_paths(
        session.id,
        root_path=str(tmp_path / "scratch" / session.id / "workspace"),
        sandbox_name=None,
    )

    removed, _ = await state.cleanup.run_once()
    assert removed >= 1
    with pytest.raises(KeyError):
        state.sessions.get(session.id)
    # Second pass must also succeed (no KeyError from update_status-after-delete).
    removed_again, _ = await state.cleanup.run_once()
    assert removed_again == 0
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_reconcile_orphans_preserves_scratch_created_during_list(
    tmp_path, monkeypatch
):
    """Active session scratch must survive reconcile that started before create.

    Reproduces the session_workspace_missing race: cleanup snapshots active
    leases, then a new session creates its scratch while list_sandboxes is
    slow; reconcile must not delete that live workspace.
    """
    monkeypatch.setenv("SANDBOX_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    settings = get_settings()
    init_database(settings.resolved_sqlite_path)
    state = build_app_state(settings)

    scratch_root = settings.resolved_scratch_root
    scratch_root.mkdir(parents=True, exist_ok=True)
    orphan_id = "sess_orphan_scratch"
    (scratch_root / orphan_id / "workspace").mkdir(parents=True)

    created: dict[str, object] = {}

    class SlowListRuntime(FakeMicrosandboxRuntime):
        async def list_sandboxes(self) -> list[str]:
            session = state.sessions.create(
                workspace_id="ws_live",
                run_id="run_live",
                image="python:3.12",
                backend="local",
                root_path="",
                sandbox_name="sbox-live",
                limits=SessionLimits(),
                metadata={},
                ttl_seconds=300,
            )
            workspace = scratch_root / session.id / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            marker = workspace / "staged.txt"
            marker.write_text("keep-me", encoding="utf-8")
            state.sessions.update_runtime_paths(
                session.id,
                root_path=str(workspace),
                sandbox_name="sbox-live",
            )
            created["session_id"] = session.id
            created["workspace"] = workspace
            return []

    # Mutate the shared registry CleanupLoop holds (do not rebind).
    state.runtimes.clear()
    state.runtimes["local"] = SlowListRuntime()
    await state.cleanup._reconcile_orphans()

    live_id = created["session_id"]
    live_workspace = Path(created["workspace"])
    assert state.sessions.get(live_id).status == "active"
    assert live_workspace.is_dir()
    assert (live_workspace / "staged.txt").read_text(encoding="utf-8") == "keep-me"
    assert not (scratch_root / orphan_id).exists()
    get_settings.cache_clear()


def test_resolve_session_ttl_seconds() -> None:
    from sandbox_service.api.routes import resolve_session_ttl_seconds

    assert (
        resolve_session_ttl_seconds(
            limits_timeout_seconds=300, session_ttl_seconds=3600
        )
        == 300
    )
    assert (
        resolve_session_ttl_seconds(
            limits_timeout_seconds=7200, session_ttl_seconds=3600
        )
        == 3600
    )
    assert (
        resolve_session_ttl_seconds(limits_timeout_seconds=0, session_ttl_seconds=3600)
        == 1
    )


@pytest.mark.asyncio
async def test_session_ttl_honors_limits_timeout(mock_msb_client):
    client, _runtime = mock_msb_client
    create = await client.post(
        "/v1/sessions",
        json={
            "workspace_id": "ws_ttl",
            "run_id": "run_ttl",
            "image": "python:3.12",
            "backend": "microsandbox",
            "limits": {"timeout_seconds": 120, "network": "disabled"},
        },
    )
    assert create.status_code == 201
    payload = create.json()
    created = datetime.fromisoformat(payload["created_at"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
    assert abs((expires - created).total_seconds() - 120) < 2
    await client.delete(f"/v1/sessions/{payload['id']}")


@pytest.mark.asyncio
async def test_max_active_sessions_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SANDBOX_MAX_ACTIVE_SESSIONS", "1")
    get_settings.cache_clear()
    settings = get_settings()
    init_database(settings.resolved_sqlite_path)
    app = create_app()
    state = build_app_state(settings)
    state.runtimes["microsandbox"] = FakeMicrosandboxRuntime()
    app.state.sandbox = state

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app.router.lifespan_context = noop_lifespan
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        first = await http_client.post(
            "/v1/sessions",
            json={
                "workspace_id": "ws_cap",
                "backend": "microsandbox",
                "limits": {"network": "disabled"},
            },
        )
        assert first.status_code == 201
        second = await http_client.post(
            "/v1/sessions",
            json={
                "workspace_id": "ws_cap2",
                "backend": "microsandbox",
                "limits": {"network": "disabled"},
            },
        )
        assert second.status_code == 429
        assert second.json()["detail"] == "max_active_sessions_exceeded"
        await http_client.delete(f"/v1/sessions/{first.json()['id']}")
        third = await http_client.post(
            "/v1/sessions",
            json={
                "workspace_id": "ws_cap3",
                "backend": "microsandbox",
                "limits": {"network": "disabled"},
            },
        )
        assert third.status_code == 201
        await http_client.delete(f"/v1/sessions/{third.json()['id']}")
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_http_backend_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    settings = get_settings()
    init_database(settings.resolved_sqlite_path)
    app = create_app()
    app.state.sandbox = build_app_state(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as http_client:
        backend = HttpSandboxBackend(base_url="http://test")
        backend._client = http_client
        session = await backend.create_session(
            workspace_id="ws_adapter",
            image="python:3.12",
            limits={"network": "disabled"},
            backend="local",
        )
        await backend.write_file(
            session["id"],
            "/workspace/script.py",
            b"print(42)\n",
        )
        result = await backend.exec(session["id"], "python script.py", timeout=30)
        assert result["exit_code"] == 0
        await backend.delete_session(session["id"])
    get_settings.cache_clear()
