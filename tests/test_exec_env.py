from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sandbox_service.runtime.exec_env import (
    GUEST_DEFAULT_EXEC_ENV,
    local_default_exec_env,
    merge_exec_env,
)
from sandbox_service.runtime.local import _isolated_exec_env
from sandbox_service.runtime.microsandbox import _exec_event_kind


def test_guest_defaults_force_headless_matplotlib() -> None:
    assert GUEST_DEFAULT_EXEC_ENV["MPLBACKEND"] == "Agg"
    assert GUEST_DEFAULT_EXEC_ENV["PYTHONUNBUFFERED"] == "1"


def test_merge_exec_env_caller_overrides_defaults() -> None:
    merged = merge_exec_env({"MPLBACKEND": "TkAgg", "CUSTOM": "1"})
    assert merged["MPLBACKEND"] == "TkAgg"
    assert merged["CUSTOM"] == "1"
    assert merged["PYTHONUNBUFFERED"] == "1"


def test_local_default_exec_env_creates_mplconfig(tmp_path: Path) -> None:
    env = local_default_exec_env(tmp_path)
    assert env["MPLBACKEND"] == "Agg"
    assert Path(env["MPLCONFIGDIR"]).is_dir()
    assert Path(env["MPLCONFIGDIR"]).parent == tmp_path


def test_isolated_exec_env_includes_agg_backend(tmp_path: Path) -> None:
    env = _isolated_exec_env(tmp_path, {})
    assert env["MPLBACKEND"] == "Agg"
    assert env["HOME"] == str(tmp_path)


def test_exec_event_kind_exited_is_terminal() -> None:
    event = SimpleNamespace(event_type="exited", code=0)
    assert _exec_event_kind(event) == "exited"
