from __future__ import annotations

from pathlib import Path

from sandbox_service.config import Settings
from sandbox_service.runtime.base import SandboxRuntime
from sandbox_service.runtime.local import LocalRuntime
from sandbox_service.runtime.microsandbox import MicrosandboxRuntime


def build_runtime_registry(settings: Settings) -> dict[str, SandboxRuntime]:
    scratch_root = settings.resolved_scratch_root
    guest_workspace = settings.guest_workspace_path
    return {
        "local": LocalRuntime(
            scratch_root=scratch_root,
            guest_workspace_path=guest_workspace,
        ),
        "microsandbox": MicrosandboxRuntime(
            scratch_root=scratch_root,
            guest_workspace_path=guest_workspace,
        ),
    }


def get_runtime(registry: dict[str, SandboxRuntime], backend: str) -> SandboxRuntime:
    runtime = registry.get(backend)
    if runtime is None:
        raise ValueError(f"Unknown backend: {backend}")
    if not runtime.is_available():
        raise RuntimeError(f"Backend '{backend}' is not available")
    return runtime
