from __future__ import annotations

import base64
import io
import tarfile
import zipfile
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse

from sandbox_service.app_state import AppState
from sandbox_service.models import FileInfo, FileListEntry, WriteFileRequest
from sandbox_service.path_guard import (
    PathEscapeError,
    resolve_host_path,
    sha256_file,
    write_file,
)
from sandbox_service.workspace import list_workspace_entries

from ._shared import AuthDep, _get_active_session, get_state, router


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
                dest = resolve_host_path(
                    session.root_path, f"{path.rstrip('/')}/{member}"
                )
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
