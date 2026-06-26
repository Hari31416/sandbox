from __future__ import annotations

from pathlib import Path

from sandbox_service.snapshot_workspace import (
    archive_workspace,
    remove_workspace_archive,
    restore_workspace,
    workspace_archive_path,
)


def test_archive_and_restore_workspace_round_trip(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "main.py").write_text("print('ok')\n")
    nested = workspace / "pkg"
    nested.mkdir()
    (nested / "util.py").write_text("VALUE = 1\n")

    archive = workspace_archive_path(tmp_path / "snapshots", "snap_test")
    size = archive_workspace(workspace_path=workspace, destination=archive)
    assert size > 0
    assert archive.exists()

    restored = tmp_path / "restored"
    restore_workspace(archive_path=archive, workspace_path=restored)
    assert (restored / "main.py").read_text() == "print('ok')\n"
    assert (restored / "pkg" / "util.py").read_text() == "VALUE = 1\n"


def test_remove_workspace_archive_cleans_up(tmp_path: Path) -> None:
    archive = workspace_archive_path(tmp_path / "snapshots", "snap_delete")
    archive_workspace(workspace_path=tmp_path / "workspace", destination=archive)
    remove_workspace_archive(archive)
    assert not archive.exists()
    assert not archive.parent.exists()
