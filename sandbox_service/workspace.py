from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from mimetypes import guess_type
from pathlib import Path


@dataclass(frozen=True)
class WorkspaceFileRecord:
    path: str
    size: int
    is_dir: bool
    updated_at: datetime


def ensure_workspace(scratch_root: str | Path, session_id: str) -> Path:
    workspace = Path(scratch_root) / session_id / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def remove_workspace(scratch_root: str | Path, session_id: str) -> None:
    root = Path(scratch_root) / session_id
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            path.rmdir()
    root.rmdir()


def list_workspace_entries(
    workspace_path: str | Path, *, prefix: str = ""
) -> list[WorkspaceFileRecord]:
    root = Path(workspace_path)
    if not root.exists():
        return []

    normalized_prefix = prefix.strip().lstrip("/")
    search_root = root / normalized_prefix if normalized_prefix else root
    if not search_root.exists():
        return []

    entries: list[WorkspaceFileRecord] = []
    for path in sorted(search_root.rglob("*")):
        stat_result = path.stat()
        relative = path.relative_to(root).as_posix()
        entries.append(
            WorkspaceFileRecord(
                path=relative,
                size=stat_result.st_size if path.is_file() else 0,
                is_dir=path.is_dir(),
                updated_at=datetime.fromtimestamp(stat_result.st_mtime, UTC),
            )
        )
    return entries


def guess_content_type(path: str) -> str | None:
    return guess_type(path)[0]
