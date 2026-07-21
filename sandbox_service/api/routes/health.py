from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException

from sandbox_service.app_state import AppState
from sandbox_service.models import (
    BackendCapabilities,
    BackendsResponse,
    HealthResponse,
    ReadyResponse,
)

from ._shared import AuthDep, get_state, router


@router.get("/healthz", response_model=HealthResponse)
async def healthz(_: AuthDep) -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadyResponse)
async def readyz(
    state: Annotated[AppState, Depends(get_state)], _: AuthDep
) -> ReadyResponse:
    backend = state.settings.default_backend
    runtime = state.runtimes.get(backend)
    sqlite_ok = state.settings.resolved_sqlite_path.exists()
    available = runtime.is_available() if runtime else False
    if not sqlite_ok or not available:
        raise HTTPException(status_code=503, detail="not_ready")
    return ReadyResponse(status="ready", backend=backend, sqlite_ok=sqlite_ok)


@router.get("/v1/backends", response_model=BackendsResponse)
async def list_backends(
    state: Annotated[AppState, Depends(get_state)], _: AuthDep
) -> BackendsResponse:
    backends = [
        BackendCapabilities(
            name=name,
            available=runtime.is_available(),
            supports_network_policy=name == "microsandbox",
            supports_streaming=False,
            supports_snapshots=runtime.supports_snapshots(),
        )
        for name, runtime in state.runtimes.items()
    ]
    return BackendsResponse(
        backends=backends,
        default_backend=state.settings.default_backend,
    )
