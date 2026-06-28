from __future__ import annotations

import base64

from sandbox_service.path_guard import (
    rewrite_guest_path,
    rewrite_guest_workspace_command,
)


def test_rewrite_guest_path_maps_workspace_root() -> None:
    assert rewrite_guest_path("/workspace") == "."
    assert rewrite_guest_path("/workspace/input.csv") == "input.csv"


def test_rewrite_guest_workspace_command_rewrites_literal_paths() -> None:
    command = "python3 /workspace/csv_profile.py /workspace/input.csv"
    assert rewrite_guest_workspace_command(command) == (
        "python3 csv_profile.py input.csv"
    )


def test_rewrite_guest_workspace_command_rewrites_deepagents_b64_paths() -> None:
    workspace_b64 = base64.b64encode(b"/workspace").decode("ascii")
    command = (
        "python3 -c \"\n"
        f"path = base64.b64decode('{workspace_b64}').decode('utf-8')\n"
        "print(path)\n"
        "\""
    )
    rewritten = rewrite_guest_workspace_command(command)
    dot_b64 = base64.b64encode(b".").decode("ascii")
    assert f"base64.b64decode('{dot_b64}')" in rewritten
