from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Response

from sandbox_service.app_state import AppState
from sandbox_service.models import (
    CreateSessionRequest,
    HeartbeatRequest,
    SessionResponse,
)
from sandbox_service.repositories import SnapshotRecord
from sandbox_service.runtime import get_runtime
from sandbox_service.runtime.local import build_sandbox_name
from sandbox_service.snapshot_workspace import restore_workspace
from sandbox_service.workspace import ensure_workspace, remove_workspace

from ._shared import (
    AuthDep,
    _get_active_session,
    _session_response,
    get_state,
    resolve_session_ttl_seconds,
    router,
)


@router.post("/v1/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    body: CreateSessionRequest,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
) -> SessionResponse:
    snapshot_record: SnapshotRecord | None = None
    if body.snapshot_id:
        try:
            snapshot_record = state.snapshots.get(body.snapshot_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="snapshot_not_found") from None
        if snapshot_record.workspace_id != body.workspace_id:
            raise HTTPException(status_code=400, detail="snapshot_workspace_mismatch")

    backend_name = (
        "microsandbox"
        if snapshot_record
        else (body.backend or state.settings.default_backend)
    )
    runtime = get_runtime(state.runtimes, backend_name)
    if snapshot_record and not runtime.supports_snapshots():
        raise HTTPException(status_code=400, detail="snapshots_not_supported")

    image = (
        snapshot_record.image_ref
        if snapshot_record
        else (body.image or state.settings.default_image)
    )
    max_active = int(state.settings.max_active_sessions)
    if max_active > 0 and state.sessions.count_active() >= max_active:
        raise HTTPException(
            status_code=429,
            detail="max_active_sessions_exceeded",
        )
    ttl_seconds = resolve_session_ttl_seconds(
        limits_timeout_seconds=body.limits.timeout_seconds,
        session_ttl_seconds=state.settings.session_ttl_seconds,
    )
    session = state.sessions.create(
        workspace_id=body.workspace_id,
        run_id=body.run_id,
        image=image,
        backend=backend_name,
        root_path="",
        sandbox_name=None,
        limits=body.limits,
        metadata=body.metadata,
        ttl_seconds=ttl_seconds,
    )
    root_path = str(ensure_workspace(state.settings.resolved_scratch_root, session.id))
    if (
        snapshot_record is not None
        and snapshot_record.include_workspace
        and snapshot_record.workspace_archive_path
    ):
        restore_workspace(
            archive_path=Path(snapshot_record.workspace_archive_path),
            workspace_path=Path(root_path),
        )
    sandbox_name = (
        build_sandbox_name(session.id) if backend_name == "microsandbox" else None
    )
    try:
        await runtime.create_session(
            session_id=session.id,
            sandbox_name=sandbox_name or session.id,
            image=image,
            root_path=root_path,
            limits=body.limits,
            snapshot=snapshot_record.msb_name if snapshot_record else None,
        )
    except Exception:
        remove_workspace(state.settings.resolved_scratch_root, session.id)
        state.sessions.delete(session.id)
        raise
    record = state.sessions.update_runtime_paths(
        session.id,
        root_path=root_path,
        sandbox_name=sandbox_name,
    )
    return _session_response(record)


@router.get("/v1/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
) -> SessionResponse:
    try:
        return _session_response(state.sessions.get(session_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="session_not_found") from None


@router.get("/v1/sessions", response_model=list[SessionResponse])
async def list_sessions(
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
    workspace_id: str | None = None,
    run_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[SessionResponse]:
    records = state.sessions.list_sessions(
        workspace_id=workspace_id,
        run_id=run_id,
        status=status_filter,
    )
    return [_session_response(record) for record in records]


@router.post("/v1/sessions/{session_id}/heartbeat", response_model=SessionResponse)
async def heartbeat_session(
    session_id: str,
    body: HeartbeatRequest,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
) -> SessionResponse:
    _get_active_session(state, session_id)
    extend = body.extend_seconds or state.settings.heartbeat_extend_seconds
    try:
        record = state.sessions.heartbeat(session_id, extend)
    except KeyError:
        raise HTTPException(status_code=404, detail="session_not_found") from None
    return _session_response(record)


@router.post("/v1/sessions/{session_id}/stop", response_model=SessionResponse)
async def stop_session(
    session_id: str,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
) -> SessionResponse:
    session = _get_active_session(state, session_id)
    runtime = get_runtime(state.runtimes, session.backend)
    if session.sandbox_name:
        await runtime.stop_session(sandbox_name=session.sandbox_name)
    record = state.sessions.update_status(session_id, "stopped")
    return _session_response(record)


@router.delete("/v1/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
) -> Response:
    try:
        session = state.sessions.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session_not_found") from None
    runtime = get_runtime(state.runtimes, session.backend)
    sandbox_name = session.sandbox_name or session.id
    await runtime.delete_session(sandbox_name=sandbox_name)
    remove_workspace(state.settings.resolved_scratch_root, session_id)
    state.sessions.delete(session_id)
    return Response(status_code=204)
