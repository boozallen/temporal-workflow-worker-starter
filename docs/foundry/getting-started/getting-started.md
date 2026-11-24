# Getting Started with Temporal Workflow Worker Starter

This template provides a foundational starting point for building Temporal workflow workers that integrate with Strands agents using the foundry packages from [Temporal Packages](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/index.md). The template demonstrates a **3-step workflow pattern** with configuration-driven architecture.

## Overview

This template demonstrates:
- **3-step workflow orchestration** using [`foundry-temporal`](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/packages/foundry-temporal/index.md) package with [`MyWorkflow`](../../../src/workflows.py)
- **Human-in-the-Loop (HITL) patterns** with approval signals ([Temporal workflow message passing](https://docs.temporal.io/encyclopedia/workflow-message-passing))
- **Strands agent integration** using [`foundry-temporal-agents`](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/packages/foundry-temporal-agents/index.md) call_strands_agent activity
- **Configuration-driven services** defined in [`config/services.yaml`](../../../config/services.yaml)
- **Local development environment** with Docker Compose and a mock agent ([`mock-strands-agent`](../../../mock-strands-agent/))
- **Clean, reusable patterns** for teams to fork and customize

## Prerequisites

- **Docker & Docker Compose**: For running the local development environment
- **[Temporal CLI](https://docs.temporal.io/cli)**: For the local Temporal development server the worker connects to
- **Python 3.15**: For local development outside Docker ([`pyproject.toml`](../../../pyproject.toml) requires `>=3.15,<3.16`)
- **[UV package manager](https://docs.astral.sh/uv/)**: For dependency management (recommended)
## Quick Start

### 1. Fork and Clone Template

This is a **template**, not a library. Fork this template and customize it for your team's needs:

```bash
# Clone your forked template
git clone <your-forked-repo> my-workflow-worker
cd my-workflow-worker
```

### 2. Environment Setup

Create your environment configuration:

```bash
# Copy the template environment file
cp env.template .env

# Edit .env with your configuration
# Key variables:
# - TEMPORAL_HOST: Temporal server address (default: localhost:7233)
# - TASK_QUEUE: Your unique task queue name
# - WORKER_IDENTITY: Your worker identifier
```

The worker refuses to start without an engine client authentication mechanism. For local development, `just dev` falls back to placeholder values in [`dev.env`](https://github.com/boozallen/temporal-workflow-worker-starter/blob/HEAD/dev.env) that are never read against a plaintext local [Temporal server](https://github.com/temporalio/temporal). It also connects to `localhost:7233` unless `TEMPORAL_HOST` is set in your shell. `dev.env` explains which settings win. Never deploy with `dev.env`. Deployed environments set real mTLS or OAuth2 settings, as described in [`env.template`](../../../env.template).

### 3. Install Dependencies

Install project dependencies using UV:

```bash
# Install and lock dependencies
uv sync
```

### 4. Start Local Development Environment

The worker needs a Temporal server. Start a local development server in its own terminal and leave it running. The worker container reaches it through `host.docker.internal` (the `TEMPORAL_HOST` in your `.env`), which Docker Desktop and Rancher Desktop map to this machine. The server has no authentication and listens on this machine only; stop it with `Ctrl+C` when you're done:

```bash
temporal server start-dev
```

Then, in another terminal, start the rest of the local development stack in [`compose.yaml`](../../../compose.yaml):

```bash
# Start worker and mock agent services
docker compose up -d

# Verify services are running
docker compose ps
```

### 5. Verify Setup

Once services are running, verify everything is working:

- **Worker Logs**: `docker compose logs -f worker`
- **Mock Agent Health**: `curl http://localhost:8081/health`
- **[Temporal UI](https://docs.temporal.io/web-ui)**: `http://localhost:8233` (served by the development server)

### 6. Explore the 3-Step Workflow

The template includes `MyWorkflow` demonstrating a complete 3-step pattern:

```python
# Step 1: Initial activity processing (my_activity)
# Step 2: Agent call using configuration-driven services
# Step 3: Human approval via signal (HITL pattern)
```

Run the worker locally to see detailed logs (`just dev` loads `dev.env` under your `.env` and connects to `localhost:7233`):
```bash
just dev
```

## Understanding the Template Architecture

### Configuration-Driven Services

Services are configured in `config/services.yaml` and loaded once:

```yaml
# config/services.yaml
mock_strands_agent:
  url: "http://mock-strands-agent:8080"
  description: "Mock Strands agent for template workflow demonstration"
```

Access services in workflows:
```python
from .services import get_service_config

service_config = get_service_config("mock_strands_agent")
agent_url = service_config["url"]
```

### 3-Step Workflow Pattern

The `MyWorkflow` demonstrates a complete orchestration pattern:

1. **Step 1: Activity Processing**
   - Calls `my_activity` in [`src/activities.py`](../../../src/activities.py) for initial data processing
   - Configurable processing type (standard or long_running)

2. **Step 2: Agent Integration**
   - Uses `call_strands_agent` from [foundry-temporal-agents](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/packages/foundry-temporal-agents/index.md)
   - Agent URL loaded from [`config/services.yaml`](../../../config/services.yaml)
   - Built-in retry policies and error handling

3. **Step 3: Human Approval**
   - Uses `HILSignalsMixin` for Human-in-the-Loop patterns
   - Waits for approval signal before completion
   - Timeout-based workflow control

### foundry Integration Patterns

**Worker Setup:**
```python
# Clean foundry-temporal integration
worker_config = WorkerConfig(
    temporal_address=app_config.temporal_host,
    namespace=app_config.temporal_namespace,
    task_queue=app_config.task_queue,
    identity=app_config.worker_identity,
    # Required by foundry-temporal >=2.0.0 (fails closed if unset):
    # "platform" | "tls" | "mtls"
    tls_mode=app_config.temporal_tls_mode,
)

client = await create_temporal_client(worker_config)
worker = create_worker_with_defaults(
    client=client, workflows=workflows, activities=activities
)
```

**Agent Calls:**
```python
# Direct foundry-temporal-agents integration
agent_result = await execute_activity(
    "call_strands_agent",
    args=[agent_url, task_prompt, query_extra_data],
    retry_policy=STRANDS_AGENT_RETRY_POLICY
)
```

## Development Workflow

### Local Development (Recommended)

For active development, run services in Docker and worker locally:

```bash
# Start services (worker will connect to these)
docker compose up -d mock-strands-agent

# The mock agent is published on localhost:8081. config/services.yaml points
# at the compose-network hostname (mock-strands-agent:8080), which a host-run
# worker can't resolve, so override it:
export MOCK_STRANDS_AGENT_URL=http://localhost:8081

# Start the worker locally in this same terminal, so it gets the override
just dev

# In another terminal, view service logs
docker compose logs -f mock-strands-agent
```

In PowerShell:

```powershell
# Start services (worker will connect to these)
docker compose up -d mock-strands-agent

# The mock agent is published on localhost:8081. config/services.yaml points
# at the compose-network hostname (mock-strands-agent:8080), which a host-run
# worker can't resolve, so override it:
$env:MOCK_STRANDS_AGENT_URL = "http://localhost:8081"

# Start the worker locally in this same terminal, so it gets the override
just dev

# In another terminal, view service logs
docker compose logs -f mock-strands-agent
```

### Full Docker Development

For testing the complete containerized setup:

```bash
# Start everything in Docker
docker compose up -d

# View worker logs
docker compose logs -f worker

# Scale worker instances
docker compose up -d --scale worker=3
```

### Testing

Run the comprehensive test suite in [`tests/`](../../../tests/):

```bash
# Run all tests
uv run pytest

# Run specific test categories
uv run pytest tests/unit/ -v
just test-integration  # tests/integration/ alone can't meet the project-wide coverage gate

# Run tests with coverage
uv run pytest --cov=src
```

## Next Steps

1. **Study the template**: Review [`src/workflows.py`](../../../src/workflows.py) to understand the 3-step pattern
2. **Customize [MyWorkflow](../../../src/workflows.py)**: Replace with your business logic while keeping the structure
3. **Update [services.yaml](../../../config/services.yaml)**: Configure your actual agents and services
4. **Add your activities**: Replace `my_activity` in [`src/activities.py`](../../../src/activities.py) with your business operations
5. **Configure workflows/activities**: Update [`config/workflows.yaml`](../../../config/workflows.yaml) and [`config/activities.yaml`](../../../config/activities.yaml)
6. **Expand tests**: Update the tests in [`tests/`](../../../tests/) for your customizations

## Updated Template Structure

```
temporal-workflow-worker-starter/
├── src/                           # Core application code
│   ├── workflows.py               # MyWorkflow (3-step template)
│   ├── activities.py              # my_activity and MyActivityResult
│   ├── worker.py                  # Clean foundry-temporal integration
│   ├── services.py                # Services configuration management
│   ├── models.py                  # Workflow input/output models
│   └── config.py                  # Essential configuration only
├── config/                        # Configuration files
│   ├── workflows.yaml             # Workflow registration
│   ├── activities.yaml            # Activity registration
│   └── services.yaml              # External services configuration
├── tests/                         # Clean test suite
│   ├── unit/                      # Unit tests for all components
│   └── integration/               # Integration tests
├── docs/                          # Documentation
├── compose.yaml                   # Local development stack
├── Dockerfile                     # Multi-stage, non-root worker container
└── env.template                   # Environment configuration template
```

## Key Architecture Benefits

- ✅ **Configuration-driven**: Services, workflows, and activities configured via YAML files in [`config/`](../../../config/)
- ✅ **Clean integration**: Uses the foundry packages from [Temporal Packages](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/index.md) without custom wrappers
- ✅ **HITL patterns**: Built-in Human-in-the-Loop support with signals
- ✅ **Logging and retries built in**: Comprehensive logging, retries, error handling
- ✅ **Testing**: Full test coverage with clean, maintainable tests in [`tests/`](../../../tests/)
- ✅ **Docker-ready**: Complete containerization with the [`Dockerfile`](../../../Dockerfile) for development and production

## Support

- **Template Issues**: Report issues with the template structure
- **Foundry Packages**: Check the [foundry-temporal](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/packages/foundry-temporal/index.md) and [foundry-temporal-agents](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/packages/foundry-temporal-agents/index.md) documentation
- **Temporal Concepts**: See [Temporal documentation](https://docs.temporal.io/)

Remember: This is a **starting point template** - fork it, customize it, and make it your own! The clean architecture and comprehensive patterns provide a solid foundation for your team's workflow automation needs.
