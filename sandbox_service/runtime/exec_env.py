"""Default environment for sandboxed command execution.

Headless data-science scripts (matplotlib/seaborn) hang without a non-GUI
backend. Closing stdin prevents tools that probe TTY/input from blocking.
"""

from __future__ import annotations

from pathlib import Path

# Guest-side defaults for microsandbox VMs (paths are inside the guest).
GUEST_DEFAULT_EXEC_ENV: dict[str, str] = {
    "PYTHONUNBUFFERED": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
    "MPLBACKEND": "Agg",
    "MPLCONFIGDIR": "/tmp/mplconfig",
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}


def merge_exec_env(
    extra: dict[str, str] | None,
    *,
    defaults: dict[str, str] | None = None,
) -> dict[str, str]:
    """Merge caller env over defaults. Caller values always win."""
    merged = dict(defaults or GUEST_DEFAULT_EXEC_ENV)
    if extra:
        merged.update({key: value for key, value in extra.items() if key})
    return merged


def local_default_exec_env(workdir: Path) -> dict[str, str]:
    """Host-side defaults for the local backend (paths under the scratch dir)."""
    mplconfig = workdir / ".mplconfig"
    mplconfig.mkdir(parents=True, exist_ok=True)
    return {
        **GUEST_DEFAULT_EXEC_ENV,
        "MPLCONFIGDIR": str(mplconfig),
    }
