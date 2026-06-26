from __future__ import annotations

import fnmatch
import shutil
from pathlib import Path, PurePosixPath

from sandbox_service.path_guard import resolve_host_path, sha256_file
from sandbox_service.repositories import ArtifactRecord, ArtifactRepository


class ArtifactExporter:
    def __init__(self, *, artifacts_root: Path, repository: ArtifactRepository) -> None:
        self._artifacts_root = artifacts_root
        self._repository = repository

    def sync(
        self,
        *,
        session_id: str,
        root_path: str,
        paths: list[str],
        destination_prefix: str,
        include_globs: list[str],
        exclude_globs: list[str],
    ) -> list[ArtifactRecord]:
        created: list[ArtifactRecord] = []
        for source_path in paths:
            host_path = resolve_host_path(root_path, source_path)
            if not host_path.exists():
                continue
            if host_path.is_file():
                record = self._export_file(
                    session_id=session_id,
                    source_path=source_path,
                    host_path=host_path,
                    destination_prefix=destination_prefix,
                )
                created.append(record)
                continue
            for file_path in sorted(host_path.rglob("*")):
                if not file_path.is_file():
                    continue
                relative = file_path.relative_to(Path(root_path)).as_posix()
                if not _matches_globs(relative, include_globs, exclude_globs):
                    continue
                record = self._export_file(
                    session_id=session_id,
                    source_path=relative,
                    host_path=file_path,
                    destination_prefix=destination_prefix,
                )
                created.append(record)
        return created

    def _export_file(
        self,
        *,
        session_id: str,
        source_path: str,
        host_path: Path,
        destination_prefix: str,
    ) -> ArtifactRecord:
        digest = sha256_file(host_path)
        relative_name = source_path.lstrip("/").replace("/", "_")
        destination_dir = self._artifacts_root / session_id / destination_prefix.strip("/")
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / relative_name
        shutil.copy2(host_path, destination)
        artifact_uri = f"file://{destination.resolve()}"
        return self._repository.create(
            session_id=session_id,
            source_path=source_path,
            artifact_uri=artifact_uri,
            size_bytes=destination.stat().st_size,
            sha256=digest,
        )


def _matches_globs(
    path: str, include_globs: list[str], exclude_globs: list[str]
) -> bool:
    included = any(_path_matches(path, pattern) for pattern in include_globs)
    if not included:
        return False
    return not any(_path_matches(path, pattern) for pattern in exclude_globs)


def _path_matches(path: str, pattern: str) -> bool:
    posix_path = PurePosixPath(path)
    if posix_path.match(pattern):
        return True
    if fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(posix_path.name, pattern):
        return True
    # "**/*" should include workspace-root files, not only nested paths.
    if pattern in {"**/*", "**/**"} and "/" not in path:
        return True
    return False
