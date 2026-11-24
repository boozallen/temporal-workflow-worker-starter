# Deployment Guide

This guide covers deploying your customized Temporal workflow worker from development to production environments. The template uses a **configuration-driven architecture** with **clean integration with the foundry packages** from [Temporal Packages](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/index.md) and **patterns you can adapt for production**.

## Deployment Overview

The template is designed for containerized deployment using Docker. After customizing the template for your needs, you'll typically deploy:

1. **Temporal Worker** ([`src/worker.py`](../../../src/worker.py)) - Your customized workflow worker with 3-step patterns
2. **[Temporal Server](https://github.com/temporalio/temporal)** - Temporal orchestration engine (shared or dedicated)
3. **Database** - PostgreSQL for Temporal persistence
4. **Strands Agents** - Your custom agents (replace [`mock-strands-agent`](../../../mock-strands-agent/))
5. **Supporting Services** - Any custom services your workflows require

### Minimum Temporal Server Version

This template does not ship a Temporal Server (`compose.yaml` runs only the worker
and mock agent) - whichever server you point it at should be at least 1.28.4 on
the 1.28.x line, 1.29.6 on 1.29.x, or 1.30.4 on 1.30.x. Those versions fix two
advisories: an AdminService authorization bypass (CVE-2026-5724, fixed in 1.28.4 /
1.29.6 / 1.30.4; Temporal Cloud is not affected) and a cross-namespace workflow
signal/delete/reset issue affecting 1.29.0+ (CVE-2026-5199, fixed in 1.29.5 /
1.30.3). Namespace-per-tenant isolation in a shared cluster relies on running a
server version that has both fixes.

## Environment Strategy

### Development Environment
- **Docker Compose**: Complete stack with the mock agent and worker
- **Mixed Mode**: Services in Docker, worker running locally for debugging
- **Configuration**: Uses [`config/services.yaml`](../../../config/services.yaml) with mock services
- **Purpose**: Development and testing the 3-step workflow pattern

### Staging Environment
- **Containerized deployment** with real agents and services
- **Shared Temporal cluster** or dedicated staging cluster
- **Configuration**: Production services in [`config/services.yaml`](../../../config/services.yaml)
- **Purpose**: Integration testing and validation

### Production Environment
- **Kubernetes deployment** (recommended) or Docker Swarm
- **Dedicated Temporal cluster** for reliability and isolation
- **Production agents** and external service integrations
- **Configuration**: Production services and scaling settings
- **Purpose**: Live workload processing with HITL workflows

## Containerization

### Current Dockerfile

The template includes a multi-stage [Dockerfile](../../../Dockerfile) that runs the worker as a non-root user:

```dockerfile
# Multi-stage build for optimal image size.
# Public Chainguard Python dev image (currently Python 3.15).
# `latest-dev` is the floating tag offered in the free public catalog.
FROM cgr.dev/chainguard/python:latest-dev AS base

USER root

# Install system dependencies and create the non-root runtime user
RUN apk update && apk add --no-cache ca-certificates \
    && /usr/sbin/update-ca-certificates \
    && mkdir -p /app/sessions/session_default \
    && addgroup -g 777 agentuser \
    && adduser -u 777 -G agentuser -h /home/agentuser -D agentuser

FROM base AS builder

# Copy uv for dependency management (teams may use different registries)
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

# Copy application code and configuration
COPY src/ ./src/
COPY tests/ ./tests/
COPY config/ ./config/

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

# Create necessary directories, set ownership, and switch to the non-root user
RUN mkdir -p /app/logs /app/data \
    && chown -R agentuser:agentuser /app /app/logs /app/data
USER agentuser
WORKDIR /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import sys; from src.config import get_config; get_config(); sys.exit(0)"

# Base image sets ENTRYPOINT ["python"]; clear it so CMD runs directly
ENTRYPOINT []
CMD ["python", "-m", "src.worker"]
```

### Build Process

If your organization terminates outbound TLS at an inspecting proxy, `apk update` and
`uv sync` will fail inside the build with certificate verification errors. Add your own
root CA to the build context and copy it into the image's trust store in the `base`
stage, before any step that makes an HTTPS request.

```bash
# Build the worker image
docker build -t your-registry/your-workflow-worker:latest .

# Push to registry
docker push your-registry/your-workflow-worker:latest
```

## Kubernetes Deployment

### Worker Deployment

```yaml
# k8s/worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: temporal-worker
  labels:
    app: temporal-worker
    version: v1
spec:
  replicas: 3
  selector:
    matchLabels:
      app: temporal-worker
  template:
    metadata:
      labels:
        app: temporal-worker
        version: v1
    spec:
      containers:
      - name: worker
        image: your-registry/your-workflow-worker:latest
        env:
        - name: TEMPORAL_HOST
          value: "temporal-server:7233"
        - name: TEMPORAL_NAMESPACE
          value: "production"
        - name: TASK_QUEUE
          value: "your-production-queue"
        - name: WORKER_IDENTITY
          valueFrom:
            fieldRef:
              fieldPath: metadata.name
        - name: LOG_LEVEL
          value: "INFO"
        # Add your custom environment variables
        envFrom:
        - secretRef:
            name: temporal-worker-secrets
        - configMapRef:
            name: temporal-worker-config
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          exec:
            command:
            - python
            - -c
            - "from src.config import get_config; get_config(); print('healthy')"
          initialDelaySeconds: 60
          periodSeconds: 30
          timeoutSeconds: 10
        readinessProbe:
          exec:
            command:
            - python
            - -c
            - "from src.config import get_config; get_config(); print('ready')"
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
        volumeMounts:
        - name: config
          mountPath: /app/config
          readOnly: true
      volumes:
      - name: config
        configMap:
          name: workflow-config-files
```

### Configuration Management

```yaml
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: temporal-worker-config
data:
  TEMPORAL_NAMESPACE: "production"
  TASK_QUEUE: "your-production-queue"
  LOG_LEVEL: "INFO"
  MAX_CONCURRENT_ACTIVITIES: "100"
  MAX_CONCURRENT_WORKFLOW_TASKS: "50"
  MAX_CONCURRENT_LOCAL_ACTIVITIES: "200"
  MAX_CONCURRENT_NEXUS_TASKS: "10"

---
# k8s/workflow-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: workflow-config-files
data:
  services.yaml: |
    # Production services configuration
    your_production_agent:
      url: "https://your-agent.production.com"
      description: "Production Strands agent"

    your_database_service:
      url: "postgresql://prod-db:5432/yourdb"
      description: "Production database"

  workflows.yaml: |
    workflows:
      - module: "src.workflows"
        classes: ["MyWorkflow"]

  activities.yaml: |
    activities:
      - module: "src.activities"
        functions: ["my_activity"]

---
# k8s/secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: temporal-worker-secrets
type: Opaque
data:
  YOUR_API_KEY: <base64-encoded-api-key>
  YOUR_DATABASE_URL: <base64-encoded-database-url>
  # Add your sensitive configuration
```

## Production Services Configuration

### Replace Mock Agent

Update your production services configuration in `config/services.yaml`:

```yaml
# config/services.yaml (production)
# Replace mock-strands-agent with your actual services
production_strands_agent:
  url: "https://your-agent.production.com"
  description: "Production Strands agent for workflow automation"

backup_strands_agent:
  url: "https://your-agent-backup.production.com"
  description: "Backup Strands agent for failover"

external_api_service:
  url: "https://api.your-service.com/v1"
  description: "External API for data processing"

database_service:
  url: "postgresql://prod-db:5432/workflows"
  description: "Production database for workflow data"
```

### Service Discovery

For dynamic service discovery:

```python
# src/services.py - extend for dynamic discovery
import os
from typing import Dict, Any

def get_service_config(service_name: str, environment: str = None) -> Dict[str, Any]:
    """Get service configuration with environment-specific overrides."""
    services = get_services_config()

    if service_name not in services:
        # Fallback to environment variables
        env_url = os.getenv(f"{service_name.upper()}_URL")
        if env_url:
            return {"url": env_url, "description": f"Environment-configured {service_name}"}
        raise KeyError(f"Service '{service_name}' not found")

    service_config = services[service_name].copy()

    # Environment-specific overrides
    if environment:
        env_key = f"{service_name}_{environment}"
        if env_key in services:
            service_config.update(services[env_key])

    return service_config
```

## Scaling Configuration

### Worker Scaling

```yaml
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: temporal-worker-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: temporal-worker
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
```

### Activity Concurrency Tuning

The template uses clean foundry integration - tune via [AppConfig](../../../src/config.py):

```python
# src/config.py - Production tuning
class AppConfig(BaseSettings):
    # Tune these based on your workload and infrastructure
    max_concurrent_activities: int = Field(default=200, description="Max concurrent activities")
    max_concurrent_workflow_tasks: int = Field(default=100, description="Max concurrent workflow tasks")
    max_concurrent_local_activities: int = Field(default=500, description="Max concurrent local activities")
    max_concurrent_nexus_tasks: int = Field(default=20, description="Max concurrent nexus tasks")

# The worker automatically uses these settings:
# worker_config = WorkerConfig(
#     max_concurrent_activities=app_config.max_concurrent_activities,
#     # ... other settings from AppConfig
# )
```

## Monitoring and Observability

### Structured Logging

The template uses foundry structured logging:

```python
# Already configured in src/worker.py:
# setup_structured_logging(log_level=app_config.log_level)

# Logs include:
# - Workflow execution context
# - Activity timing and results
# - Configuration loading events
# - Error details with structured data
```

### Health Checks

The Dockerfile includes a comprehensive health check:

```bash
# Health check validates:
# 1. Python environment is working
# 2. Configuration can be loaded
# 3. All required modules are importable
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import sys; from src.config import get_config; get_config(); sys.exit(0)"
```

### Monitoring Workflow Progress

Use [Temporal UI](https://docs.temporal.io/web-ui) and queries to monitor the 3-step workflow in [`src/workflows.py`](../../../src/workflows.py):

```python
# MyWorkflow provides built-in queries via HILSignalsMixin
# Access via Temporal UI or programmatically:

# GET /api/v1/namespaces/{namespace}/workflows/{workflowId}/query
# - get_status(): Current workflow status
# - get_progress(): Progress percentage (0-100)
# - approved: Whether approval signal was received
```

## Production Deployment Patterns

### Blue-Green Deployment

```bash
# 1. Deploy new version alongside current
kubectl apply -f k8s/worker-deployment-v2.yaml

# 2. Verify new version is healthy
kubectl rollout status deployment/temporal-worker-v2

# 3. Update service selector to switch traffic
kubectl patch service temporal-worker -p '{"spec":{"selector":{"version":"v2"}}}'

# 4. Monitor for issues, rollback if needed
kubectl patch service temporal-worker -p '{"spec":{"selector":{"version":"v1"}}}'

# 5. Clean up old version after validation
kubectl delete deployment temporal-worker-v1
```

### Configuration Updates

Update configuration without redeployment:

```bash
# Update services configuration
kubectl create configmap workflow-config-files \
    --from-file=config/ \
    --dry-run=client -o yaml | kubectl apply -f -

# Rolling restart to pick up new config
kubectl rollout restart deployment/temporal-worker
```

## CI/CD Pipeline

The template ships no CI workflows. The pipelines below are examples to adapt and commit
into your own fork — nothing here describes automation that already exists in the repo.
Until you add one, `just check` and `just validate-docker` are your verification gates.

### Build and Test Pipeline

```yaml
# .github/workflows/build-and-test.yml
name: Build and Test Workflow Worker
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v4
      with:
        python-version: '3.15'

    - name: Install UV
      run: curl -LsSf https://astral.sh/uv/install.sh | sh

    - name: Install dependencies
      run: |
        uv sync --dev
        source .venv/bin/activate

    - name: Run tests
      run: |
        source .venv/bin/activate
        pytest tests/ --cov=src --cov-report=xml

    - name: Build Docker image
      run: |
        docker build -t temporal-worker:${{ github.sha }} .

    - name: Test Docker image
      run: |
        docker run --rm temporal-worker:${{ github.sha }} python -c "from src.config import get_config; get_config(); print('Docker image OK')"

  security-scan:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - name: Run Trivy vulnerability scanner
      uses: aquasecurity/trivy-action@master
      with:
        image-ref: 'temporal-worker:${{ github.sha }}'
        format: 'sarif'
        output: 'trivy-results.sarif'
```

### Deployment Pipeline

```yaml
# .github/workflows/deploy.yml
name: Deploy Workflow Worker
on:
  push:
    branches: [main]
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production
    steps:
    - uses: actions/checkout@v4

    - name: Build and push image
      run: |
        docker build -t ${{ secrets.REGISTRY }}/temporal-worker:${{ github.sha }} .
        docker push ${{ secrets.REGISTRY }}/temporal-worker:${{ github.sha }}

    - name: Deploy to Kubernetes
      run: |
        # Update image in deployment
        kubectl set image deployment/temporal-worker \
          worker=${{ secrets.REGISTRY }}/temporal-worker:${{ github.sha }}

        # Wait for rollout to complete
        kubectl rollout status deployment/temporal-worker --timeout=300s

        # Verify deployment health
        kubectl wait --for=condition=ready pod -l app=temporal-worker --timeout=300s

    - name: Run smoke tests
      run: |
        # Add smoke tests to verify deployment
        kubectl exec deployment/temporal-worker -- python -c "
        from src.config import get_config
        from src.services import get_service_config
        get_config()
        get_service_config('production_strands_agent')
        print('Deployment verification successful')
        "
```

## Troubleshooting

### Common Issues

1. **Configuration Loading Errors**
   ```bash
   # Check configuration files are mounted correctly
   kubectl exec deployment/temporal-worker -- ls -la /app/config/
   kubectl exec deployment/temporal-worker -- cat /app/config/services.yaml
   ```

2. **Service Discovery Failures**
   ```bash
   # Test service configuration access
   kubectl exec deployment/temporal-worker -- python -c "
   from src.services import get_service_config
   print(get_service_config('your_agent_service'))
   "
   ```

3. **Worker Connection Issues**
   ```bash
   # Check Temporal server connectivity
   kubectl exec deployment/temporal-worker -- python -c "
   from src.config import get_config
   config = get_config()
   print(f'Temporal host: {config.temporal_host}')
   print(f'Namespace: {config.temporal_namespace}')
   "
   ```

4. **HITL Workflow Issues**
   ```bash
   # Check workflow signal handling
   # Use Temporal UI to send approval signals
   # Monitor workflow queries for status updates
   ```

### Debugging Commands

```bash
# View worker logs with structured output
kubectl logs deployment/temporal-worker --tail=100 -f

# Connect to worker container for debugging
kubectl exec -it deployment/temporal-worker -- /bin/bash

# Check configuration loading
kubectl exec deployment/temporal-worker -- python -c "
from src.worker import load_default_configs
workflows, activities, services = load_default_configs()
print('Config loaded successfully')
print('Workflows:', list(workflows.keys()))
print('Activities:', list(activities.keys()))
print('Services:', list(services.keys()))
"

# Monitor workflow execution via Temporal UI
kubectl port-forward service/temporal-ui 8080:8080
# Visit http://localhost:8080
```

## Performance Optimization

### Resource Allocation

Based on the 3-step workflow pattern:

```yaml
# Optimize resource requests/limits based on your workflow characteristics
resources:
  requests:
    memory: "512Mi"  # Base memory for foundry packages
    cpu: "200m"      # Base CPU for workflow orchestration
  limits:
    memory: "2Gi"    # Allow for activity data processing
    cpu: "2000m"     # Allow for concurrent activity execution
```

### Concurrency Tuning

```yaml
# Environment-specific concurrency tuning
env:
- name: MAX_CONCURRENT_ACTIVITIES
  value: "100"  # Tune based on external service capacity
- name: MAX_CONCURRENT_WORKFLOW_TASKS
  value: "50"   # Tune based on Temporal server capacity
- name: MAX_CONCURRENT_LOCAL_ACTIVITIES
  value: "200"  # Higher for fast local operations
```

Remember: Start with the template's defaults and tune based on your production load patterns and infrastructure capacity!
