# Nexus Sandbox

Standalone compute-plane service for isolated code execution: session lifecycle, command runs, workspace files, artifact export, and microVM snapshots. Includes a **Sandbox Console** web UI for local development and testing.

## Features

- **Sessions** — create, stop, heartbeat, and TTL-based cleanup
- **Execution** — run shell commands with timeouts and captured stdout/stderr
- **Filesystem** — read, write, list, upload/download archives under `/workspace`
- **Artifacts** — sync workspace paths to a local artifact store
- **Snapshots** (microsandbox) — save VM disk state, optionally bundle workspace files to resume later
- **Backends** — `local` (subprocess + host dirs) or `microsandbox` (hardware-isolated microVMs via `msb`)

## Stack

| Layer    | Tech                                                                              |
| -------- | --------------------------------------------------------------------------------- |
| API      | FastAPI, Pydantic v2, SQLite                                                      |
| Runtimes | Local subprocess, [microsandbox](https://github.com/superradcompany/microsandbox) |
| UI       | React, Vite, Tailwind, shadcn/ui, TanStack Query                                  |
| Tooling  | uv, pnpm, just                                                                    |

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — `just install-uv`
- [pnpm](https://pnpm.io/) — `just install-pnpm`
- [just](https://github.com/casey/just) (recommended)
- **microsandbox** (optional) — install `msb` for microVM sessions and snapshots

## Quick start

```bash
just setup    # uv sync + pnpm install
just start    # backend :8787 + frontend :5173
just health   # verify both services
```

Open **http://127.0.0.1:5173** for the Sandbox Console.

```bash
just stop           # stop both
just logs-backend   # tail API logs
just logs-frontend  # tail UI logs
```

### Backend only

```bash
uv sync --extra dev
uv run sandbox-service
# or
uv run uvicorn sandbox_service.main:app --host 127.0.0.1 --port 8787
```

### Frontend only

```bash
cd frontend && pnpm install && pnpm dev
```

## Configuration

All settings use the `SANDBOX_` prefix (see `sandbox_service/config.py`).

| Variable                        | Default              | Description                         |
| ------------------------------- | -------------------- | ----------------------------------- |
| `SANDBOX_DEFAULT_BACKEND`       | `local`              | `local` or `microsandbox`           |
| `SANDBOX_DEFAULT_IMAGE`         | `python:3.12`        | OCI image for new sessions          |
| `SANDBOX_DATA_DIR`              | `~/.nexus-sandbox`   | Root for SQLite, scratch, artifacts |
| `SANDBOX_HOST` / `SANDBOX_PORT` | `127.0.0.1` / `8787` | API bind address                    |
| `SANDBOX_AUTH_TOKEN`            | _(none)_             | Optional bearer token for API auth  |

### Data layout

```
~/.nexus-sandbox/
├── sandbox.db              # session/snapshot metadata
├── scratch/<session_id>/workspace/   # live workspace files
├── artifacts/              # exported artifacts
└── snapshot-workspaces/    # workspace tarballs (when include_workspace=true)
```

microsandbox VM disk snapshots are stored separately under `~/.microsandbox/snapshots/`.

## Snapshots

With the **microsandbox** backend you can snapshot a stopped session:

- **VM disk** — captured by microsandbox (`Snapshot.create`)
- **Workspace files** (optional) — archived to `snapshot-workspaces/` when `include_workspace: true`

Restore by creating a new session with `snapshot_id`. Workspace files are extracted automatically when the snapshot includes them.

## Development

```bash
uv run pytest              # backend tests
cd frontend && pnpm build  # production UI build
```

## Project layout

```
sandbox_service/   # FastAPI app, runtimes, SQLite repos
sandbox/           # HttpSandboxBackend adapter for Nexus workers
frontend/          # Sandbox Console UI
tests/             # API and snapshot tests
justfile           # local orchestration
```

## API reference

See [`sandbox_service_plan.md`](sandbox_service_plan.md) for the full HTTP contract and architecture notes.

Health checks: `GET /healthz`, `GET /readyz`, `GET /v1/backends`
