from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from sandbox_service.app_state import AppState
from sandbox_service.models import ArtifactInfo, GcResponse, SyncArtifactsRequest

from ._shared import AuthDep, _artifact_info, _get_active_session, get_state, router


@router.post(
    "/v1/sessions/{session_id}/artifacts/sync", response_model=list[ArtifactInfo]
)
async def sync_artifacts(
    session_id: str,
    body: SyncArtifactsRequest,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
) -> list[ArtifactInfo]:
    session = _get_active_session(state, session_id)
    records = state.artifact_exporter.sync(
        session_id=session_id,
        root_path=session.root_path,
        paths=body.paths,
        destination_prefix=body.destination_prefix,
        include_globs=body.include_globs,
        exclude_globs=body.exclude_globs,
    )
    return [_artifact_info(record) for record in records]


@router.get("/v1/sessions/{session_id}/artifacts", response_model=list[ArtifactInfo])
async def list_artifacts(
    session_id: str,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
) -> list[ArtifactInfo]:
    _get_active_session(state, session_id)
    return [
        _artifact_info(record)
        for record in state.artifacts.list_for_session(session_id)
    ]


@router.post("/v1/gc", response_model=GcResponse)
async def run_gc(
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
) -> GcResponse:
    sessions_removed, exec_logs_removed = await state.cleanup.run_once()
    return GcResponse(
        sessions_removed=sessions_removed,
        exec_logs_removed=exec_logs_removed,
    )
