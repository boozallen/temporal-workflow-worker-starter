# Customization Guide

This guide explains how to customize the Temporal Workflow Worker Starter template for your team's specific requirements. The template uses a **configuration-driven architecture** with a **3-step workflow pattern** and **clean foundry integration**.

## Template Philosophy

This template follows the **"fork and customize"** approach:
- **Fork the template** as a starting point for your project
- **Customize everything** to match your team's needs
- **Configuration-driven**: Use YAML files for workflows, activities, and services
- **Clean architecture**: No unused code, proper separation of concerns
- **The template is yours** - make it work for your use case

## Core Customizations

### 1. Workflows (`src/workflows.py`)

The template provides `MyWorkflow` in [`src/workflows.py`](../../../src/workflows.py), demonstrating a 3-step pattern. Replace with your business logic:

```python
from temporalio import workflow
from foundry_temporal.signals import HILSignalsMixin
from temporalio.workflow import execute_activity

@workflow.defn
class YourCustomWorkflow(HILSignalsMixin):
    """Replace MyWorkflow with your actual workflow logic."""

    def __init__(self) -> None:
        super().__init__()  # Initialize HILSignalsMixin for approval patterns
        self._status = "initialized"
        self._progress = 0

    @workflow.run
    async def run(self, input_data: YourWorkflowInput) -> YourWorkflowResult:
        # STEP 1: Your initial processing activity
        step1_result = await execute_activity(
            "your_processing_activity",
            args=[input_data.dict()],
            start_to_close_timeout=timedelta(minutes=5)
        )

        # STEP 2: Agent call using configuration-driven services
        service_config = get_service_config("your_agent_service")
        agent_url = service_config["url"]
        agent_result = await execute_activity(
            "call_strands_agent",
            args=[agent_url, your_prompt, query_data],
            retry_policy=STRANDS_AGENT_RETRY_POLICY
        )

        # STEP 3: Optional approval step (remove if not needed)
        await workflow.wait_condition(
            lambda: self.approved,
            timeout=timedelta(minutes=10)
        )

        return YourWorkflowResult(
            success=True,
            message="Workflow completed successfully",
            data=combined_results
        )
```

**Key customizations**:
- Replace `MyWorkflow` with your domain-specific workflow class
- Update the 3-step pattern to match your business process
- Define your input/output models in [`models.py`](../../../src/models.py)
- Configure services in [`config/services.yaml`](../../../config/services.yaml)
- Remove HITL patterns if you don't need approval workflows

### 2. Activities (`src/activities.py`)

Replace `my_activity` in [`src/activities.py`](../../../src/activities.py) with your actual operations:

```python
from temporalio import activity
from .models import YourActivityResult

@activity.defn
async def your_processing_activity(data: dict[str, Any]) -> dict[str, Any]:
    """Replace my_activity with your business logic."""
    logger = activity.logger
    start_time = time.time()

    # Your processing logic here
    processed_data = process_your_data(data)

    processing_time = time.time() - start_time

    result = YourActivityResult(
        success=True,
        message=f"Processed {data.get('type', 'data')} successfully",
        data=processed_data,
        processing_time=processing_time,
        timestamp=datetime.utcnow().isoformat()
    )

    return result.dict()

# Note: Agent calls use foundry-temporal-agents call_strands_agent activity directly
# No custom decorators needed - configure agent URLs in config/services.yaml
```

**Key customizations**:
- Rename activities to match your operations
- Replace `MyActivityResult` with your result models
- Add domain-specific processing logic
- Configure timeout and retry policies in [`config/activities.yaml`](../../../config/activities.yaml)

### 3. Configuration Files

#### Workflows Registration (`config/workflows.yaml`)

Update workflow registration in [`config/workflows.yaml`](../../../config/workflows.yaml):

```yaml
# Register your workflows
workflows:
  - module: "src.workflows"
    classes:
      - "YourCustomWorkflow"
      - "YourSecondWorkflow"  # Add more as needed
```

#### Activities Registration (`config/activities.yaml`)

Update activity registration:

```yaml
# Register your activities
activities:
  - module: "src.activities"
    functions:
      - "your_processing_activity"
      - "your_validation_activity"
  - module: "foundry_temporal_agents"
    functions:
      - name: "call_strands_agent"
        timeout_seconds: 300
```

#### Services Configuration (`config/services.yaml`)

Configure your external services:

