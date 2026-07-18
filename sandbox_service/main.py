from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sandbox_service.api.routes import router
from sandbox_service.app_state import AppState, build_app_state
from sandbox_service.config import Settings, get_settings
from sandbox_service.db import init_database
from sandbox_service.secure_defaults import (
    is_secure_profile,
    validate_sandbox_secure_defaults,
)

logger = logging.getLogger(__name__)


def enforce_sandbox_secure_defaults(settings: Settings) -> None:
    validate_sandbox_secure_defaults(
        deploy_profile=settings.deploy_profile,
        auth_token=settings.auth_token,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    enforce_sandbox_secure_defaults(settings)
    init_database(settings.resolved_sqlite_path)
    state = build_app_state(settings)
    app.state.sandbox = state
    await state.cleanup.start()
    logger.info(
        "sandbox service started profile=%s host=%s port=%s data_dir=%s default_backend=%s",
        settings.deploy_profile,
        settings.host,
        settings.port,
        settings.data_dir,
        settings.default_backend,
    )
    try:
        yield
    finally:
        await state.cleanup.stop()
        logger.info("sandbox service stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Nexus Sandbox Service", version="0.1.0", lifespan=lifespan)
    # Sandbox is not a browser-facing control plane in staging/prod.
    # Local/demo keep a localhost allowlist for ad-hoc tooling; secure profiles
    # omit wildcard CORS entirely.
    if is_secure_profile(settings.deploy_profile):
        cors_origins: list[str] = []
    else:
        cors_origins = [
            "http://127.0.0.1:5174",
            "http://localhost:5174",
            "http://127.0.0.1:8881",
            "http://localhost:8881",
        ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uvicorn.run(
        "sandbox_service.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
