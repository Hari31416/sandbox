from __future__ import annotations

import tarfile
from pathlib import Path


def workspace_archive_path(snapshots_root: Path, snapshot_id: str) -> Path:
    return snapshots_root / snapshot_id / "workspace.tar.gz"


def archive_workspace(*, workspace_path: Path, destination: Path) -> int:
    workspace = workspace_path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()

    with tarfile.open(destination, mode="w:gz") as archive:
        if workspace.exists():
            for file_path in sorted(workspace.rglob("*")):
                if file_path.is_file():
                    archive.add(
                        file_path,
                        arcname=file_path.relative_to(workspace).as_posix(),
                    )
    return destination.stat().st_size if destination.exists() else 0


def restore_workspace(*, archive_path: Path, workspace_path: Path) -> None:
    if not archive_path.exists():
        return

    workspace = workspace_path.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                continue
            dest = (workspace / member.name).resolve()
            try:
                dest.relative_to(workspace)
            except ValueError:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is not None:
                dest.write_bytes(extracted.read())


def remove_workspace_archive(archive_path: Path) -> None:
    if not archive_path.exists():
        return
    archive_path.unlink()
    parent = archive_path.parent
    if parent.exists() and not any(parent.iterdir()):
        parent.rmdir()
