from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sandbox_service.repositories import SessionRepository
from sandbox_service.runtime import SandboxRuntime
from sandbox_service.workspace import remove_workspace


logger = logging.getLogger(__name__)


class CleanupLoop:
    def __init__(
        self,
        *,
        sessions: SessionRepository,
        scratch_root: Path,
        exec_logs_root: Path,
        runtimes: dict[str, SandboxRuntime],
        ttl_seconds: int,
        interval_seconds: int,
        exec_log_retention_seconds: int = 7 * 24 * 3600,
    ) -> None:
        self._sessions = sessions
        self._scratch_root = scratch_root
        self._exec_logs_root = exec_logs_root
        self._runtimes = runtimes
        self._ttl_seconds = ttl_seconds
        self._interval_seconds = interval_seconds
        self._exec_log_retention_seconds = exec_log_retention_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self.run_once()
        self._task = asyncio.create_task(self._run(), name="sandbox-cleanup")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def run_once(self) -> tuple[int, int]:
        sessions_removed = await self._cleanup_expired_sessions()
        exec_logs_removed = self._cleanup_exec_logs()
        await self._reconcile_orphans()
        return sessions_removed, exec_logs_removed

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval_seconds)
            try:
                await self.run_once()
            except Exception:
                logger.exception("sandbox cleanup iteration failed")

    async def _cleanup_expired_sessions(self) -> int:
        removed = 0
        for session in self._sessions.list_expired():
            try:
                # _stop_and_remove deletes the DB row; do not update_status afterward.
                await self._stop_and_remove(
                    session.id, session.backend, session.sandbox_name
                )
                removed += 1
            except Exception:
                logger.exception(
                    "failed to clean up expired sandbox session %s", session.id
                )
        return removed

    def _cleanup_exec_logs(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=self._exec_log_retention_seconds)
        removed = 0
        if not self._exec_logs_root.exists():
            return 0
        for path in self._exec_logs_root.rglob("*"):
            if not path.is_file():
                continue
            mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            if mtime < cutoff:
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    async def _reconcile_orphans(self) -> None:
        leases = self._sessions.list_sessions(status="active")
        known_names = {lease.sandbox_name for lease in leases if lease.sandbox_name}
        for runtime in self._runtimes.values():
            try:
                sandbox_names = await runtime.list_sandboxes()
            except Exception:
                logger.exception(
                    "failed to list sandboxes for runtime %s", runtime.name
                )
                continue
            for sandbox_name in sandbox_names:
                if sandbox_name not in known_names:
                    try:
                        await runtime.delete_session(sandbox_name=sandbox_name)
                    except Exception:
                        logger.exception(
                            "failed to delete orphan sandbox %s", sandbox_name
                        )

        known_ids = {lease.id for lease in leases}
        if self._scratch_root.exists():
            for session_root in self._scratch_root.iterdir():
                if session_root.is_dir() and session_root.name not in known_ids:
                    remove_workspace(self._scratch_root, session_root.name)

    async def _stop_and_remove(
        self, session_id: str, backend: str, sandbox_name: str | None
    ) -> None:
        runtime = self._runtimes.get(backend)
        if runtime is not None and sandbox_name:
            with suppress(Exception):
                await runtime.stop_session(sandbox_name=sandbox_name)
            with suppress(Exception):
                await runtime.delete_session(sandbox_name=sandbox_name)
        remove_workspace(self._scratch_root, session_id)
        self._sessions.delete(session_id)