```yaml
# Replace mock agent with your actual services
your_agent_service:
  url: "https://your-agent.example.com"
  description: "Your production agent service"

your_database_service:
  url: "postgresql://localhost:5432/yourdb"
  description: "Your database connection"

your_api_service:
  url: "https://api.your-service.com"
  description: "Your external API service"
```

#### Agent Calls (`call_strands_agent`)

The `call_strands_agent` activity from [`foundry-temporal-agents`](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/packages/foundry-temporal-agents/index.md) has a few behaviors to plan for when you customize the workflow.

- **Authentication**: set `FOUNDRY_AGENT_BEARER_TOKEN` for any agent that checks credentials. Without it, requests go out unauthenticated and the worker logs a warning.
- **Retries**: `STRANDS_AGENT_RETRY_POLICY` retries only transient failures, such as an unreachable agent. Authentication failures, `404` responses, other rejected requests and tasks the agent reports as failed are not retried, so the workflow fails on the first attempt.
- **Input limits**: `query_extra_data` must stay within 32 keys, 128-character keys and 512 KiB serialized. `MyWorkflow` passes the whole `my_activity` result in it, so keep that result small or pass a reference instead. A larger value fails the step without a retry. The `FOUNDRY_TEMPORAL_AGENTS_MAX_DICT_*` environment variables adjust these limits.
- **Transport**: `FOUNDRY_TLS_MODE` sets TLS for agent calls, separate from `TEMPORAL_TLS_MODE`. See [`env.template`](../../../env.template).

### 4. Worker Configuration (`src/worker.py`)

The worker ([`src/worker.py`](../../../src/worker.py)) uses configuration-driven approach - **no changes needed** unless adding custom logic:

```python
# Worker automatically loads from config files:
# - config/workflows.yaml
# - config/activities.yaml
# - config/services.yaml

# Only customize if you need additional worker-level configuration
```

### 5. Application Configuration (`src/config.py`)

Add your application-specific settings to `AppConfig` in [`src/config.py`](../../../src/config.py):

```python
class AppConfig(BaseSettings):
    # Core Temporal configuration (keep these)
    temporal_host: str = Field(default="localhost:7233")
    temporal_namespace: str = Field(default="default")
    task_queue: str = Field(default="workflow-task-queue")
    worker_identity: str = Field(default="foundry-worker")

    # Add your custom configuration
    your_api_key: str = Field(description="Your service API key")
    your_database_url: str = Field(description="Database connection URL")
    your_timeout_seconds: int = Field(default=30, description="Default timeout")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
```

### 6. Data Models (`src/models.py`)

Define your domain-specific models:

```python
from pydantic import BaseModel
from typing import Dict, Any, Optional

class YourWorkflowInput(BaseModel):
    """Input model for your workflow."""
    user_id: str
    task_type: str
    parameters: Dict[str, Any] = {}
    priority: int = 1

class YourWorkflowResult(BaseModel):
    """Result model for your workflow."""
    success: bool
    message: str
    data: Dict[str, Any] = {}
    processing_time: Optional[float] = None

class YourActivityResult(BaseModel):
    """Result model for your activity."""
    success: bool
    message: str
    data: Dict[str, Any] = {}
    processing_time: float
    timestamp: str
```

## Advanced Customizations

### Service Integration Patterns

Access configured services in workflows:

```python
from .services import get_service_config

# In your workflow
service_config = get_service_config("your_api_service")
api_url = service_config["url"]

# Pass to activity
result = await execute_activity(
    "call_external_api",
    args=[api_url, request_data],
    start_to_close_timeout=timedelta(minutes=2)
)
```

### Human-in-the-Loop (HITL) Patterns

Customize approval workflows:

```python
@workflow.defn
class YourApprovalWorkflow(HILSignalsMixin):
    @workflow.run
    async def run(self, input_data: ApprovalInput) -> ApprovalResult:
        # Do processing
        processing_result = await execute_activity("process_request", args=[input_data])

        # Wait for approval with custom timeout
        try:
            await workflow.wait_condition(
                lambda: self.approved,
                timeout=timedelta(hours=24)  # 24-hour approval window
            )
            return ApprovalResult(approved=True, result=processing_result)
        except asyncio.TimeoutError:
            return ApprovalResult(approved=False, reason="Approval timeout")

    @workflow.signal
    def reject(self, reason: str) -> None:
        """Custom rejection signal"""
        self._rejected = True
        self._rejection_reason = reason

    @workflow.query
    def get_approval_status(self) -> dict:
        """Query approval status"""
        return {
            "approved": self.approved,
            "rejected": getattr(self, '_rejected', False),
            "reason": getattr(self, '_rejection_reason', None)
        }
```

