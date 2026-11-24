# Temporal Workflow Worker Starter

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.15-blue)
![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue)

A fork-and-customize template for [Temporal](https://temporal.io/) workflow workers. It
gives you a complete, running worker — a 3-step workflow with an agent call and a
human-in-the-loop approval gate, configuration-driven registration, a local Docker stack,
and both test tiers — so you start from something that works rather than from an empty
`workflows.py`.

This is **not a library**. It is a starting point: fork it, replace the template workflow
and activities with your business logic, and deploy the result as your team's service. It
composes the [`temporal-packages`](https://github.com/boozallen/temporal-packages)
libraries, which supply the workflow primitives (signals, queries, retry policies, storage
abstraction, worker bootstrap) and the activity for calling Strands agents.

> **End-to-End Guides** — for a walkthrough of the full stack (Worker + API + Agent), see
> [Getting Started](docs/foundry/guides/end-to-end-how-to-getting-started.md),
> [Next Steps](docs/foundry/guides/end-to-end-how-to-next-steps.md), and
> [Advanced](docs/foundry/guides/end-to-end-how-to-advanced.md).

## Installation

Fork the repository first — customizing it is the intended workflow — then clone your fork:

```bash
git clone https://github.com/<your-username>/temporal-workflow-worker-starter.git my-workflow-worker
cd my-workflow-worker
cp env.template .env
just setup          # uv sync --group dev --group test, then uv lock
```

The `foundry-*` dependencies install from their public GitHub release wheels
([temporal-packages](https://github.com/boozallen/temporal-packages/releases) and
[foundry-agent-packages](https://github.com/boozallen/foundry-agent-packages/releases)), which
`[tool.uv.sources]` in [`pyproject.toml`](pyproject.toml) names, so `just setup` needs no extra package index.

## Getting Started

The local stack runs the worker against a mock Strands agent, so you can watch a workflow
execute without any external services. The mock agent is for local development only.
Replace it with a real agent before deploying (see the
[Next Steps guide](docs/foundry/guides/end-to-end-how-to-next-steps.md)):

```bash
just temporal       # 1. Temporal dev server (needs the Temporal CLI)
just start          # 2. Worker + mock agent via docker compose
just logs           # 3. Follow worker output
just status         # 4. Check container health
```

Then open the Temporal Web UI at `http://localhost:8233` to see
workflow executions. `just reset` stops everything and re-provisions the environment.

`just temporal` binds the dev server to `127.0.0.1`, because the dev server has no
authentication. Docker Desktop and Rancher Desktop reach it through
`host.docker.internal` with no changes. If you run Docker Engine directly in
Linux or WSL, start it with `just temporal 0.0.0.0` instead. That also exposes
the server to your network, so only do this on a trusted network.

If the worker on Docker Engine cannot resolve `host.docker.internal`, add this
to the worker service in `compose.yaml`:

```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

## Local Development & Verification

This is how you verify the repo. The template ships no CI workflows, so these are the
gates — run them before opening a pull request against your fork.

**Prerequisites**

- Python 3.15 ([`pyproject.toml`](pyproject.toml) requires `>=3.15,<3.16`)
- [uv](https://docs.astral.sh/uv/) package manager
- [just](https://github.com/casey/just) command runner
- Docker with Compose, for the local stack and `just validate-docker`
- The [Temporal CLI](https://docs.temporal.io/cli), for `just temporal`

**Verify**

```bash
just check          # full gate: lint + format + type-check + test
just test           # unit and integration tiers (writes htmlcov/ via pytest config)
just validate-docker # confirm the container image builds
```

**Narrower loops**

| Command | Description |
|---------|-------------|
| `just sync` | Install dependencies only (no `.env` or lockfile work) |
| `just setup` | `sync` plus local env prep — creates `.env` from [`env.template`](env.template), runs `uv lock` |
| `just lint` / `just lint-fix` | Ruff lint plus the bandit command-injection sink set (`B602,B603,B605,B607`) / auto-fix |
| `just format` / `just format-fix` | Check / apply formatting |
| `just type-check` | basedpyright type checking |
| `just test-unit` / `just test-integration` | One tier only |
| `just dev` / `just run` | Run the worker locally, no Docker (alias) — needs a reachable Temporal server. Connects to `localhost:7233` and falls back to the local-only placeholders in [`dev.env`](dev.env) |
| `just up` / `just start` | Start the worker and mock agent containers (`start` is an alias) |
| `just down` / `just stop` | Stop the worker and mock agent containers (`stop` is an alias) |
| `just logs [service]` / `just status` / `just reset` | Local stack lifecycle |
| `just build` | Build the worker Docker image |
| `just clean` / `just clean-all` | Remove build artifacts and caches / plus this project's containers and volumes |

`just --list` shows the full recipe surface.

Tests split by **directory**, not by marker: [`tests/unit/`](tests/unit/) and [`tests/integration/`](tests/integration/), so a
test's tier is decided by where the file lives and cannot be forgotten.
`just test-integration` treats "no tests collected" (pytest exit code 5) as success, so it
is safe to run on a branch with no integration tests yet. `just check` does not call
`sync` — `uv run` auto-syncs on every invocation, so a cold clone can run it directly.
`just clean` never touches Docker, so it works with no daemon running; `just clean-all`
adds `docker compose down -v --remove-orphans`, scoped to this project's own compose file.

## What You Get Out of the Box

- **A complete working system** — runs immediately against the mock agent, no external
  services required
- **A 3-step workflow template** — `MyWorkflow`, demonstrating activity execution, an
  agent call, and a human-in-the-loop approval gate
- **Configuration-driven architecture** — workflows, activities, and services declared in
  `config/*.yaml` rather than hardcoded in the worker
- **Docker development stack** — worker container plus a mock Strands agent service
- **Both test tiers** — unit and integration, split by directory
- **Production-ready patterns** — structured logging, retry policies, error handling,
  graceful shutdown, and a multi-stage image with a non-root runtime user

The template does **not** ship CI workflows. Add your own for your fork — see the
[Deployment Guide](docs/foundry/operations/deployment.md) for an example pipeline.

## Fork-and-Customize Approach

1. **Fork** this repository into your team's namespace and rename it for your project
   (e.g. `customer-onboarding-workflows`). That fork becomes your team's worker codebase.
2. **Customize** — replace the template workflow with your business logic, update
   activities to call your services and agents, and modify the data models for your domain.
3. **Deploy** your customized worker, connected to your own agents and services, scaled to
   your workflow volume.

### Customization Roadmap

**Step 1 — Update project identity** in `pyproject.toml` (`name`, `description`,
`[project.urls]`, `authors`) and copy `env.template` to `.env` for your configuration.

**Step 2 — Replace the template workflow** in [`src/workflows.py`](src/workflows.py):

```python
@workflow.defn
class CustomerOnboardingWorkflow(HILSignalsMixin):
    @workflow.run
    async def run(self, customer_data: CustomerInput) -> OnboardingResult:
        # Your business logic here
        ...
```

**Step 3 — Replace the template activities** in [`src/activities.py`](src/activities.py):

```python
@activity.defn
async def validate_customer_data(customer: dict) -> bool:
    # Your validation logic
    ...
```

**Step 4 — Register your code** in the config files:

```yaml
# config/workflows.yaml
workflows:
  - module: "src.workflows"
    classes: ["CustomerOnboardingWorkflow"]

# config/activities.yaml
activities:
  - module: "src.activities"
    functions: ["validate_customer_data"]

# config/services.yaml
customer_service_agent:
  url: "https://your-agent.example.com"
  description: "Customer service agent for onboarding"
```

**Step 5 — Point at your real agents** by replacing the [`mock-strands-agent`](mock-strands-agent/) service in
[`compose.yaml`](compose.yaml) with your own image.

The [Customization Guide](docs/foundry/guides/customization-guide.md) covers each step in
detail.

## Template Structure

```
temporal-workflow-worker-starter/
├── README.md                      # This guide (customize for your team)
├── CONTRIBUTING.md                # Fork workflow, dev setup, review process
├── SECURITY.md                    # Reporting a vulnerability
├── CHANGELOG.md                   # Release history
├── pyproject.toml                 # Dependencies (add your packages)
├── justfile                       # Development commands
├── compose.yaml                   # Local dev stack (add your services)
├── Dockerfile                     # Worker container (customize as needed)
├── env.template                   # Environment config template
│
├── src/                           # CUSTOMIZE: core application code
│   ├── workflows.py               # REPLACE: MyWorkflow → your workflows
│   ├── activities.py              # REPLACE: my_activity → your activities
│   ├── worker.py                  # Configuration-driven worker bootstrap
│   ├── services.py                # Services configuration management
│   ├── models.py                  # UPDATE: add your data models
│   └── config.py                  # Essential configuration only
│
├── config/                        # CUSTOMIZE: registration and services
│   ├── workflows.yaml             # UPDATE: register your workflows
│   ├── activities.yaml            # UPDATE: register your activities
│   └── services.yaml              # UPDATE: configure your services
│
├── tests/
│   ├── unit/                      # Unit tests (update for your logic)
│   └── integration/               # Integration tests (need running services)
│
├── mock-strands-agent/            # Stand-in agent, local development only
├── security/                      # Security assessment artifacts
└── docs/foundry/                  # Documentation (see table below)
```

## Template Example: 3-Step Workflow

`MyWorkflow` demonstrates the orchestration pattern the template is built around:

```python
@workflow.defn
class MyWorkflow(HILSignalsMixin):
    @workflow.run
    async def run(self, input_data: MyWorkflowInput) -> MyWorkflowResult:
        # STEP 1: Initial activity processing
        activity_result = await execute_activity(
            "my_activity",
            args=[activity_data],
            start_to_close_timeout=timedelta(minutes=2),
        )

        # STEP 2: Agent call, with the URL resolved from services.yaml
        service_config = get_service_config("mock_strands_agent")
        agent_result = await execute_activity(
            "call_strands_agent",
            args=[service_config["url"], task_prompt, query_extra_data],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=STRANDS_AGENT_RETRY_POLICY,
        )

        # STEP 3: Block until a human approves
        await workflow.wait_condition(
            lambda: self.approved,
            timeout=timedelta(minutes=10),
        )

        return MyWorkflowResult(success=True, message=combined_message, data=result_data)

    @workflow.signal
    def approve(self) -> None:
        """Human approval signal from HILSignalsMixin."""
        super().approve()
```

### Key Patterns

**Configuration-driven services** — agent URLs live in [`config/services.yaml`](config/services.yaml) and are
resolved at runtime via `get_service_config()`, so no endpoint is hardcoded in workflow
code.

**Human-in-the-loop signals** — `HILSignalsMixin` supplies the approval signal and query
handlers; a workflow blocks on `workflow.wait_condition(lambda: self.approved)`.

**Agent integration without custom decorators** — call the ready-made
`call_strands_agent` activity directly, with the packaged `STRANDS_AGENT_RETRY_POLICY`
rather than hand-rolled backoff.

**Minimal configuration surface** — `AppConfig` carries only the Temporal connection,
worker concurrency, and logging settings. Note that `tls_mode` is required: the worker
library fails closed without an explicit TLS posture, so the transport is never silently
plaintext.

## Documentation

| Document | Description |
|----------|-------------|
| [Overview](docs/foundry/index.md) | What ships in the template and where to go next |
| [Getting Started](docs/foundry/getting-started/getting-started.md) | Setup and first workflow |
| [End-to-End: Getting Started](docs/foundry/guides/end-to-end-how-to-getting-started.md) | Full stack setup from scratch |
| [End-to-End: Next Steps](docs/foundry/guides/end-to-end-how-to-next-steps.md) | Swap the mock agent for a real Strands agent |
| [End-to-End: Advanced](docs/foundry/guides/end-to-end-how-to-advanced.md) | Loop-based workflows with HIL feedback cycles |
| [Customization Guide](docs/foundry/guides/customization-guide.md) | Step-by-step customization |
| [Deployment Guide](docs/foundry/operations/deployment.md) | Production deployment patterns |
| [HA Worker Tuning](docs/foundry/operations/ha-worker-tuning.md) | Concurrency, scaling, and monitoring |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Fork workflow, dev setup, review and merge process |
| [SECURITY.md](SECURITY.md) | Reporting a vulnerability |

## Support

- **Template issues** — open an issue on this repository
- **Security vulnerabilities** — do not open a public issue; see [SECURITY.md](SECURITY.md)
- **Foundry packages** — see the
  [`temporal-packages`](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/index.md) documentation
- **Temporal concepts** — see the [Temporal documentation](https://docs.temporal.io/)

## License

Apache-2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).
