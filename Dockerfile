# syntax=docker/dockerfile:1
# Build from repo root:
#   docker build -f sandbox/Dockerfile -t nexus-sandbox .
#
# Requires Linux host with KVM for microsandbox (--privileged + /dev/kvm at run).
# Ubuntu 24.04 provides glibc >= 2.39 required by the msb installer.

FROM ubuntu:24.04 AS builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=manual \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh

ENV PATH="/root/.local/bin:$PATH"

COPY sandbox/pyproject.toml sandbox/uv.lock sandbox/README.md ./
COPY sandbox/sandbox_service ./sandbox_service
COPY sandbox/sandbox ./sandbox

RUN uv python install 3.12 \
    && uv sync --frozen --no-dev

FROM ubuntu:24.04 AS runtime

WORKDIR /app
ENV PATH="/app/.venv/bin:/root/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    SANDBOX_HOST=0.0.0.0 \
    SANDBOX_PORT=8787 \
    SANDBOX_DEFAULT_BACKEND=microsandbox \
    SANDBOX_DEFAULT_IMAGE=hari31416/data-science-heavy-runtime:py312-v2 \
    SANDBOX_DATA_DIR=/var/lib/nexus-sandbox

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://install.microsandbox.dev | sh

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/sandbox_service /app/sandbox_service
COPY --from=builder /app/sandbox /app/sandbox
# uv-managed CPython used by the venv
COPY --from=builder /root/.local/share/uv/python /root/.local/share/uv/python

RUN mkdir -p /var/lib/nexus-sandbox /root/.microsandbox

EXPOSE 8787
CMD ["sandbox-service"]
