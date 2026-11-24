# Temporal Workflow Worker Starter - Development Commands
# Usage: just <command> [args]

image := "temporal-workflow-worker-starter"

# Show all available recipes
default:
    @just --list

# ============================================================================
# Setup & Dependencies
# ============================================================================

# Sync the virtual environment with the lockfile (dev + test groups)
sync:
    uv sync --group dev --group test

# Set up the local development environment (dependencies + .env + lockfile)
setup: sync
    @if [ ! -f .env ]; then \
        cp env.template .env; \
        echo "Created .env from env.template - review and customize it"; \
    fi
    uv lock
    @echo "Development environment ready"

# Add a package to the project
add-package package:
    uv add "{{package}}"
    uv lock

# Add a development package to the project
add-dev-package package:
    uv add --dev "{{package}}"
    uv lock

# ============================================================================
# Code Quality
# ============================================================================

# Run ruff lint + the bandit command-injection sink set
lint:
    uv run ruff check src/ tests/
    uv run bandit -c pyproject.toml -r src -t B602,B603,B605,B607

# Auto-fix ruff lint findings
lint-fix:
    uv run ruff check src/ tests/ --fix

# Check code formatting
format:
    uv run ruff format --check src/ tests/

# Auto-format code
format-fix:
    uv run ruff format src/ tests/

# Run basedpyright type checking
type-check:
    uv run basedpyright src/

# Run every quality gate: lint, format, type-check, test
check: lint format type-check test
    @echo "All quality checks passed"

# ============================================================================
# Testing
# ============================================================================
#
# The unit/integration split is by DIRECTORY, not by marker: `tests/unit/` is the
# unit tier and `tests/integration/` is the integration tier, so a test's tier is
# decided by where its file lives and cannot be forgotten. `test` runs both tiers,
# `test-unit` runs `tests/unit/` only, `test-integration` runs `tests/integration/`
# only. No recipe passes `-m`; markers stay declared as cross-cutting trait tags
# but nothing selects on them.
#
# Coverage is always on via `[tool.pytest.ini_options] addopts` in pyproject.toml
# (terminal + HTML into `htmlcov/`), never from a recipe, so there is no separate
# coverage recipe.

# Run all tests (unit + integration)
test:
    uv run pytest tests/

# Run unit tests only
test-unit:
    uv run pytest tests/unit/

# Coverage is disabled for this isolated slice (`--no-cov --cov-fail-under=0`): on
# its own it does not exercise enough of the source tree to meet the configured
# threshold, and instrumenting it would overwrite `htmlcov/` with integration-only
# data. pytest exit code 5 (no tests collected) is treated as success so the recipe
# stays valid if this tier is ever empty.
# Run integration tests only
test-integration:
    #!/usr/bin/env bash
    set -uo pipefail
    uv run pytest tests/integration/ --no-cov --cov-fail-under=0
    status=$?
    if [ "$status" -eq 5 ]; then
        echo "No integration tests collected - not a failure."
        exit 0
    fi
    exit $status

# ============================================================================
# Local Runtime (repo-specific)
# ============================================================================

# Start Temporal dev server (run this first). The dev server has no auth, so it
# binds loopback by default. With Docker Engine installed directly in Linux or
# WSL, run `just temporal 0.0.0.0` so the worker container can reach it.
temporal ip="127.0.0.1":
    @echo "Starting Temporal development server on {{ ip }}..."
    @echo "Web UI will be available at: http://localhost:8233"
    temporal server start-dev --ip {{ ip }} --port 7233 --ui-port 8233

# Run the worker locally with dev.env defaults under .env (no Docker; needs a reachable Temporal server)
dev:
    TEMPORAL_HOST={{ env_var_or_default("TEMPORAL_HOST", "localhost:7233") }} uv run --env-file dev.env {{ if path_exists(".env") == "true" { "--env-file .env" } else { "" } }} python -m src.worker

# Run the worker locally (alias for dev)
run: dev

