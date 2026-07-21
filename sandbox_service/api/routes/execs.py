from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Response

from sandbox_service.app_state import AppState
from sandbox_service.models import ExecRequest, ExecResponse
from sandbox_service.runtime import get_runtime

from ._shared import AuthDep, _get_active_session, get_state, router


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
    status_name = (
        "timed_out"
        if result.timed_out
        else ("completed" if result.exit_code == 0 else "failed")
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
