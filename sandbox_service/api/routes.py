from __future__ import annotations

import base64
import hashlib
import io
import tarfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, Response, StreamingResponse

from sandbox_service.app_state import AppState
from sandbox_service.models import (
    ArtifactInfo,
    BackendCapabilities,
    BackendsResponse,
    CreateSessionRequest,
    CreateSnapshotRequest,
    ExecRequest,
    ExecResponse,
    FileInfo,
    FileListEntry,
    GcResponse,
    HeartbeatRequest,
    HealthResponse,
    ReadyResponse,
    SessionResponse,
    SnapshotResponse,
    SyncArtifactsRequest,
    WriteFileRequest,
)
from sandbox_service.path_guard import PathEscapeError, resolve_host_path, sha256_file, write_file
from sandbox_service.repositories import SessionRecord, SnapshotRecord
from sandbox_service.runtime import get_runtime
from sandbox_service.runtime.local import build_sandbox_name
from sandbox_service.snapshot_workspace import (
    archive_workspace,
    remove_workspace_archive,
    restore_workspace,
    workspace_archive_path,
)
from sandbox_service.workspace import ensure_workspace, list_workspace_entries, remove_workspace


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


def require_auth(request: Request, state: Annotated[AppState, Depends(get_state)]) -> None:
    token = state.settings.auth_token
    if not token:
        return
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {token}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")


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


@router.get("/healthz", response_model=HealthResponse)
async def healthz(_: AuthDep) -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=ReadyResponse)
async def readyz(state: Annotated[AppState, Depends(get_state)], _: AuthDep) -> ReadyResponse:
    backend = state.settings.default_backend
    runtime = state.runtimes.get(backend)
    sqlite_ok = state.settings.resolved_sqlite_path.exists()
    available = runtime.is_available() if runtime else False
    if not sqlite_ok or not available:
        raise HTTPException(status_code=503, detail="not_ready")
    return ReadyResponse(status="ready", backend=backend, sqlite_ok=sqlite_ok)


@router.get("/v1/backends", response_model=BackendsResponse)
async def list_backends(state: Annotated[AppState, Depends(get_state)], _: AuthDep) -> BackendsResponse:
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

    backend_name = "microsandbox" if snapshot_record else (body.backend or state.settings.default_backend)
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
    sandbox_name = build_sandbox_name(session.id) if backend_name == "microsandbox" else None
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


@router.post("/v1/sessions/{session_id}/snapshots", response_model=SnapshotResponse, status_code=201)
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


@router.post("/v1/sessions/{session_id}/execs", response_model=ExecResponse)
async def create_exec(
    session_id: str,
    body: ExecRequest,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
) -> ExecResponse:
    session = _get_active_session(state, session_id)
    if not session.root_path or not Path(session.root_path).is_dir():
        raise HTTPException(
            status_code=409,
            detail="session_workspace_missing",
        )
    requested = body.timeout_seconds or state.settings.default_exec_timeout_seconds
    timeout = max(1, min(requested, state.settings.max_exec_timeout_seconds))
    exec_logs = state.settings.resolved_exec_logs_root / session_id
    exec_logs.mkdir(parents=True, exist_ok=True)
    stdout_path = exec_logs / f"stdout_{datetime.now().timestamp()}.log"
    stderr_path = exec_logs / f"stderr_{datetime.now().timestamp()}.log"
    record = state.execs.create(
        session_id=session_id,
        command=body.command,
        cwd=body.cwd,
        timeout_seconds=timeout,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )
    runtime = get_runtime(state.runtimes, session.backend)
    try:
        result = await runtime.exec_command(
            sandbox_name=session.sandbox_name or session.id,
            image=session.image,
            root_path=session.root_path,
            command=body.command,
            cwd=body.cwd,
            timeout_seconds=timeout,
            env=body.env,
            limits=session.limits,
            max_output_bytes=state.settings.max_exec_output_bytes,
        )
    except Exception as exc:
        error_bytes = str(exc).encode("utf-8", errors="replace")
        stdout_path.write_bytes(b"")
        stderr_path.write_bytes(error_bytes)
        finished = state.execs.finish(
            record.id,
            status="failed",
            exit_code=1,
        )
        return ExecResponse(
            id=finished.id,
            session_id=finished.session_id,
            command=finished.command,
            cwd=finished.cwd,
            status=finished.status,
            exit_code=finished.exit_code,
            started_at=finished.started_at,
            finished_at=finished.finished_at,
            timeout_seconds=finished.timeout_seconds,
        )
    stdout_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)
    status_name = "timed_out" if result.timed_out else (
        "completed" if result.exit_code == 0 else "failed"
    )
    finished = state.execs.finish(
        record.id,
        status=status_name,
        exit_code=result.exit_code,
    )
    return ExecResponse(
        id=finished.id,
        session_id=finished.session_id,
        command=finished.command,
        cwd=finished.cwd,
        status=finished.status,
        exit_code=finished.exit_code,
        started_at=finished.started_at,
        finished_at=finished.finished_at,
        timeout_seconds=finished.timeout_seconds,
    )


@router.get("/v1/sessions/{session_id}/execs/{exec_id}", response_model=ExecResponse)
async def get_exec(
    session_id: str,
    exec_id: str,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
) -> ExecResponse:
    try:
        record = state.execs.get(exec_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="exec_not_found") from None
    if record.session_id != session_id:
        raise HTTPException(status_code=404, detail="exec_not_found")
    return ExecResponse(
        id=record.id,
        session_id=record.session_id,
        command=record.command,
        cwd=record.cwd,
        status=record.status,
        exit_code=record.exit_code,
        started_at=record.started_at,
        finished_at=record.finished_at,
        timeout_seconds=record.timeout_seconds,
    )


