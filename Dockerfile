# Temporal Workflow Worker Dockerfile
# Template version - teams should customize for their needs
# CI trigger: rebuild to pull patched cgr.dev/chainguard/python:latest-dev
# layers for CVE-2026-84243 (glibc), CVE-2026-119586 (sqlite-libs), and
# CVE-2026-116566 / CVE-2026-103995 (python-3.15).

# Public Chainguard Python dev image (currently Python 3.15).
# `latest-dev` is the floating tag offered in the free public catalog.
FROM cgr.dev/chainguard/python:latest-dev AS base

# Install system dependencies
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     curl \
#     ca-certificates \
#     && rm -rf /var/lib/apt/lists/* \
#     && groupadd -r agentuser \
#     && useradd -r -g agentuser agentuser \
#     && mkdir -p /app/logs /app/data

# switch to root user
USER root


RUN apk update && apk add --no-cache ca-certificates \
    && /usr/sbin/update-ca-certificates \
    && mkdir -p /app/sessions/session_default \
    && addgroup -g 777 agentuser \
    && adduser -u 777 -G agentuser -h /home/agentuser -D agentuser

###

FROM base AS builder

# Copy uv (teams may use different registries)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=true \
    UV_LINK_MODE=copy \
    UV_NO_INSTALLER_METADATA=true \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies including foundry packages (uses pyproject.toml index configuration)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-editable --no-install-project --no-install-workspace

# Copy source code
COPY src/ ./src/
COPY tests/ ./tests/
COPY config/ ./config/

###

FROM base AS production

# Copy built application from builder
COPY --from=builder --chown=agentuser:agentuser /app /app

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TEMPORAL_HOST=temporal-server:7233 \
    TEMPORAL_NAMESPACE=default \
    TASK_QUEUE=workflow-task-queue \
    WORKER_IDENTITY=workflow-worker-starter \
    LOG_LEVEL=INFO

# create necessary directories
RUN mkdir -p /app/logs /app/data \
    && chown -R agentuser:agentuser /app

# Set ownership and switch to non-root user
RUN chown -R agentuser:agentuser /app /app/logs /app/data
USER agentuser

WORKDIR /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import sys; from src.config import get_config; get_config(); sys.exit(0)"

# Container metadata
LABEL \
    org.opencontainers.image.title="Workflow Worker Template" \
    org.opencontainers.image.description="Template for Temporal workflow workers with foundry integration" \
    org.opencontainers.image.version="1.0.0" \
    maintainer="Baseline Team" \
    worker.type="template-workflow-worker"

# Base image sets ENTRYPOINT ["python"]; clear it so CMD runs directly
ENTRYPOINT []
CMD ["python", "-m", "src.worker"]