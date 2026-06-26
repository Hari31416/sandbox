# Nexus Sandbox — service orchestration
#
# Usage:
#   just setup    # install backend + frontend deps
#   just start    # start backend + frontend
#   just stop     # stop both
#   just health   # check both services

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

export BACKEND_PORT := "8787"
export FRONTEND_PORT := "5173"
export SANDBOX_HOST := "0.0.0.0"
export SANDBOX_PORT := BACKEND_PORT
export VITE_BACKEND_PORT := BACKEND_PORT

default:
    @just --list

# ── Top-level ────────────────────────────────────────────────────────────────

setup: backend-setup frontend-setup

start: backend-start frontend-start

stop: backend-stop frontend-stop

restart: stop start

health:
    @echo "Checking services..."
    @just health-backend
    @just health-frontend

# ── Tooling ──────────────────────────────────────────────────────────────────

install-uv:
    @echo "Installing uv..."
    @curl -LsSf https://astral.sh/uv/install.sh | sh
    @echo "uv installed. Restart your shell or run: source ~/.local/bin/env"

install-pnpm:
    @echo "Installing pnpm via corepack..."
    @corepack enable
    @corepack prepare pnpm@latest --activate
    @echo "pnpm $(pnpm --version) ready"

# ── Backend ──────────────────────────────────────────────────────────────────

backend-setup:
    @echo "Setting up backend (uv sync)..."
    @if ! command -v uv >/dev/null 2>&1; then \
        echo "uv not found. Run: just install-uv"; \
        exit 1; \
    fi
    @uv sync --extra dev
    @echo "Backend setup complete."

backend-start:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p .run
    if [[ -f .run/backend.pid ]] && kill -0 "$(cat .run/backend.pid)" 2>/dev/null; then
        echo "Backend is already running (pid $(cat .run/backend.pid))"
        exit 0
    fi
    if [[ ! -x .venv/bin/uvicorn ]]; then
        echo "Backend venv missing; running uv sync..."
        uv sync --extra dev
    fi
    export SANDBOX_HOST="{{SANDBOX_HOST}}"
    export SANDBOX_PORT="{{BACKEND_PORT}}"
    nohup .venv/bin/uvicorn sandbox_service.main:app \
        --host "{{SANDBOX_HOST}}" \
        --port "{{BACKEND_PORT}}" \
        > .run/backend.log 2>&1 < /dev/null &
    printf '%s\n' "$!" > .run/backend.pid
    echo "Started backend (pid $(cat .run/backend.pid))"
    echo "URL:  http://127.0.0.1:{{BACKEND_PORT}}"
    echo "Logs: .run/backend.log"

backend-stop:
    @echo "Stopping backend on port {{BACKEND_PORT}}..."
    @if [[ -f .run/backend.pid ]]; then \
        pid="$(cat .run/backend.pid)"; \
        if kill -0 "$pid" 2>/dev/null; then \
            kill "$pid" 2>/dev/null || true; \
            sleep 0.5; \
            kill -9 "$pid" 2>/dev/null || true; \
        fi; \
    fi
    @lsof -ti :{{BACKEND_PORT}} | xargs kill -9 2>/dev/null || true
    @rm -f .run/backend.pid
    @echo "Backend stopped."

logs-backend:
    @mkdir -p .run
    @touch .run/backend.log
    @tail -f .run/backend.log

health-backend:
    #!/usr/bin/env bash
    if curl -sf "http://127.0.0.1:{{BACKEND_PORT}}/healthz" >/dev/null; then
        ready="$(curl -sf "http://127.0.0.1:{{BACKEND_PORT}}/readyz" 2>/dev/null || echo '{}')"
        echo "Backend: healthy (port {{BACKEND_PORT}}) $ready"
    else
        echo "Backend: down (port {{BACKEND_PORT}})"
        exit 1
    fi

# ── Frontend ─────────────────────────────────────────────────────────────────

frontend-setup:
    @echo "Setting up frontend (pnpm install)..."
    @if ! command -v pnpm >/dev/null 2>&1; then \
        echo "pnpm not found. Run: just install-pnpm"; \
        exit 1; \
    fi
    @cd frontend && pnpm install
    @echo "Frontend setup complete."

frontend-start:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p .run
    if [[ -f .run/frontend.pid ]] && kill -0 "$(cat .run/frontend.pid)" 2>/dev/null; then
        echo "Frontend is already running (pid $(cat .run/frontend.pid))"
        exit 0
    fi
    if [[ ! -d frontend/node_modules ]]; then
        echo "Frontend deps missing; running pnpm install..."
        (cd frontend && pnpm install)
    fi
    (
        cd frontend
        export BACKEND_PORT="{{BACKEND_PORT}}"
        nohup ./node_modules/.bin/vite --host 0.0.0.0 --port "{{FRONTEND_PORT}}" \
            > ../.run/frontend.log 2>&1 < /dev/null &
        printf '%s\n' "$!" > ../.run/frontend.pid
    )
    echo "Started frontend (pid $(cat .run/frontend.pid))"
    echo "URL:  http://127.0.0.1:{{FRONTEND_PORT}}"
    echo "Logs: .run/frontend.log"

frontend-stop:
    @echo "Stopping frontend on port {{FRONTEND_PORT}}..."
    @if [[ -f .run/frontend.pid ]]; then \
        pid="$(cat .run/frontend.pid)"; \
        if kill -0 "$pid" 2>/dev/null; then \
            kill "$pid" 2>/dev/null || true; \
            sleep 0.5; \
            kill -9 "$pid" 2>/dev/null || true; \
        fi; \
    fi
    @lsof -ti :{{FRONTEND_PORT}} | xargs kill -9 2>/dev/null || true
    @rm -f .run/frontend.pid
    @echo "Frontend stopped."

frontend-preview:
    @echo "Building frontend..."
    @cd frontend && pnpm build
    @echo "Starting preview server on port {{FRONTEND_PORT}}..."
    @cd frontend && BACKEND_PORT="{{BACKEND_PORT}}" ./node_modules/.bin/vite preview --host 0.0.0.0 --port "{{FRONTEND_PORT}}"

logs-frontend:
    @mkdir -p .run
    @touch .run/frontend.log
    @tail -f .run/frontend.log

health-frontend:
    #!/usr/bin/env bash
    if curl -sf "http://127.0.0.1:{{FRONTEND_PORT}}/" >/dev/null; then
        echo "Frontend: healthy (port {{FRONTEND_PORT}})"
    else
        echo "Frontend: down (port {{FRONTEND_PORT}})"
        exit 1
    fi
