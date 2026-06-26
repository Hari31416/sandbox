from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sandbox_service.artifacts import ArtifactExporter
from sandbox_service.cleanup import CleanupLoop
from sandbox_service.config import Settings
from sandbox_service.repositories import (
    ArtifactRepository,
    ExecRepository,
    FileMetadataRepository,
    SessionRepository,
)
from sandbox_service.runtime import SandboxRuntime, build_runtime_registry


@dataclass
class AppState:
    settings: Settings
    sessions: SessionRepository
    execs: ExecRepository
    files: FileMetadataRepository
    artifacts: ArtifactRepository
    artifact_exporter: ArtifactExporter
    runtimes: dict[str, SandboxRuntime]
    cleanup: CleanupLoop


def build_app_state(settings: Settings) -> AppState:
    db_path = settings.resolved_sqlite_path
    scratch_root = settings.resolved_scratch_root
    artifacts_root = settings.resolved_artifacts_root
    exec_logs_root = settings.resolved_exec_logs_root
    scratch_root.mkdir(parents=True, exist_ok=True)
    artifacts_root.mkdir(parents=True, exist_ok=True)
    exec_logs_root.mkdir(parents=True, exist_ok=True)

    sessions = SessionRepository(db_path)
    execs = ExecRepository(db_path)
    files = FileMetadataRepository(db_path)
    artifacts = ArtifactRepository(db_path)
    runtimes = build_runtime_registry(settings)
    cleanup = CleanupLoop(
        sessions=sessions,
        scratch_root=scratch_root,
        exec_logs_root=exec_logs_root,
        runtimes=runtimes,
        ttl_seconds=settings.session_ttl_seconds,
        interval_seconds=settings.cleanup_interval_seconds,
    )
    return AppState(
        settings=settings,
        sessions=sessions,
        execs=execs,
        files=files,
        artifacts=artifacts,
        artifact_exporter=ArtifactExporter(
            artifacts_root=artifacts_root,
            repository=artifacts,
        ),
        runtimes=runtimes,
        cleanup=cleanup,
    )
