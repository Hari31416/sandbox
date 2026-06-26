from __future__ import annotations

import asyncio

import httpx
import pytest
from contextlib import asynccontextmanager

from sandbox import HttpSandboxBackend
from sandbox_service.config import get_settings
from sandbox_service.db import init_database
from sandbox_service.main import create_app
from sandbox_service.app_state import build_app_state


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
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    get_settings.cache_clear()


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
async def test_http_backend_adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    settings = get_settings()
    init_database(settings.resolved_sqlite_path)
    app = create_app()
    app.state.sandbox = build_app_state(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
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
