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
ARG TARGETARCH
# Pin a known release; install.sh can lag libkrunfw soname vs the tarball.
ARG MSB_VERSION=v0.6.6
ENV PATH="/app/.venv/bin:/root/.local/bin:/root/.microsandbox/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    SANDBOX_HOST=0.0.0.0 \
    SANDBOX_PORT=8787 \
    SANDBOX_DEFAULT_BACKEND=microsandbox \
    SANDBOX_DEFAULT_IMAGE=hari31416/data-science-heavy-runtime:py312-v2 \
    SANDBOX_DATA_DIR=/var/lib/nexus-sandbox \
    MSB_HOME=/root/.microsandbox \
    LD_LIBRARY_PATH=/root/.microsandbox/lib

# Install msb from the GitHub release for TARGETARCH (not curl|sh / uname),
# so linux/amd64 builds on Apple Silicon get the correct bundle.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && case "${TARGETARCH}" in \
         amd64) MSB_ARCH=x86_64 ;; \
         arm64) MSB_ARCH=aarch64 ;; \
         *) echo "unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
       esac \
    && curl -fsSL \
         "https://github.com/superradcompany/microsandbox/releases/download/${MSB_VERSION}/microsandbox-linux-${MSB_ARCH}.tar.gz" \
         -o /tmp/msb.tar.gz \
    && mkdir -p /tmp/msb-extract \
    && tar -xzf /tmp/msb.tar.gz -C /tmp/msb-extract \
    && mkdir -p /root/.microsandbox/bin /root/.microsandbox/lib /root/.local/bin \
    && install -m 755 /tmp/msb-extract/msb /root/.microsandbox/bin/msb \
    && ln -sf /root/.microsandbox/bin/msb /root/.microsandbox/bin/microsandbox \
    && ln -sf /root/.microsandbox/bin/msb /root/.local/bin/msb \
    && ln -sf /root/.microsandbox/bin/msb /root/.local/bin/microsandbox \
    && LIBKRUNFW="$(find /tmp/msb-extract -maxdepth 1 -name 'libkrunfw.so.*' | head -1)" \
    && test -n "${LIBKRUNFW}" \
    && install -m 644 "${LIBKRUNFW}" "/root/.microsandbox/lib/$(basename "${LIBKRUNFW}")" \
    && ln -sfn "$(basename "${LIBKRUNFW}")" /root/.microsandbox/lib/libkrunfw.so.5 \
    && ln -sfn libkrunfw.so.5 /root/.microsandbox/lib/libkrunfw.so \
    && rm -rf /tmp/msb.tar.gz /tmp/msb-extract \
    && msb --help >/dev/null

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/sandbox_service /app/sandbox_service
COPY --from=builder /app/sandbox /app/sandbox
# uv-managed CPython used by the venv
COPY --from=builder /root/.local/share/uv/python /root/.local/share/uv/python

RUN mkdir -p /var/lib/nexus-sandbox /root/.microsandbox

EXPOSE 8787
CMD ["sandbox-service"]
