"""Unit tests for microsandbox create config limits wiring."""

from __future__ import annotations

from pathlib import Path

from sandbox_service.models import SessionLimits
from sandbox_service.runtime.microsandbox import MicrosandboxRuntime


def test_build_create_config_applies_disk_and_timeout() -> None:
    runtime = MicrosandboxRuntime(
        scratch_root=Path("/tmp"),
        guest_workspace_path="/workspace",
    )
    limits = SessionLimits(
        cpu=2,
        memory_mb=2048,
        disk_mb=4096,
        timeout_seconds=900,
        network="disabled",
    )
    config = runtime._build_create_config(
        sandbox_name="sb_test",
        image="python:3.12",
        root_path="/tmp/ws",
        limits=limits,
        snapshot=None,
    )
    assert config["cpus"] == 2
    assert config["memoryMib"] == 2048
    assert config["maxDurationSecs"] == 900
    image = config["image"]
    # Must not be a bare string — Image.oci carries upper_size_mib.
    assert image != "python:3.12"
    assert getattr(image, "_upper_size_mib", None) == 4096
    assert getattr(image, "_reference", None) == "python:3.12"


def test_build_create_config_snapshot_skips_image_disk() -> None:
    runtime = MicrosandboxRuntime(
        scratch_root=Path("/tmp"),
        guest_workspace_path="/workspace",
    )
    config = runtime._build_create_config(
        sandbox_name="sb_snap",
        image="python:3.12",
        root_path="/tmp/ws",
        limits=SessionLimits(disk_mb=4096, timeout_seconds=120),
        snapshot="snap_abc",
    )
    assert config["snapshot"] == "snap_abc"
    assert "image" not in config
    assert config["maxDurationSecs"] == 120