### Multi-Step Workflows

Extend the 3-step pattern:

```python
@workflow.defn
class YourMultiStepWorkflow(HILSignalsMixin):
    @workflow.run
    async def run(self, input_data: MultiStepInput) -> MultiStepResult:
        results = []

        # Step 1: Data validation
        validation_result = await execute_activity(
            "validate_input", args=[input_data]
        )
        results.append(validation_result)

        # Step 2: External service call
        service_result = await execute_activity(
            "call_external_service", args=[input_data, validation_result]
        )
        results.append(service_result)

        # Step 3: Agent processing
        agent_result = await execute_activity(
            "call_strands_agent",
            args=[agent_url, prompt, context]
        )
        results.append(agent_result)

        # Step 4: Data persistence
        persistence_result = await execute_activity(
            "save_results", args=[results]
        )
        results.append(persistence_result)

        # Step 5: Optional approval
        if input_data.requires_approval:
            await workflow.wait_condition(lambda: self.approved)

        return MultiStepResult(
            success=True,
            steps_completed=len(results),
            results=results
        )
```

## Testing Customizations

Update tests for your workflows:

```python
# tests/unit/test_your_workflows.py
import pytest
from src.workflows import YourCustomWorkflow
from src.models import YourWorkflowInput

class TestYourCustomWorkflow:
    @pytest.mark.asyncio
    async def test_workflow_success(self):
        """Test successful workflow execution."""
        # Test your workflow with mock activities
        pass

    @pytest.mark.asyncio
    async def test_workflow_approval_timeout(self):
        """Test workflow behavior when approval times out."""
        pass
```

## Deployment Customization

### Docker Environment

Update [`compose.yaml`](../../../compose.yaml) for your services:

```yaml
services:
  worker:
    # Worker configuration stays the same
    environment:
      - TEMPORAL_HOST=${TEMPORAL_HOST:-host.docker.internal:7233}
      - TASK_QUEUE=${TASK_QUEUE:-your-workflow-queue}
      - WORKER_IDENTITY=your-worker-1
      # Add your custom environment variables
      - YOUR_API_KEY=${YOUR_API_KEY}
      - YOUR_DATABASE_URL=${YOUR_DATABASE_URL}

  your-agent:
    image: your-registry/your-agent:latest
    ports:
      - "8080:8080"
    environment:
      - LOG_LEVEL=INFO
    # Replace mock-strands-agent with your actual agent

  your-database:
    image: postgres:15
    environment:
      POSTGRES_DB: your_app_db
      POSTGRES_USER: your_user
      POSTGRES_PASSWORD: your_password
```

### Environment Variables

Update `env.template`:

```bash
# Core Temporal configuration
TEMPORAL_HOST=localhost:7233
TEMPORAL_NAMESPACE=default
TASK_QUEUE=your-workflow-queue
WORKER_IDENTITY=your-worker

# Your application configuration
YOUR_API_KEY=your-secret-key
YOUR_DATABASE_URL=postgresql://localhost:5432/yourdb
YOUR_SERVICE_URL=https://your-service.com
```

## Migration Path

When customizing, follow this order:

1. **Run template as-is**: Verify the 3-step workflow works
2. **Update models**: Define your input/output data models
3. **Update [services.yaml](../../../config/services.yaml)**: Configure your actual services
4. **Replace MyWorkflow**: Implement your business workflow
5. **Replace my_activity**: Add your business activities
6. **Update configuration files**: Register your workflows/activities
7. **Update tests**: Test your customizations
8. **Update deployment**: Configure production environment

## Best Practices

### 1. Configuration-Driven Development
- Define services in [`config/services.yaml`](../../../config/services.yaml)
- Use `get_service_config()` to access service URLs
- Keep environment variables minimal (only essential config)

### 2. Clean Architecture
- Separate concerns: workflows orchestrate, activities execute
- Use proper data models with Pydantic validation
- Keep foundry integration clean (no custom wrappers)

### 3. HITL Patterns
- Use `HILSignalsMixin` for approval workflows
- Set appropriate timeouts for human interactions
- Provide query methods for workflow status

### 4. Testing Strategy
- Test workflows with mocked activities
- Test activities in isolation
- Use integration tests for full workflow execution

### 5. Error Handling
- Configure retry policies in [`config/activities.yaml`](../../../config/activities.yaml)
- Use proper error handling in activities
- Log errors with sufficient context for debugging

Remember: This template provides a clean, configuration-driven foundation - customize it completely to fit your team's needs!
