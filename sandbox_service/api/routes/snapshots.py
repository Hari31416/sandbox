from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Response

from sandbox_service.app_state import AppState
from sandbox_service.models import CreateSnapshotRequest, SnapshotResponse
from sandbox_service.runtime import get_runtime
from sandbox_service.runtime.local import build_sandbox_name
from sandbox_service.snapshot_workspace import (
    archive_workspace,
    remove_workspace_archive,
    workspace_archive_path,
)

from ._shared import (
    AuthDep,
    _default_snapshot_name,
    _get_session,
    _snapshot_response,
    get_state,
    router,
)


@router.post(
    "/v1/sessions/{session_id}/snapshots",
    response_model=SnapshotResponse,
    status_code=201,
)
async def create_snapshot(
    session_id: str,
    body: CreateSnapshotRequest,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
) -> SnapshotResponse:
    session = _get_session(state, session_id)
    if session.backend != "microsandbox":
        raise HTTPException(status_code=400, detail="snapshots_not_supported")

    runtime = get_runtime(state.runtimes, session.backend)
    if not runtime.supports_snapshots():
        raise HTTPException(status_code=400, detail="snapshots_not_supported")

    if session.status in {"active", "creating"}:
        if not body.stop_session:
            raise HTTPException(status_code=409, detail="session_not_stopped")
        if session.sandbox_name:
            await runtime.stop_session(sandbox_name=session.sandbox_name)
        state.sessions.update_status(session_id, "stopped")
    elif session.status not in {"stopped", "expired"}:
        raise HTTPException(status_code=409, detail=f"session_{session.status}")

    snapshot_name = body.name or _default_snapshot_name(session_id)
    labels = {
        "workspace_id": session.workspace_id,
        "source_session_id": session_id,
        **{k: str(v) for k, v in body.metadata.items()},
    }
    sandbox_name = session.sandbox_name or build_sandbox_name(session_id)
    info = await runtime.create_snapshot(
        sandbox_name=sandbox_name,
        name=snapshot_name,
        labels=labels,
    )
    record = state.snapshots.create(
        workspace_id=session.workspace_id,
        source_session_id=session_id,
        name=snapshot_name,
        msb_name=info.msb_name,
        digest=info.digest,
        image_ref=info.image_ref,
        size_bytes=info.size_bytes,
        include_workspace=body.include_workspace,
        workspace_bytes=0,
        workspace_archive_path=None,
        metadata=body.metadata,
    )
    if body.include_workspace and session.root_path:
        archive_path = workspace_archive_path(
            state.settings.resolved_snapshots_root,
            record.id,
        )
        workspace_bytes = archive_workspace(
            workspace_path=Path(session.root_path),
            destination=archive_path,
        )
        record = state.snapshots.update_workspace_bundle(
            record.id,
            workspace_bytes=workspace_bytes,
            workspace_archive_path=str(archive_path),
        )
    return _snapshot_response(record)


@router.get("/v1/snapshots", response_model=list[SnapshotResponse])
async def list_snapshots(
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
    workspace_id: str,
) -> list[SnapshotResponse]:
    records = state.snapshots.list_snapshots(workspace_id=workspace_id)
    return [_snapshot_response(record) for record in records]


@router.get("/v1/snapshots/{snapshot_id}", response_model=SnapshotResponse)
async def get_snapshot(
    snapshot_id: str,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
) -> SnapshotResponse:
    try:
        return _snapshot_response(state.snapshots.get(snapshot_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="snapshot_not_found") from None


@router.delete("/v1/snapshots/{snapshot_id}", status_code=204)
async def delete_snapshot(
    snapshot_id: str,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
) -> Response:
    try:
        record = state.snapshots.get(snapshot_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="snapshot_not_found") from None

    runtime = get_runtime(state.runtimes, "microsandbox")
    if runtime.supports_snapshots():
        try:
            await runtime.delete_snapshot(msb_name=record.msb_name)
        except Exception:
            pass
    if record.workspace_archive_path:
        remove_workspace_archive(Path(record.workspace_archive_path))
    state.snapshots.delete(snapshot_id)
    return Response(status_code=204)
