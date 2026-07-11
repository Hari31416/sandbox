from __future__ import annotations

import base64
from typing import Any, Protocol

import httpx

from sandbox_service.models import (
    CreateSessionRequest,
    ExecRequest,
    SessionLimits,
    SyncArtifactsRequest,
    WriteFileRequest,
)


class SandboxBackend(Protocol):
    async def create_session(
        self,
        workspace_id: str,
        image: str,
        limits: dict[str, Any] | SessionLimits,
        *,
        run_id: str | None = None,
        backend: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def exec(
        self,
        session_id: str,
        command: str,
        timeout: int,
        *,
        cwd: str = "/workspace",
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]: ...

    async def write_file(self, session_id: str, path: str, content: bytes) -> dict[str, Any]: ...

    async def read_file(self, session_id: str, path: str) -> bytes: ...

    async def sync_to_artifacts(
        self,
        session_id: str,
        paths: list[str],
        destination_prefix: str,
    ) -> list[dict[str, Any]]: ...

    async def stop_session(self, session_id: str) -> dict[str, Any]: ...


class HttpSandboxBackend:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8787",
        *,
        auth_token: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        headers: dict[str, str] = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> HttpSandboxBackend:
        return self

    async def __aexit__(self, *args) -> None:
        await self.aclose()

    async def create_session(
        self,
        workspace_id: str,
        image: str,
        limits: dict[str, Any] | SessionLimits,
        *,
        run_id: str | None = None,
        backend: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = CreateSessionRequest(
            workspace_id=workspace_id,
            run_id=run_id,
            image=image,
            backend=backend,
            limits=(
                limits
                if isinstance(limits, SessionLimits)
                else SessionLimits.model_validate(limits)
            ),
            metadata=metadata or {},
        )
        response = await self._client.post("/v1/sessions", json=payload.model_dump())
        response.raise_for_status()
        return response.json()

    async def get_session(self, session_id: str) -> dict[str, Any]:
        response = await self._client.get(f"/v1/sessions/{session_id}")
        response.raise_for_status()
        return response.json()

    async def exec(
        self,
        session_id: str,
        command: str,
        timeout: int,
        *,
        cwd: str = "/workspace",
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        payload = ExecRequest(
            command=command,
            cwd=cwd,
            timeout_seconds=timeout,
            env=env or {},
        )
        # Allow the HTTP call to outlive the command timeout with a small buffer.
        exec_timeout = float(timeout) + 30.0
        response = await self._client.post(
            f"/v1/sessions/{session_id}/execs",
            json=payload.model_dump(),
            timeout=exec_timeout,
        )
        response.raise_for_status()
        return response.json()

    async def write_file(self, session_id: str, path: str, content: bytes) -> dict[str, Any]:
        payload = WriteFileRequest(
            path=path,
            content_base64=base64.b64encode(content).decode("ascii"),
        )
        response = await self._client.put(
            f"/v1/sessions/{session_id}/files",
            json=payload.model_dump(),
        )
        response.raise_for_status()
        return response.json()

    async def read_file(self, session_id: str, path: str) -> bytes:
        response = await self._client.get(
            f"/v1/sessions/{session_id}/files",
            params={"path": path},
        )
        response.raise_for_status()
        return response.content

    async def sync_to_artifacts(
        self,
        session_id: str,
        paths: list[str],
        destination_prefix: str,
    ) -> list[dict[str, Any]]:
        payload = SyncArtifactsRequest(
            paths=paths,
            destination_prefix=destination_prefix,
        )
        response = await self._client.post(
            f"/v1/sessions/{session_id}/artifacts/sync",
            json=payload.model_dump(),
        )
        response.raise_for_status()
        return response.json()

    async def stop_session(self, session_id: str) -> dict[str, Any]:
        response = await self._client.post(f"/v1/sessions/{session_id}/stop")
        response.raise_for_status()
        return response.json()

    async def delete_session(self, session_id: str) -> None:
        response = await self._client.delete(f"/v1/sessions/{session_id}")
        response.raise_for_status()

    async def heartbeat(self, session_id: str, extend_seconds: int | None = None) -> dict[str, Any]:
        payload = {"extend_seconds": extend_seconds} if extend_seconds else {}
        response = await self._client.post(
            f"/v1/sessions/{session_id}/heartbeat",
            json=payload,
        )
        response.raise_for_status()
        return response.json()
