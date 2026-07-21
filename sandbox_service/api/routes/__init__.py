from __future__ import annotations

"""Sandbox API route package — domain modules register on the shared router."""

from sandbox_service.api.routes._shared import (  # noqa: F401
    AuthDep,
    get_state,
    require_auth,
    resolve_session_ttl_seconds,
    router,
)

# Import domain modules for side-effect route registration (order preserved).
from sandbox_service.api.routes import health as _health  # noqa: F401, E402
from sandbox_service.api.routes import sessions as _sessions  # noqa: F401, E402
from sandbox_service.api.routes import snapshots as _snapshots  # noqa: F401, E402
from sandbox_service.api.routes import execs as _execs  # noqa: F401, E402
from sandbox_service.api.routes import files as _files  # noqa: F401, E402
from sandbox_service.api.routes import artifacts as _artifacts  # noqa: F401, E402

__all__ = [
    "AuthDep",
    "get_state",
    "require_auth",
    "resolve_session_ttl_seconds",
    "router",
]
