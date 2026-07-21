from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from sandbox_service.app_state import AppState
from sandbox_service.models import ArtifactInfo, SessionResponse, SnapshotResponse
from sandbox_service.repositories import SessionRecord, SnapshotRecord


def resolve_session_ttl_seconds(
    *,
    limits_timeout_seconds: int,
    session_ttl_seconds: int,
) -> int:
    """Session lease TTL: honor policy timeout, capped by service ceiling."""
    return max(1, min(int(limits_timeout_seconds), int(session_ttl_seconds)))


router = APIRouter()


def get_state(request: Request) -> AppState:
    return request.app.state.sandbox


def require_auth(
    request: Request, state: Annotated[AppState, Depends(get_state)]
) -> None:
    token = state.settings.auth_token
    if not token:
        return
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized"
        )


AuthDep = Annotated[None, Depends(require_auth)]


def _session_response(record: SessionRecord) -> SessionResponse:
    return SessionResponse(
        id=record.id,
        workspace_id=record.workspace_id,
        run_id=record.run_id,
        image=record.image,
        status=record.status,
        backend=record.backend,
        root_path=record.root_path,
        limits=record.limits,
        metadata=record.metadata,
        created_at=record.created_at,
        expires_at=record.expires_at,
        last_heartbeat_at=record.last_heartbeat_at,
        stopped_at=record.stopped_at,
    )


def _artifact_info(record) -> ArtifactInfo:
    return ArtifactInfo(
        id=record.id,
        session_id=record.session_id,
        source_path=record.source_path,
        artifact_uri=record.artifact_uri,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        created_at=record.created_at,
    )


def _snapshot_response(record: SnapshotRecord) -> SnapshotResponse:
    return SnapshotResponse(
        id=record.id,
        workspace_id=record.workspace_id,
        source_session_id=record.source_session_id,
        name=record.name,
        digest=record.digest,
        image_ref=record.image_ref,
        size_bytes=record.size_bytes,
        include_workspace=record.include_workspace,
        workspace_bytes=record.workspace_bytes,
        metadata=record.metadata,
        created_at=record.created_at,
    )


def _default_snapshot_name(session_id: str) -> str:
    digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]
    return f"snap-{digest}"


def _get_session(state: AppState, session_id: str) -> SessionRecord:
    try:
        return state.sessions.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session_not_found") from None


def _get_active_session(state: AppState, session_id: str) -> SessionRecord:
    try:
        session = state.sessions.get(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="session_not_found") from None
    if session.status not in {"active", "creating"}:
        raise HTTPException(status_code=409, detail=f"session_{session.status}")
    return session