def _read_log(path: str | None, offset: int) -> bytes:
    if not path:
        return b""
    file_path = Path(path)
    if not file_path.exists():
        return b""
    data = file_path.read_bytes()
    if offset >= len(data):
        return b""
    return data[offset:]


@router.get("/v1/sessions/{session_id}/execs/{exec_id}/stdout")
async def get_exec_stdout(
    session_id: str,
    exec_id: str,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
    offset: int = 0,
) -> Response:
    try:
        record = state.execs.get(exec_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="exec_not_found") from None
    if record.session_id != session_id:
        raise HTTPException(status_code=404, detail="exec_not_found")
    content = _read_log(record.stdout_path, offset)
    return Response(content=content, media_type="application/octet-stream")


@router.get("/v1/sessions/{session_id}/execs/{exec_id}/stderr")
async def get_exec_stderr(
    session_id: str,
    exec_id: str,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
    offset: int = 0,
) -> Response:
    record = state.execs.get(exec_id)
    if record.session_id != session_id:
        raise HTTPException(status_code=404, detail="exec_not_found")
    content = _read_log(record.stderr_path, offset)
    return Response(content=content, media_type="application/octet-stream")


@router.put("/v1/sessions/{session_id}/files", response_model=FileInfo)
async def write_session_file(
    session_id: str,
    body: WriteFileRequest,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
) -> FileInfo:
    session = _get_active_session(state, session_id)
    try:
        target = resolve_host_path(session.root_path, body.path)
        content = base64.b64decode(body.content_base64)
        mode = int(body.mode, 8)
        write_file(target, content, mode=mode)
        digest = sha256_file(target)
        updated_at = datetime.fromtimestamp(target.stat().st_mtime, UTC)
        state.files.upsert(
            session_id=session_id,
            path=body.path.lstrip("/"),
            size_bytes=len(content),
            sha256=digest,
        )
        return FileInfo(
            path=body.path,
            size_bytes=len(content),
            sha256=digest,
            updated_at=updated_at,
        )
    except PathEscapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/v1/sessions/{session_id}/files")
async def read_session_file(
    session_id: str,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
    path: str,
) -> Response:
    session = _get_active_session(state, session_id)
    try:
        target = resolve_host_path(session.root_path, path)
    except PathEscapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="file_not_found")
    return FileResponse(target)


@router.get("/v1/sessions/{session_id}/files/list", response_model=list[FileListEntry])
async def list_session_files(
    session_id: str,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
    path: str = "",
) -> list[FileListEntry]:
    session = _get_active_session(state, session_id)
    entries = list_workspace_entries(session.root_path, prefix=path)
    return [
        FileListEntry(
            path=entry.path,
            is_dir=entry.is_dir,
            size_bytes=entry.size,
            updated_at=entry.updated_at,
        )
        for entry in entries
    ]


@router.delete("/v1/sessions/{session_id}/files", status_code=204)
async def delete_session_file(
    session_id: str,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
    path: str,
) -> Response:
    session = _get_active_session(state, session_id)
    try:
        target = resolve_host_path(session.root_path, path)
    except PathEscapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target.exists():
        raise HTTPException(status_code=404, detail="file_not_found")
    if target.is_dir():
        import shutil

        shutil.rmtree(target)
    else:
        target.unlink()
    state.files.delete(session_id, path.lstrip("/"))
    return Response(status_code=204)


@router.post("/v1/sessions/{session_id}/files/archive")
async def upload_archive(
    request: Request,
    session_id: str,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
    path: str = "/workspace",
    format: str = "tar",
) -> dict[str, int]:
    session = _get_active_session(state, session_id)
    content = await request.body()
    try:
        target_dir = resolve_host_path(session.root_path, path)
    except PathEscapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    target_dir.mkdir(parents=True, exist_ok=True)
    extracted = 0
    if format == "zip":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for member in archive.namelist():
                if member.endswith("/"):
                    continue
                dest = resolve_host_path(session.root_path, f"{path.rstrip('/')}/{member}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.read(member))
                extracted += 1
    else:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                dest = resolve_host_path(
                    session.root_path, f"{path.rstrip('/')}/{member.name}"
                )
                dest.parent.mkdir(parents=True, exist_ok=True)
                extracted_file = archive.extractfile(member)
                if extracted_file is not None:
                    dest.write_bytes(extracted_file.read())
                    extracted += 1
    return {"extracted": extracted}


@router.get("/v1/sessions/{session_id}/files/archive")
async def download_archive(
    session_id: str,
    state: Annotated[AppState, Depends(get_state)],
    _: AuthDep,
    path: str = "/workspace",
    format: str = "tar",
) -> StreamingResponse:
    session = _get_active_session(state, session_id)
    try:
        target_dir = resolve_host_path(session.root_path, path)
    except PathEscapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not target_dir.exists():
        raise HTTPException(status_code=404, detail="path_not_found")

    buffer = io.BytesIO()
    if format == "zip":
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for file_path in sorted(target_dir.rglob("*")):
                if file_path.is_file():
                    archive.write(
                        file_path,
                        arcname=file_path.relative_to(target_dir).as_posix(),
                    )
        media_type = "application/zip"
        filename = "archive.zip"
    else:
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for file_path in sorted(target_dir.rglob("*")):
                if file_path.is_file():
                    archive.add(
                        file_path,
                        arcname=file_path.relative_to(target_dir).as_posix(),
                    )
        media_type = "application/gzip"
        filename = "archive.tar.gz"
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/v1/sessions/{session_id}/artifacts/sync", response_model=list[ArtifactInfo])
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