# Start the worker and mock agent containers (assumes a Temporal server is running)
up:
    @echo "Temporal server must already be reachable on localhost:7233"
    docker compose up -d
    @echo "Worker and mock agent started! Use 'just logs' to view output"

# Start the worker and mock agent containers (alias for up)
start: up

# Stop the worker and mock agent containers
down:
    docker compose down

# Stop the worker and mock agent containers (alias for down)
stop: down

# View logs (optionally for a single service)
logs service="":
    @if [ -z "{{service}}" ]; then \
        docker compose logs -f; \
    else \
        docker compose logs -f "{{service}}"; \
    fi

# Build the worker Docker image
build:
    docker build -t {{image}} .

# Check service status and health
status:
    @echo "=== Service Status ==="
    docker compose ps
    @echo ""
    @echo "=== Service Health ==="
    @curl -s http://localhost:8081/health && echo "" || echo "Mock Agent not ready"

# Stop containers, clean artifacts, and re-run setup
reset: down clean setup
    @echo "Development environment reset complete"

# Validate the Docker image builds
validate-docker:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! docker info > /dev/null 2>&1 && command -v wsl.exe > /dev/null 2>&1; then
        wsl_docker="$(wsl.exe -e bash -lc 'command -v docker' 2>/dev/null | tr -d '\r')" || true
        if [ -z "$wsl_docker" ]; then
            echo "Docker daemon unreachable natively, and no docker found via WSL either." >&2
            exit 1
        fi
        echo "Native docker unreachable - routing through WSL instead ($wsl_docker)."
        docker() { MSYS_NO_PATHCONV=1 wsl.exe -e "$wsl_docker" "$@"; }
    fi
    echo "Building Docker image for validation..."
    docker buildx build \
        --platform linux/amd64 \
        --build-arg BUILDKIT_INLINE_CACHE=1 \
        --tag {{image}}:test \
        --load \
        .
    echo "Testing container startup..."
    docker run --rm --env-file dev.env {{image}}:test python -c "\
        import sys; \
        from src.config import get_config; \
        get_config(); \
        sys.exit(0)"
    echo "Testing core dependencies..."
    docker run --rm {{image}}:test python -c "\
        import temporalio; \
        import foundry_temporal; \
        print('Core dependencies installed successfully'); \
        print(f'Temporal SDK version: {temporalio.__version__}')"
    echo "Testing worker configuration..."
    docker run --rm {{image}}:test python -c "\
        from src.worker import run_worker, start_temporal_worker; \
        from src.workflows import MyWorkflow; \
        from src.activities import my_activity, get_service_config_activity; \
        print('Worker functions can be imported'); \
        print('Example workflows and activities can be imported')"
    echo "Validating image metadata..."
    docker inspect {{image}}:test --format '{{{{json .Config.Labels}}' | grep -q "version"
    docker inspect {{image}}:test --format '{{{{.Config.User}}' | grep -q "agentuser"
    echo "Docker image metadata is correct"
    echo "Testing multi-platform build capability..."
    if docker buildx build --platform linux/amd64,linux/arm64 --build-arg BUILDKIT_INLINE_CACHE=1 --tag {{image}}:multiplatform . 2>/dev/null; then
        echo "Multi-platform build validation successful"
    else
        echo "Multi-platform build not supported locally (requires containerd or different driver)"
        echo "This will work in GitHub Actions - skipping for local validation"
    fi
    echo "All Docker validation tests passed!"

# ============================================================================
# Maintenance
# ============================================================================

# Clean build artifacts and tooling caches
clean:
    rm -rf build/
    rm -rf dist/
    rm -rf htmlcov/
    rm -rf *.egg-info/
    rm -f .coverage
    find . \( -path ./.venv -prune \) -o \( -type d \( -name .pytest_cache -o -name .ruff_cache -o -name __pycache__ \) -prune -exec rm -rf {} + \) -o \( -type f -name "*.pyc" -exec rm -f {} + \)
    @echo "Cleaned build artifacts"

# Clean build artifacts plus this project's Docker containers and volumes
clean-all: clean
    docker compose down -v --remove-orphans
    @echo "Cleaned build artifacts and Docker resources"
