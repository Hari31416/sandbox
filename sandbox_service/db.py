from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS sandbox_sessions (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    run_id TEXT,
    image TEXT NOT NULL,
    status TEXT NOT NULL,
    backend TEXT NOT NULL,
    root_path TEXT NOT NULL,
    sandbox_name TEXT,
    limits_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_heartbeat_at TEXT,
    stopped_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_workspace ON sandbox_sessions(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sessions_run ON sandbox_sessions(run_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sandbox_sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sandbox_sessions(expires_at);

CREATE TABLE IF NOT EXISTS execs (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    command TEXT NOT NULL,
    cwd TEXT NOT NULL,
    status TEXT NOT NULL,
    exit_code INTEGER,
    stdout_path TEXT,
    stderr_path TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    timeout_seconds INTEGER NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sandbox_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_execs_session ON execs(session_id);

CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(session_id, path),
    FOREIGN KEY(session_id) REFERENCES sandbox_sessions(id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    artifact_uri TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sandbox_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id);

CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    source_session_id TEXT,
    name TEXT NOT NULL,
    msb_name TEXT NOT NULL,
    digest TEXT NOT NULL,
    image_ref TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(workspace_id, name)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_workspace ON snapshots(workspace_id);
"""


def init_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
