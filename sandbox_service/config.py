from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SANDBOX_",
        env_file=".env",
        extra="ignore",
    )

    host: str = "127.0.0.1"
    port: int = 8787
    auth_token: str | None = None

    data_dir: Path = Field(default_factory=lambda: Path.home() / ".nexus-sandbox")
    sqlite_path: Path | None = None
    scratch_root: Path | None = None
    artifacts_root: Path | None = None
    exec_logs_root: Path | None = None

    default_backend: str = "local"
    default_image: str = "python:3.12"
    guest_workspace_path: str = "/workspace"

    session_ttl_seconds: int = 3600
    heartbeat_extend_seconds: int = 1800
    cleanup_interval_seconds: int = 60
    default_exec_timeout_seconds: int = 300
    max_exec_output_bytes: int = 10 * 1024 * 1024

    @property
    def resolved_sqlite_path(self) -> Path:
        if self.sqlite_path is not None:
            return self.sqlite_path
        return self.data_dir / "sandbox.db"

    @property
    def resolved_scratch_root(self) -> Path:
        if self.scratch_root is not None:
            return self.scratch_root
        return self.data_dir / "scratch"

    @property
    def resolved_artifacts_root(self) -> Path:
        if self.artifacts_root is not None:
            return self.artifacts_root
        return self.data_dir / "artifacts"

    @property
    def resolved_exec_logs_root(self) -> Path:
        if self.exec_logs_root is not None:
            return self.exec_logs_root
        return self.data_dir / "exec-logs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
