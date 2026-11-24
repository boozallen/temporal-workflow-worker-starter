# Next Steps: Swap Mock Agent for Foundry Strands Base Agent

This guide picks up where the [End-to-End Setup Guide](end-to-end-how-to-getting-started.md) left off. You already have the [Temporal Server](https://github.com/temporalio/temporal), [Workflow Worker](../index.md), and [Workflow API](https://github.com/boozallen/temporal-workflow-api-starter/blob/HEAD/docs/foundry/index.md) running with the **[mock-strands-agent](../../../mock-strands-agent/)**. Now you will replace the mock agent with the real **[Foundry Strands Base Agent](https://github.com/boozallen/strands-base-agent/blob/HEAD/docs/foundry/index.md)** — an [AWS Bedrock](https://aws.amazon.com/bedrock/)–powered A2A agent.

## What Changes

| Component | Before (mock) | After (real) |
|---|---|---|
| **Agent service** | [`mock-strands-agent`](../../../mock-strands-agent/) — static canned responses | [`strands-base-agent`](https://github.com/boozallen/strands-base-agent/blob/HEAD/docs/foundry/index.md) — live LLM-backed agent ([AWS Bedrock](https://aws.amazon.com/bedrock/)) |
| **Agent port** | `8080` (container), `8081` (host) | `8000` (container), `8081` (host) |
| **Health endpoint** | `GET /health` | `GET /api/v1/health` |
| **A2A protocol** | JSON-RPC 2.0 on `POST /` | JSON-RPC 2.0 via Strands A2A server |
| **Worker → Agent URL** | `http://mock-strands-agent:8080` (Docker DNS) | `http://host.docker.internal:8081` (host network) |

> The Strands Base Agent runs in its own compose stack on its own network. The worker reaches it via `host.docker.internal` — the same pattern used to connect to the Temporal Server. No shared Docker network is required.

---

## Prerequisites

Everything from the [End-to-End Setup Guide](end-to-end-how-to-getting-started.md), plus:

1. **AWS credentials** configured via AWS SSO or static credentials in `~/.aws`

   ```bash
   # Verify you have valid AWS credentials
   aws sts get-caller-identity
   ```

   > The Strands Base Agent uses **AWS Bedrock** as its LLM provider. You need an AWS account with Bedrock model access enabled for the model the agent's [`config.yaml`](https://github.com/boozallen/strands-base-agent/blob/HEAD/config.yaml) names under `model.model_id` (currently `us.anthropic.claude-haiku-5-5`), in `us-east-1`.

2. **Access to the [Foundry Strands Base Agent repository](https://github.com/boozallen/strands-base-agent)**

   ```bash
   # Verify you can reach the repository
   git ls-remote https://github.com/boozallen/strands-base-agent.git
   ```

---

## Step 1 — Clone the Strands Base Agent

```bash
cd ~/temporal-stack

# Clone the Foundry Strands Base Agent
git clone https://github.com/boozallen/strands-base-agent.git strands-base-agent
```

Your directory should now look like this:

```
temporal-stack/
├── temporal-workflow-worker-starter/ ← Worker template
├── temporal-workflow-api-starter/    ← API template
└── strands-base-agent/              ← NEW: Real Strands agent
```

---

## Step 2 — Configure the Strands Base Agent

### 2.1 Create the environment file

```bash
cd ~/temporal-stack/strands-base-agent
cp env.template .env
```

### 2.2 Generate the agent's API key

The agent refuses to start without `STRANDS_API_KEY`, and every request to it except the health check and agent card must send that key as a bearer token. Generate one (`--no-project` runs Python without installing the agent's dependencies):

```bash
uv run --no-project python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the printed value. It goes in the agent's `.env` (next step) and, as `FOUNDRY_AGENT_BEARER_TOKEN`, in the worker's `.env` ([step 5.5](#55-give-the-worker-the-agents-api-key)).

### 2.3 Edit the `.env` file

Open `.env` and configure the required values. At minimum, verify these settings:

```env
# Server Configuration
HOST=0.0.0.0
PORT=8081
LOG_LEVEL=INFO

# API key from step 2.2. The agent won't start while this is empty.
STRANDS_API_KEY=<the key you generated in step 2.2>

# AWS Profile — set this to your profile name from ~/.aws/config
AWS_PROFILE=<your-aws-profile>
AWS_DEFAULT_REGION=us-east-1

# Model Configuration: the agent's config.yaml sets the model. To use another
# Bedrock inference profile, override it (STRANDS__ prefix, __ between levels):
# STRANDS__MODEL__MODEL_ID=<inference-profile-id>

# Answer length: the Advanced guide's research documents run longer than the model's
# default answer cap (config.yaml leaves max_tokens unset), so raise it:
STRANDS__MODEL__MAX_TOKENS=16000

# Session Management: sessions are off by default. To keep conversations in
# files, set both overrides and SESSION_ENCRYPTION_KEY (required for file sessions):
# STRANDS__SESSION_TYPE=file
# STRANDS__SESSION_STORAGE_DIR=./sessions
```

> **Important**: Set `PORT=8081` so the host-mapped port doesn't conflict with the Workflow API on port `8000`. The agent's [`compose.yaml`](https://github.com/boozallen/strands-base-agent/blob/HEAD/compose.yaml) maps `$PORT:8000`, so this exposes the agent at `localhost:8081`.

> **AWS_PROFILE**: Check your available profiles with `aws configure list-profiles` and set `AWS_PROFILE` to the one that has Bedrock access. If you only have one profile, it's likely `default`.

> **WSL**: If your WSL `~/.aws` folder, or its `sso`, `cli`, `config` or `credentials` entry, links into your Windows profile, also add the `AWS_LINK_*` lines the agent's [Docker quickstart](https://github.com/boozallen/strands-base-agent/blob/HEAD/docs/foundry/quickstart-docker.md) describes to this `.env`, so the container can follow those links.

> **Tip**: The [`env.template`](https://github.com/boozallen/strands-base-agent/blob/HEAD/env.template) lists the secrets and per-environment values `.env` takes. The agent's other settings, such as its model, system prompt, tools, MCP servers and sessions, live in its [`config.yaml`](https://github.com/boozallen/strands-base-agent/blob/HEAD/config.yaml).

---

## Step 3 — Stop the Mock Agent

Before starting the real agent, stop the mock agent to free port `8081`.

```bash
cd ~/temporal-stack/temporal-workflow-worker-starter

# Stop only the mock-strands-agent container (leave the worker running)
docker compose stop mock-strands-agent
docker compose rm -f mock-strands-agent
```

---

## Step 4 — Start the Strands Base Agent

The agent runs with its own `compose.yaml` — no special network configuration needed. The worker will reach it via `host.docker.internal`.

`just up` runs `docker compose up -d`, and on WSL it also loads the agent's `compose.wsl.yaml`, without which the container can't read your `~/.aws` (see the agent's [Docker quickstart](https://github.com/boozallen/strands-base-agent/blob/HEAD/docs/foundry/quickstart-docker.md)). It doesn't build the image, so build it first. Otherwise an image left over from an earlier copy of the agent would be used.

```bash
cd ~/temporal-stack/strands-base-agent

# Build the image, then start the agent
docker compose build
just up
```

### 4.1 Verify the agent is running

```bash
# Check container status
docker compose ps

# Wait for startup (~15–30 seconds for model initialization)
sleep 15

# Test health endpoint
curl http://localhost:8081/api/v1/health
# Expected: {"status":"healthy","timestamp":"...","service_info":{...}}
```

In PowerShell:

```powershell
# Check container status
docker compose ps

# Wait for startup (~15–30 seconds for model initialization)
sleep 15

# Test health endpoint
curl.exe http://localhost:8081/api/v1/health
# Expected: {"status":"healthy","timestamp":"...","service_info":{...}}
```

---

## Step 5 — Update the Worker Configuration

The worker needs to point to the real agent's external URL instead of the mock agent's Docker DNS name, and to send the agent's API key. Four files and the worker's `.env` need to change.

### 5.1 Update `config/services.yaml`

```bash
cd ~/temporal-stack/temporal-workflow-worker-starter
```

Edit [`config/services.yaml`](../../../config/services.yaml) — replace the mock agent entry with the real agent:

```yaml
# Foundry Strands Base Agent (replaces mock-strands-agent)
strands_agent:
  url: "http://host.docker.internal:8081"
  description: "Foundry Strands Base Agent powered by AWS Bedrock"
```

> **Key change**: The URL uses `host.docker.internal:8081` — this is how Docker containers reach services on the host machine. It's the same pattern the worker uses to reach the Temporal Server (`host.docker.internal:7233`). Port `8081` matches the host-mapped port from the agent's compose stack.

### 5.2 Update `src/workflows.py`

In the `run` method of [`MyWorkflow`](../../../src/workflows.py), find `args=["mock_strands_agent"]` and change the service config key to match the new `services.yaml` entry:

```python
# Before:
service_config = await execute_activity(
    "get_service_config_activity",
    args=["mock_strands_agent"],
    start_to_close_timeout=timedelta(seconds=10),
)

# After:
service_config = await execute_activity(
    "get_service_config_activity",
    args=["strands_agent"],
    start_to_close_timeout=timedelta(seconds=10),
)
```

### 5.3 Update `src/models.py` (optional)

In `MyWorkflowResult` in [`src/models.py`](../../../src/models.py), find `source: str = "mock-strands-agent"` and change the default to reflect the real agent:

```python
# Before:
source: str = "mock-strands-agent"

# After:
source: str = "strands-base-agent"
```

### 5.4 Update `compose.yaml` to remove mock-strands-agent

Edit the worker's [`compose.yaml`](../../../compose.yaml) and delete two blocks. Leave the rest of the file as it is, including the `TEMPORAL_TLS_*` and `FOUNDRY_AGENT_BEARER_TOKEN` lines: the worker won't start without its Temporal client authentication settings, and the agent key reaches the worker through `FOUNDRY_AGENT_BEARER_TOKEN`.

1. The worker's dependency on the mock agent, at the end of the `worker` service:

   ```yaml
   depends_on:
     mock-strands-agent:
       condition: service_started
   ```

2. The whole `mock-strands-agent` service, from `# Mock Strands Agent for local development only` down to its `restart: unless-stopped` line.

The file then reads:

```yaml
services:
  # Temporal Worker
  worker:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      - TEMPORAL_HOST=${TEMPORAL_HOST:-host.docker.internal:7233}
      - TEMPORAL_NAMESPACE=default
      - TASK_QUEUE=${TASK_QUEUE:-workflow-task-queue}
      # Local dev only: the compose Temporal server is plaintext, so no application
      # TLS is negotiated. "platform" asserts TLS is terminated by the deployment
      # platform / service mesh. Deployed environments MUST set this explicitly to
      # match their actual transport posture ("tls" or "mtls" when the application
      # terminates TLS itself) rather than inheriting this value.
      - TEMPORAL_TLS_MODE=${TEMPORAL_TLS_MODE:-platform}
      # Engine client authentication (required at startup, independent of
      # TEMPORAL_TLS_MODE — see env.template). Local dev placeholders: under
      # "platform" mode these paths are never read, so no real certificate
      # material is needed here. Deployed environments MUST replace these
      # with real mTLS material (or TEMPORAL_AUTH_* OAuth2 settings instead).
      - TEMPORAL_TLS_CERT=${TEMPORAL_TLS_CERT:-/dev-placeholder/client.pem}
      - TEMPORAL_TLS_KEY=${TEMPORAL_TLS_KEY:-/dev-placeholder/client.key}
      # Bearer token for agent calls (see env.template). The mock agent does not
      # check it, so it may stay empty locally. Deployed agents usually require it.
      - FOUNDRY_AGENT_BEARER_TOKEN=${FOUNDRY_AGENT_BEARER_TOKEN:-}
      - WORKER_IDENTITY=docker-worker-1
      - LOG_LEVEL=INFO
    networks:
      - temporal-network
    restart: unless-stopped

networks:
  temporal-network:
```

> **Important**: The real Strands Base Agent runs independently in its own compose stack, so the worker no longer starts or waits for an agent container.

### 5.5 Give the worker the agent's API key

Open the worker's `.env`, which you created from `env.template` in the [Getting Started Guide](end-to-end-how-to-getting-started.md). `env.template` ships the setting commented out as `#FOUNDRY_AGENT_BEARER_TOKEN=your-agent-token`. Uncomment it and set it to the key from [step 2.2](#22-generate-the-agents-api-key), the same value as the agent's `STRANDS_API_KEY`:

```env
FOUNDRY_AGENT_BEARER_TOKEN=<the key you generated in step 2.2>
```

> **How it reaches the worker**: `compose.yaml` passes `FOUNDRY_AGENT_BEARER_TOKEN=${FOUNDRY_AGENT_BEARER_TOKEN:-}` to the container, and Docker Compose fills in `${...}` values from the `.env` file in the project folder. A `FOUNDRY_AGENT_BEARER_TOKEN` set in your shell takes precedence over `.env`. The worker's `call_strands_agent` activity sends the value as `Authorization: Bearer <key>` on every agent call. Without it, the agent answers `401`.

---

## Step 6 — Rebuild and Restart the Worker

```bash
cd ~/temporal-stack/temporal-workflow-worker-starter

# Rebuild to pick up code changes
docker compose build worker

# Restart the worker
docker compose up -d worker
```

### 6.1 Verify the worker

```bash
# Check worker logs for successful startup
docker compose logs -f worker
```

Look for:
- `Loaded workflow: MyWorkflow from src.workflows`
- `Loaded activity: my_activity from src.activities`
- `Temporal worker started successfully`

Press `Ctrl+C` to stop following logs.

---

## Step 7 — Verify End-to-End with the Real Agent

### 7.1 Check all services

```bash
echo "--- Temporal UI ---"
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8233

echo "--- Workflow API ---"
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/health

echo "--- Strands Base Agent ---"
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8081/api/v1/health
```

In PowerShell:

```powershell
echo "--- Temporal UI ---"
curl.exe -s -o NUL -w "HTTP %{http_code}\n" http://localhost:8233

echo "--- Workflow API ---"
curl.exe -s -o NUL -w "HTTP %{http_code}\n" http://localhost:8000/health

echo "--- Strands Base Agent ---"
curl.exe -s -o NUL -w "HTTP %{http_code}\n" http://localhost:8081/api/v1/health
```

All three should return `HTTP 200`.

### 7.2 Start a test workflow

The curl example below reads `$API_AUTH_TOKEN` from your shell. If you started a new
terminal since the [Getting Started Guide](end-to-end-how-to-getting-started.md),
export it again first:

```bash
export API_AUTH_TOKEN=local-dev-token-replace-with-32-chars
```

In PowerShell:

```powershell
$env:API_AUTH_TOKEN = "local-dev-token-replace-with-32-chars"
```

```bash
curl -X POST http://localhost:8000/workflows/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -d '{
    "workflow_type": "MyWorkflow",
    "workflow_id": "test-real-agent-001",
    "input_data": {"user_name": "Developer", "task_type": "greeting", "language": "en"}
  }'
```

In PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/workflows/start `
  -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer $env:API_AUTH_TOKEN" } `
  -Body '{
    "workflow_type": "MyWorkflow",
    "workflow_id": "test-real-agent-001",
    "input_data": {"user_name": "Developer", "task_type": "greeting", "language": "en"}
  }'
```

### 7.3 Monitor in Temporal UI

1. Open `http://localhost:8233`
2. Select the **default** namespace
3. Find your workflow `test-real-agent-001`
4. Observe the execution history — Step 2 should now show a real LLM-generated response instead of the canned mock response

### 7.4 Check agent logs

```bash
cd ~/temporal-stack/strands-base-agent
just logs
```

You should see incoming A2A JSON-RPC requests being processed by the Strands agent.

---

## Updated Architecture

```
┌─────────────────────┐       ┌──────────────────────────┐
│   Workflow API       │       │   Temporal Server         │
│   (FastAPI)          │──────▶│   (Temporal dev server)   │
│   localhost:8000     │       │   gRPC: localhost:7233    │
└─────────────────────┘       │   UI:   localhost:8233    │
                               └──────────┬───────────────┘
                                          │
                               ┌──────────▼───────────────┐
                               │   Workflow Worker         │
                               │   (temporal-network)      │
                               │   Polls task queue        │
                               └──────────┬───────────────┘
                                          │ host.docker.internal:8081
                               ┌──────────▼───────────────┐
                               │   Strands Base Agent      │
                               │   (AWS Bedrock LLM)       │
                               │   localhost:8081          │
                               │   A2A JSON-RPC 2.0       │
                               └──────────────────────────┘
```

---

## Updated Service Reference

| Item | Value |
|---|---|
| Repository | [`strands-base-agent/`](https://github.com/boozallen/strands-base-agent) |
| Compose file | [`strands-base-agent/compose.yaml`](https://github.com/boozallen/strands-base-agent/blob/HEAD/compose.yaml) (default) |
| Environment file | `strands-base-agent/.env` |
| Health endpoint | `http://localhost:8081/api/v1/health` |
| A2A endpoint | `http://localhost:8081/` (JSON-RPC 2.0) |
| Query endpoint | `http://localhost:8081/api/v1/query` |
| Worker → Agent URL | `http://host.docker.internal:8081` |

---

## Common Operations

### View Strands Base Agent logs

```bash
cd ~/temporal-stack/strands-base-agent
just logs
```

### Stop the Strands Base Agent

```bash
cd ~/temporal-stack/strands-base-agent
just down
```

### Restart everything (with real agent)

First start the Temporal Server in its own terminal, and wait until it prints
`Temporal Server:      0.0.0.0:7233`:

```bash
temporal server start-dev --ip 0.0.0.0
```

Then, in another terminal:

```bash
# 1. Start Strands Base Agent
cd ~/temporal-stack/strands-base-agent
just up

# 2. Start Worker (no mock agent — real agent is external)
cd ~/temporal-stack/temporal-workflow-worker-starter
docker compose up -d

# 3. Start API
cd ~/temporal-stack/temporal-workflow-api-starter
docker compose up -d
```

### Switch back to mock agent

If you need to switch back to the mock agent (e.g., for offline development):

1. Stop the [Strands Base Agent](https://github.com/boozallen/strands-base-agent/blob/HEAD/docs/foundry/index.md):

   ```bash
   cd ~/temporal-stack/strands-base-agent
   just down
   ```

2. Restore the worker's own [`compose.yaml`](../../../compose.yaml), `config/` and `src/` files, which brings back the [`mock-strands-agent`](../../../mock-strands-agent/) service and the `mock_strands_agent` entry, and rebuild. This discards every change you made to those files, including the [Advanced guide's](end-to-end-how-to-advanced.md) if you followed it. The mock agent ignores the `FOUNDRY_AGENT_BEARER_TOKEN` in `.env`, so that line can stay.

   ```bash
   cd ~/temporal-stack/temporal-workflow-worker-starter
   git checkout -- compose.yaml config/ src/
   docker compose up -d --build
   ```

---

## Troubleshooting

### AWS credentials not found

```
botocore.exceptions.NoCredentialsError: Unable to locate credentials
```

- Ensure `~/.aws` contains valid credentials or SSO configuration
- Verify your AWS profile name matches `AWS_PROFILE` in the `.env` file
- If using SSO, refresh your session: `aws sso login --profile <your-profile>`

### Bedrock model access denied

```
AccessDeniedException: You don't have access to the model
```

- Verify [Bedrock](https://aws.amazon.com/bedrock/) model access is enabled in the AWS Console for your region
- Check that the model ID the agent uses is available in your account: `model.model_id` in its `config.yaml`, or `STRANDS__MODEL__MODEL_ID` in `.env` if you set that override
- Request model access at: AWS Console → Bedrock → Model Access

### Agent container fails to start

```bash
# Check container logs for errors
cd ~/temporal-stack/strands-base-agent
docker compose logs strands-agent
```

Common causes:
- Empty `STRANDS_API_KEY` — the log says `STRANDS_API_KEY is required and must be non-empty`. Set it in `.env` ([step 2.3](#23-edit-the-env-file)) and run `just up` again
- Missing `~/.aws` directory — ensure AWS CLI is configured

### Worker cannot reach the agent

```
ConnectionError: Cannot connect to host.docker.internal:8081
```

1. Verify the agent is running and healthy:

   ```bash
   curl http://localhost:8081/api/v1/health
   ```

   In PowerShell:

   ```powershell
   curl.exe http://localhost:8081/api/v1/health
   ```

2. Verify `host.docker.internal` resolves from inside the worker container (the worker image has Python but not curl):

   ```bash
   docker compose exec worker python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:8081/api/v1/health').read().decode())"
   ```

3. Ensure [`config/services.yaml`](../../../config/services.yaml) uses `http://host.docker.internal:8081` (not `localhost` — `localhost` inside a container refers to the container itself, not the host machine)

### Agent answers 401 Unauthorized

The worker's logs show the agent call failing with `401` (an `AgentAuthenticationFailure`, which isn't retried). The worker sent no key, or a different one. Check that `FOUNDRY_AGENT_BEARER_TOKEN` in the worker's `.env` ([step 5.5](#55-give-the-worker-the-agents-api-key)) equals `STRANDS_API_KEY` in the agent's `.env`, and that your shell doesn't set a different `FOUNDRY_AGENT_BEARER_TOKEN`. Then recreate the worker with `docker compose up -d worker`.

### Agent responds slowly or times out

The real Strands Base Agent calls AWS Bedrock, which is slower than the mock agent. If you see timeouts:

- The default `start_to_close_timeout` in the workflow is `5 minutes` — this should be sufficient
- The `heartbeat_timeout` is `30 seconds` — the `call_strands_agent` activity sends periodic heartbeats automatically
- If needed, increase timeouts in [`src/workflows.py`](../../../src/workflows.py) for your use case
- Check Bedrock service health in the AWS Console

### Private PyPI package errors

If you see import errors for [`foundry-temporal`](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/packages/foundry-temporal/index.md) or [`foundry-temporal-agents`](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/packages/foundry-temporal-agents/index.md), these packages are hosted on a private index. Ensure your network can reach the index configured in [`pyproject.toml`](../../../pyproject.toml), or configure your own index.

---

## Advanced

Ready to build multi-phase workflows with human-in-the-loop feedback loops? Continue with:

- **[End-to-End Advanced](end-to-end-how-to-advanced.md)** — Replace the simple 3-step workflow with a loop-based research workflow featuring HIL signals, iteration tracking, and versioned document keys

## What's Next

1. **Customize the agent** — Configure its system prompt, tools, and capabilities in the agent's [`config.yaml`](https://github.com/boozallen/strands-base-agent/blob/HEAD/config.yaml)
2. **Add custom tools** — Create tool modules for the Strands agent (see the agent's [Adding Tools](https://github.com/boozallen/strands-base-agent/blob/HEAD/docs/foundry/guides/adding-tools.md) guide)
3. **[Customization Guide](customization-guide.md)** — Replace template workflows and activities with your business logic
4. **[Deployment Guide](../operations/deployment.md)** — Production deployment patterns for all services
5. **[Strands Base Agent Docs](https://github.com/boozallen/strands-base-agent/blob/HEAD/docs/foundry/index.md)** — Full agent configuration and extension reference
