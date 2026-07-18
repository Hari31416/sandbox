"""Sandbox bearer auth and fail-closed deploy profile (H1)."""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest

from sandbox_service.app_state import build_app_state
from sandbox_service.config import get_settings
from sandbox_service.db import init_database
from sandbox_service.main import create_app, enforce_sandbox_secure_defaults
from sandbox_service.secure_defaults import SecureDefaultsError


@pytest.fixture
async def authed_client(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SANDBOX_AUTH_TOKEN", "test-sandbox-token")
    monkeypatch.setenv("SANDBOX_DEPLOY_PROFILE", "local")
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


async def test_healthz_rejects_missing_bearer(authed_client: httpx.AsyncClient) -> None:
    response = await authed_client.get("/healthz")
    assert response.status_code == 401


async def test_healthz_rejects_wrong_bearer(authed_client: httpx.AsyncClient) -> None:
    response = await authed_client.get(
        "/healthz",
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401


async def test_healthz_accepts_correct_bearer(authed_client: httpx.AsyncClient) -> None:
    response = await authed_client.get(
        "/healthz",
        headers={"Authorization": "Bearer test-sandbox-token"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_staging_profile_refuses_empty_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SANDBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SANDBOX_DEPLOY_PROFILE", "staging")
    monkeypatch.delenv("SANDBOX_AUTH_TOKEN", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    with pytest.raises(SecureDefaultsError):
        enforce_sandbox_secure_defaults(settings)
    get_settings.cache_clear()


def test_staging_profile_ok_with_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SANDBOX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SANDBOX_DEPLOY_PROFILE", "staging")
    monkeypatch.setenv("SANDBOX_AUTH_TOKEN", "tok")
    get_settings.cache_clear()
    settings = get_settings()
    enforce_sandbox_secure_defaults(settings)
    get_settings.cache_clear()
