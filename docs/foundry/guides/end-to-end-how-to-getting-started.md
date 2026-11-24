# End-to-End Setup Guide: Temporal Workflow Templates

This guide walks you through setting up the complete Temporal workflow development environment from scratch. By the end, you will have four services running together:

| Service | URL | Description |
|---|---|---|
| **[Temporal Server](https://github.com/temporalio/temporal)** | `http://localhost:8233` (UI), `localhost:7233` (gRPC) | Open-source Temporal orchestration engine, run by the Temporal CLI's development server |
| **[Workflow Worker](../index.md)** | — (no exposed port, connects to Temporal) | Executes workflows and activities |
| **[Workflow API](https://github.com/boozallen/temporal-workflow-api-starter/blob/HEAD/docs/foundry/index.md)** | `http://localhost:8000` | FastAPI gateway for starting/managing workflows |
| **[Mock Agent](../../../mock-strands-agent/)** | `http://localhost:8081` | Simulated Strands agent for local development |

## Architecture Overview

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
                                          │
                               ┌──────────▼───────────────┐
                               │   Mock Strands Agent      │
                               │   localhost:8081          │
                               └──────────────────────────┘
```

---

## Prerequisites

### macOS (Rancher Desktop)

1. **Rancher Desktop** — provides Docker and Docker Compose
   - Download from [https://rancherdesktop.io](https://rancherdesktop.io)
   - During setup, select **dockerd (moby)** as the container runtime
   - Verify after install:

   ```bash
   docker --version
   docker compose version
   ```

2. **Git**

   ```bash
   git --version
   # If not installed, Xcode Command Line Tools will prompt you — accept the install
   ```

3. **UV package manager** (recommended for dependency management)

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   # The installer puts uv in ~/.local/bin, which isn't on this shell's PATH
   # yet - load it now instead of waiting for a new terminal.
   source $HOME/.local/bin/env
   ```

4. **Python 3.15** ([`pyproject.toml`](../../../pyproject.toml) requires `>=3.15,<3.16`)

   macOS's built-in Python 3 is usually older than 3.15 and this repo never
   uses it anyway - install 3.15 with uv instead:

   ```bash
   uv python install 3.15
   uv python find 3.15
   ```

5. **Just command runner** (optional but recommended — used by both templates)

   ```bash
   brew install just
   ```

6. **Temporal CLI** — runs the local Temporal Server (Step 2)

   ```bash
   brew install temporal
   temporal --version
   ```

### Windows (WSL2)

1. **WSL2 with Ubuntu** — provides a Linux environment for Docker

   ```powershell
   # In PowerShell (Administrator)
   wsl --install -d Ubuntu
   ```

   After reboot, open the Ubuntu terminal and continue there for all remaining steps.

2. **Docker Engine inside WSL2**

   Option A — **Rancher Desktop** (recommended):
   - Install Rancher Desktop for Windows from [https://rancherdesktop.io](https://rancherdesktop.io)
   - In Settings → WSL, enable integration with your Ubuntu distro
   - Select **dockerd (moby)** as the container runtime

   Option B — **Docker Engine directly in WSL2**:

   ```bash
   # Inside WSL2 Ubuntu
   sudo apt update && sudo apt install -y docker.io docker-compose-plugin
   sudo usermod -aG docker $USER
   # Log out and back in for group changes to take effect
   newgrp docker
   ```

3. **Git, Python 3.15, UV, and Just** — install inside WSL2:

   ```bash
   sudo apt update && sudo apt install -y git
   curl -LsSf https://astral.sh/uv/install.sh | sh
   # The installer puts uv in ~/.local/bin, which isn't on this shell's PATH
   # yet - load it now instead of waiting for the shell restart below.
   source $HOME/.local/bin/env
   # Ubuntu's apt python3 is the distro's own version (3.12 on Ubuntu 24.04),
   # not the 3.15 this repo requires - install 3.15 with uv instead.
   uv python install 3.15
   # Install Just
   curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to ~/bin
   echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
   ```

4. **Temporal CLI** — runs the local Temporal Server (Step 2). Download the Linux archive
   (use `arch=arm64` on an ARM machine), extract it, and copy `temporal` onto your PATH:

   ```bash
   curl -sSfL -o temporal.tar.gz "https://temporal.download/cli/archive/latest?platform=linux&arch=amd64"
   tar -xzf temporal.tar.gz temporal
   sudo mv temporal /usr/local/bin/
   rm temporal.tar.gz
   ```

5. **Verify everything**:

   ```bash
   docker --version
   docker compose version
   git --version
   uv --version
   uv python find 3.15
   just --version
   temporal --version
   ```

### Windows (PowerShell)

Everything in this guide also runs from Windows PowerShell, with no WSL2. Where a step's
commands differ in PowerShell, the step gives a PowerShell block after the bash one.

1. **Rancher Desktop** — provides Docker and Docker Compose
   - Install Rancher Desktop for Windows from [https://rancherdesktop.io](https://rancherdesktop.io)
   - Select **dockerd (moby)** as the container runtime

2. **Git, UV, and Just**:

   ```powershell
   winget install --id Git.Git -e
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   winget install --id Casey.Just -e
   ```

   Open a new PowerShell window afterwards, so Git, uv and just are on its PATH.

3. **Python 3.15** ([`pyproject.toml`](../../../pyproject.toml) requires `>=3.15,<3.16`):

   ```powershell
   uv python install 3.15
   ```

4. **Temporal CLI** — runs the local Temporal Server (Step 2). Download the Windows archive
   (use `arch=arm64` on an ARM machine), extract `temporal.exe`, and add its folder to your PATH:

   ```powershell
   Invoke-WebRequest -Uri "https://temporal.download/cli/archive/latest?platform=windows&arch=amd64" -OutFile temporal.zip
   Expand-Archive temporal.zip -DestinationPath "$env:LOCALAPPDATA\Programs\temporal" -Force
   Remove-Item temporal.zip
   [Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "User") + ";$env:LOCALAPPDATA\Programs\temporal", "User")
   ```

   Open a new PowerShell window afterwards, so `temporal` is on its PATH.

5. **Verify everything**:

   ```powershell
   docker --version
   docker compose version
   git --version
   uv --version
   uv python find 3.15
   just --version
   temporal --version
   ```

---

## Step 1 — Clone the Repositories

You need two repositories. Choose a workspace directory and clone them side-by-side:

```bash
# Choose your workspace (adjust to your preference)
mkdir -p ~/temporal-stack
cd ~/temporal-stack

# 1. Workflow Worker Starter template
git clone <your-worker-starter-repo-url> temporal-workflow-worker-starter

# 2. Workflow API Starter template
git clone <your-api-starter-repo-url> temporal-workflow-api-starter
```

In PowerShell (its `mkdir` fails when the folder already exists, so a re-run would stop there):

```powershell
# Choose your workspace (adjust to your preference)
New-Item -ItemType Directory -Force ~/temporal-stack
Set-Location ~/temporal-stack

# 1. Workflow Worker Starter template
git clone <your-worker-starter-repo-url> temporal-workflow-worker-starter

# 2. Workflow API Starter template
git clone <your-api-starter-repo-url> temporal-workflow-api-starter
```

Your directory should look like this:

```
temporal-stack/
├── temporal-workflow-worker-starter/   ← Worker template
└── temporal-workflow-api-starter/      ← API template
```

> **Note**: Use the Git URL of your own fork for each template — this guide assumes you have forked both, since customizing them is the intended workflow. The Temporal Server needs no clone: the Temporal CLI you installed runs it (Step 2).

---

## Step 2 — Start the Temporal Server

The Temporal Server is the backbone. It must be running before the worker or API can connect.
This guide runs it with the Temporal CLI's development server, as
[Temporal's own setup guide](https://learn.temporal.io/getting_started/python/dev_environment/)
recommends for local development.

### 2.1 Start Temporal Server

Open a new terminal, and leave the server running in it while you work through this guide:

```bash
temporal server start-dev --ip 0.0.0.0
```

The command is the same in PowerShell. It starts a local Temporal Server with an in-memory
database, creates the `default` namespace, and serves the Web UI. When it is ready it prints,
among other lines:

```text
Temporal Server:      0.0.0.0:7233
Temporal UI:          http://0.0.0.0:8233
```

> **`--ip 0.0.0.0`**: The worker and API run in containers, which reach the server through
> `host.docker.internal`. With Docker Engine installed directly in Linux or WSL, that
> address can't reach a server on `127.0.0.1`, so `--ip 0.0.0.0` is required. Docker Desktop
> and Rancher Desktop work without it. Leave it off there to keep the server off your
> network. The development server has no authentication, so stop it when you are done (`Ctrl+C`).

> **Tip**: Temporal Server `1.29.6` is the minimum version with fixes for two 2026 security
> advisories - see the [Deployment Guide](../operations/deployment.md#minimum-temporal-server-version)
> for details. `temporal --version` shows the server version your CLI runs
> (`Temporal CLI 1.x.y (Server 1.x.y, UI 2.x.y)`); upgrade the CLI if it is older.

The in-memory database is erased when you stop the server. To keep your workflows between
runs, give it a database file instead, and pass the same file each time:

```bash
temporal server start-dev --ip 0.0.0.0 --db-filename temporal.db
```

### 2.2 Verify Temporal Server is running

In another terminal:

```bash
# Check the server answers
temporal operator cluster health

# Verify Temporal UI is accessible
curl -s -o /dev/null -w "%{http_code}" http://localhost:8233
# Should return 200
```

In PowerShell:

```powershell
# Check the server answers
temporal operator cluster health

# Verify Temporal UI is accessible
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8233
# Should return 200
```

`temporal operator cluster health` prints `SERVING`. Open `http://localhost:8233` in your
browser — you should see the Temporal Web UI.

---

## Step 3 — Set Up and Start the Workflow Worker

The worker template registers workflows and activities with the Temporal Server and executes them when triggered.

### 3.1 Navigate to the worker template

```bash
cd ~/temporal-stack/temporal-workflow-worker-starter
```

### 3.2 Create the environment file

```bash
cp env.template .env
```

Review the `.env` file — the defaults should work for local development:

```env
# .env
TEMPORAL_HOST=host.docker.internal:7233
TEMPORAL_NAMESPACE=default
TASK_QUEUE=workflow-task-queue
WORKER_IDENTITY=worker-1
```

> **`host.docker.internal`**: This is a Docker-provided DNS name that resolves to the host machine. Since the Temporal Server listens on port `7233` on all of the host's addresses (`--ip 0.0.0.0`, Step 2), the worker container uses this address to connect.

### 3.3 Start the worker and mock agent

Using `just` (recommended):

```bash
just start
```

Or using Docker Compose directly:

```bash
docker compose up -d
```

This starts two containers on the worker's own `temporal-network`:

| Container | Purpose | Port |
|---|---|---|
| `worker` | Temporal workflow worker — polls the task queue | — (internal) |
| [`mock-strands-agent`](../../../mock-strands-agent/) | Mock A2A JSON-RPC agent for local development | `8081` (mapped to host) |

### 3.4 Verify the worker

```bash
# Check containers
docker compose ps

# Verify the mock agent health endpoint
curl http://localhost:8081/health
# Expected: {"status":"healthy","agent":"mock-strands-agent",...}

# Check worker logs (should show successful connection to Temporal)
docker compose logs -f worker
```

In PowerShell:

```powershell
# Check containers
docker compose ps

# Verify the mock agent health endpoint
curl.exe http://localhost:8081/health
# Expected: {"status":"healthy","agent":"mock-strands-agent",...}

# Check worker logs (should show successful connection to Temporal)
docker compose logs -f worker
```

In the worker logs, look for messages like:
- `Loaded workflow: MyWorkflow from src.workflows`
- `Loaded activity: my_activity from src.activities`
- `Temporal worker started successfully`

Press `Ctrl+C` to stop following logs.

---

## Step 4 — Set Up and Start the Workflow API

The API template provides a FastAPI REST gateway for starting and managing workflows.

### 4.1 Navigate to the API template

```bash
cd ~/temporal-stack/temporal-workflow-api-starter
```

### 4.2 Create the environment file

```bash
cp env.template .env
```

The [`env.template`](https://github.com/boozallen/temporal-workflow-api-starter/blob/HEAD/env.template) copies with `API_AUTH_TOKEN=` empty. You must set it to a value at least 32 characters long before starting the API. Without it, all `/workflows/*` requests return 503; a shorter token fails config validation at startup.

Review and update the `.env` file:

```env
# .env
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
TEMPORAL_HOST=host.docker.internal:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=workflow-task-queue
API_AUTH_TOKEN=local-dev-token-replace-with-32-chars
```

> **`API_AUTH_TOKEN`**: Required for all `/workflows/*` endpoints, and must be at least 32 characters. Use any string that long for local development.

The value in `.env` only reaches the API container — it is not automatically available
in your own shell. The curl examples below read `$API_AUTH_TOKEN` from your shell, so
export the same value there too:

```bash
export API_AUTH_TOKEN=local-dev-token-replace-with-32-chars
```

In PowerShell:

```powershell
$env:API_AUTH_TOKEN = "local-dev-token-replace-with-32-chars"
```

### 4.3 Start the API service

Using `just` (recommended):

```bash
just start
```

Or using Docker Compose directly:

```bash
docker compose up -d
```

### 4.4 Verify the API

```bash
# Check container status
docker compose ps

# Test API health endpoint
curl http://localhost:8000/health
# Expected: {"status":"healthy",...}

# Test detailed health (includes Temporal connectivity check)
curl http://localhost:8000/health/detailed
```

In PowerShell:

```powershell
# Check container status
docker compose ps

# Test API health endpoint
curl.exe http://localhost:8000/health
# Expected: {"status":"healthy",...}

# Test detailed health (includes Temporal connectivity check)
curl.exe http://localhost:8000/health/detailed
```

Open `http://localhost:8000/docs` in your browser to see the interactive Swagger UI documentation.

---

## Step 5 — Verify the Full Stack

With all three components running, verify end-to-end connectivity:

### 5.1 Check all services

```bash
echo "--- Temporal UI ---"
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8233

echo "--- Workflow API ---"
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/health

echo "--- Mock Agent ---"
curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8081/health
```

In PowerShell:

```powershell
echo "--- Temporal UI ---"
curl.exe -s -o NUL -w "HTTP %{http_code}\n" http://localhost:8233

echo "--- Workflow API ---"
curl.exe -s -o NUL -w "HTTP %{http_code}\n" http://localhost:8000/health

echo "--- Mock Agent ---"
curl.exe -s -o NUL -w "HTTP %{http_code}\n" http://localhost:8081/health
```

All three should return `HTTP 200`.

### 5.2 Start a test workflow via the API

```bash
curl -X POST http://localhost:8000/workflows/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -d '{
    "workflow_type": "MyWorkflow",
    "workflow_id": "test-workflow-001",
    "input_data": {"user_name": "End-to-End Tester", "task_type": "greeting"}
  }'
```

In PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/workflows/start `
  -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer $env:API_AUTH_TOKEN" } `
  -Body '{
    "workflow_type": "MyWorkflow",
    "workflow_id": "test-workflow-001",
    "input_data": {"user_name": "End-to-End Tester", "task_type": "greeting"}
  }'
```

### 5.3 Monitor in Temporal UI

1. Open `http://localhost:8233`
2. Select the **default** namespace
3. You should see your workflow running
4. Click on the workflow to view its execution history, steps, and pending signals

### 5.4 Use Postman collections (optional)

The API template includes pre-configured Postman collections:

1. Import `temporal-workflow-api-starter/postman/API.postman_collection.json` into Postman
2. Import `temporal-workflow-api-starter/postman/Local.postman_environment.json` as an environment
3. Select the **Local** environment and test all endpoints

---

## Common Operations

### View logs

```bash
# Worker logs
cd ~/temporal-stack/temporal-workflow-worker-starter
docker compose logs -f

# API logs
cd ~/temporal-stack/temporal-workflow-api-starter
docker compose logs -f
```

The Temporal Server's logs print in the terminal running `temporal server start-dev`.

### Stop all services

Stop in reverse order — API first, then worker, then Temporal Server:

```bash
# Stop API
cd ~/temporal-stack/temporal-workflow-api-starter
docker compose down

# Stop Worker
cd ~/temporal-stack/temporal-workflow-worker-starter
docker compose down
```

Then stop the Temporal Server with `Ctrl+C` in its terminal. Its in-memory database, and so
your workflow history, goes with it; a server started with `--db-filename` keeps it in that file.

### Reset all services (removes data and volumes)

```bash
# Reset API
cd ~/temporal-stack/temporal-workflow-api-starter
docker compose down -v

# Reset Worker
cd ~/temporal-stack/temporal-workflow-worker-starter
docker compose down -v --remove-orphans
```

Then stop the Temporal Server with `Ctrl+C`; if you started it with `--db-filename`, delete
that file too.

### Clean up template Docker images (for fresh rebuild)

```bash
docker rmi -f temporal-workflow-api-starter-api
docker rmi -f temporal-workflow-worker-starter-mock-strands-agent
docker rmi -f temporal-workflow-worker-starter-worker
```

### Restart everything from scratch

First start the Temporal Server in its own terminal, and wait until it prints
`Temporal Server:      0.0.0.0:7233`:

```bash
temporal server start-dev --ip 0.0.0.0
```

Then, in another terminal:

```bash
# Start Worker
cd ~/temporal-stack/temporal-workflow-worker-starter
just start    # or: docker compose up -d

# Start API
cd ~/temporal-stack/temporal-workflow-api-starter
just start    # or: docker compose up -d
```

---

## Troubleshooting

### Docker Hub Rate Limiting

The templates' images build from `cgr.dev`, but an image you pull from Docker Hub (for example a `python:3.15-slim` base, see [Build failures](#build-failures-base-image-or-tls)) can hit Docker Hub's rate limit from within the network:

```
Error response from daemon: toomanyrequests: You have reached your pull rate limit.
```

This occurs because Docker Hub requests from the network originate from a small set of public IPs, causing unauthenticated requests to quickly hit Docker Hub's daily rate limits.

**Workaround Options:**

1. **Authenticate with Docker Hub** — Users with a Docker license can authenticate to make authenticated pull requests, avoiding the unauthenticated rate limit:

   ```bash
   docker login
   # Enter your Docker Hub credentials
   ```

2. **Retry at different times** — The rate limit resets on a 24-hour basis, so pulling images at different times of day may succeed. Once images are cached locally, this won't be an issue for subsequent runs.

3. **Use a registry mirror** — If your organization runs a Docker Hub pull-through proxy (Nexus, Artifactory, ECR pull-through cache, etc.), pull from it instead of directly from Docker Hub: prefix the image in the Dockerfile's `FROM` line with your mirror's host: `YOUR_REGISTRY_HOST/DOCKER_IMAGE:IMAGE_TAG`.

### Docker is not running

```
ERROR: Cannot connect to the Docker daemon
```

- **macOS**: Open Rancher Desktop and ensure it is running. Check the tray icon.
- **Windows/WSL2**: Ensure Rancher Desktop is running with WSL integration enabled, or start Docker Engine manually: `sudo service docker start`

### Certificate Issues

Behind a corporate proxy that inspects TLS, an image build can fail with a TLS or certificate
error, for example at `apk update` or `pip install`. Add your organization's root CA certificate
to the image that fails, such as the mock agent's
[`mock-strands-agent/Dockerfile`](../../../mock-strands-agent/Dockerfile):

1. Export the root CA from your browser. In Firefox: Settings -> Privacy & Security -> Manage
   certificates, select your organization's root CA, then Export...
2. Save it next to that Dockerfile, for example as `corporate-root-ca.crt`, and make sure it is
   gitignored so you don't commit it.
3. Add these lines to the Dockerfile after its `USER root` line and before the step that fails,
   as the worker's own [`Dockerfile`](../../../Dockerfile) does for its base stage (both images
   build from the Chainguard Python image):

```dockerfile
COPY corporate-root-ca.crt /usr/local/share/ca-certificates/corporate-root-ca.crt
RUN cat /usr/local/share/ca-certificates/corporate-root-ca.crt >> /etc/ssl/certs/ca-certificates.crt
```

### Port conflicts

If you see `bind: address already in use`:

| Port | Used by | Resolution |
|---|---|---|
| `7233` | Temporal gRPC | Stop any other Temporal dev server: `pkill temporal` |
| `8000` | Workflow API | Stop the conflicting process: `lsof -ti:8000 | xargs kill` |
| `8233` | Temporal UI | Stop the conflicting process: `lsof -ti:8233 | xargs kill` |
| `8081` | Mock Agent | Stop the conflicting process: `lsof -ti:8081 | xargs kill` |

### Worker cannot connect to Temporal Server

```
Failed to connect to Temporal server at host.docker.internal:7233
```

1. Verify Temporal Server is running (it prints `SERVING`):

   ```bash
   temporal operator cluster health
   ```

2. With Docker Engine installed directly in Linux or WSL, make sure you started it with
   `--ip 0.0.0.0` (Step 2). Without it the worker container cannot reach the server through
   `host.docker.internal`.
   Stop it with `Ctrl+C` and start it again:

   ```bash
   temporal server start-dev --ip 0.0.0.0
   ```

### API cannot connect to Temporal Server

The API container uses `host.docker.internal:7233` to reach the Temporal Server on the host network. If this doesn't resolve:

- **Rancher Desktop or Docker Desktop** (macOS, Windows and WSL2): `host.docker.internal` is supported by default.
- **Docker Engine installed directly in Linux or WSL2**: add this to your API's [`compose.yaml`](https://github.com/boozallen/temporal-workflow-api-starter/blob/HEAD/compose.yaml):

  ```yaml
  services:
    api:
      extra_hosts:
        - "host.docker.internal:host-gateway"
  ```

### Temporal UI shows no workflows

- Ensure you are viewing the **default** namespace in the Temporal UI
- Verify the worker is registered and connected by checking worker logs
- Start a workflow through the API and refresh the UI

### Build failures (base image or TLS)

The worker [`Dockerfile`](../../../Dockerfile) and the mock agent [`Dockerfile`](../../../mock-strands-agent/Dockerfile) both build from the public Chainguard Python image, so no private registry access is required:

```dockerfile
# Dockerfile
FROM cgr.dev/chainguard/python:latest-dev AS base

# mock-strands-agent/Dockerfile
FROM cgr.dev/chainguard/python:latest-dev
```

If your network blocks `cgr.dev`, point both `FROM` lines at your own registry mirror or another Python base image. Note that the Chainguard image is Alpine-based (`apk`), sets `ENTRYPOINT ["python"]`, and ships a built-in `nonroot` user. Switching to a Debian-based image such as `python:3.15-slim` also means:

- In the worker `Dockerfile`, replacing the `apk`/`addgroup`/`adduser` commands with `apt-get`/`groupadd`/`useradd`.
- In the mock agent `Dockerfile`, creating a `nonroot` user (for example `useradd -r nonroot`), because `COPY --chown=nonroot:nonroot` and `USER nonroot` expect it.
- In both, dropping the `ENTRYPOINT []` reset.

If the build fails during `apk update`, `uv sync`, or the mock agent's `pip install` with a certificate error, you are likely behind a TLS-inspecting proxy. Add your organization's root CA to the build context and copy it into the image's trust store in the `base` stage, before any step that makes an HTTPS request.

### Container logs show `foundry-temporal` or `foundry-temporal-agents` import errors

The [`foundry-temporal`](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/packages/foundry-temporal/index.md) and [`foundry-temporal-agents`](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/packages/foundry-temporal-agents/index.md) packages install from their public GitHub release wheels, which `[tool.uv.sources]` in `pyproject.toml`
names, so the build environment needs to reach github.com but no extra package index.

---

## Service Reference

### Temporal Server (Temporal CLI development server)

| Item | Value |
|---|---|
| Start command | `temporal server start-dev --ip 0.0.0.0` |
| gRPC endpoint | `localhost:7233` |
| Web UI | `http://localhost:8233` |
| Database | In-memory (or the file given with `--db-filename`) |
| Namespace | `default` (created at start-up) |

### Workflow Worker Starter

| Item | Value |
|---|---|
| Compose file | `temporal-workflow-worker-starter/compose.yaml` |
| Environment file | `temporal-workflow-worker-starter/.env` |
| Task queue | `workflow-task-queue` |
| Mock agent | `http://localhost:8081` |
| Docker network | `temporal-network` |
| Available `just` commands | `setup`, `start`, `logs`, `status`, `reset`, `test`, `check` |

### Workflow API Starter

| Item | Value |
|---|---|
| Compose file | `temporal-workflow-api-starter/compose.yaml` |
| Environment file | `temporal-workflow-api-starter/.env` |
| API endpoint | `http://localhost:8000` |
| Swagger docs | `http://localhost:8000/docs` |
| ReDoc docs | `http://localhost:8000/redoc` |
| Available `just` commands | `setup`, `start`, `stop`, `logs`, `dev`, `test`, `check` |

---

## Next Steps

Ready to replace the mock agent with a real LLM-powered [Strands Base Agent](https://github.com/boozallen/strands-base-agent/blob/HEAD/docs/foundry/index.md)? Continue with:

- **[End-to-End Next Steps](end-to-end-how-to-next-steps.md)** — Swap the mock agent for the real [Foundry Strands Base Agent](https://github.com/boozallen/strands-base-agent/blob/HEAD/docs/foundry/index.md) (AWS Bedrock)

## What's Next

Once the full stack is running, continue with:

1. **[Customization Guide](customization-guide.md)** — Replace template workflows and activities with your business logic
2. **[Getting Started (Worker)](../getting-started/getting-started.md)** — Deep dive into the worker template architecture
3. **API Endpoint Docs** — see the API starter's [API Endpoints Reference](https://github.com/boozallen/temporal-workflow-api-starter/blob/HEAD/docs/foundry/endpoints.md), also in the `docs/` directory of the API starter template you cloned in Step 1
4. **[Deployment Guide](../operations/deployment.md)** — Production deployment patterns
5. **[Temporal Documentation](https://docs.temporal.io/)** — Official Temporal concepts and guides
