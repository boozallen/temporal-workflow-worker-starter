# Advanced Guide: Building Complex Workflows with Loops

This guide builds on the [Next Steps Guide](end-to-end-how-to-next-steps.md). You should have the full stack running with the **real [Strands Base Agent](https://github.com/boozallen/strands-base-agent/blob/HEAD/docs/foundry/index.md)** (Temporal Server, [Workflow Worker](../index.md), [Workflow API](https://github.com/boozallen/temporal-workflow-api-starter/blob/HEAD/docs/foundry/index.md), and Strands Base Agent on `localhost:8081`) before proceeding.

> **Prerequisite check**: Verify the three services with a health endpoint are up before continuing (the worker has none; step 6.2 checks its log):
> ```bash
> curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8233       # Temporal UI
> curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8000/health  # Workflow API
> curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8081/api/v1/health # Strands Base Agent
> ```
>
> In PowerShell:
>
> ```powershell
> curl.exe -s -o NUL -w "HTTP %{http_code}\n" http://localhost:8233       # Temporal UI
> curl.exe -s -o NUL -w "HTTP %{http_code}\n" http://localhost:8000/health  # Workflow API
> curl.exe -s -o NUL -w "HTTP %{http_code}\n" http://localhost:8081/api/v1/health # Strands Base Agent
> ```

By the end of this guide you will have replaced the simple 3-step `MyWorkflow` with a **multi-phase, loop-based workflow** that demonstrates production patterns for:

- **Multi-phase orchestration** — sequential workflow phases with distinct loop logic
- **Human-in-the-loop (HIL) feedback loops** — `while` loops that pause for signals and iterate on revisions
- **Iteration tracking** — versioned document keys and counters across loop iterations
- **Multiple signal & query handlers** — per-phase approve/feedback signals, approvals bound to the reviewed content, and real-time status queries
- **Timeout handling** — configurable deadlines inside loops
- **Richer data models** — Pydantic models with validators for workflow I/O

> **Reference implementation**: This guide is modeled on a production HIL Research Workflow — an agent drafts a plan, a human approves or sends it back with feedback, and the same review loop then runs over the research output. Every pattern below is reproduced in full here; you do not need a separate reference repository to follow along.

---

## Architecture: Next Steps vs. Advanced

### Current Setup — Linear 3-Step Workflow (from Next Steps guide)

```
Start ──▶ my_activity ──▶ call_strands_agent ──▶ wait for approval ──▶ End
                          (Strands Base Agent
                           via host.docker.internal:8081)
```

The current `MyWorkflow` executes three steps sequentially with a single approval gate at the end. It uses the real Strands Base Agent you configured in the [Next Steps Guide](end-to-end-how-to-next-steps.md).

### Advanced — Multi-Phase Loop Workflow

```
Start ──▶ ┌─────────────────────────────────┐
          │  Phase 1: Generate Plan          │
          │  ┌───────────────────────────┐   │
          │  │ call_research_agent       │   │
          │  └───────────┬───────────────┘   │
          │              ▼                   │
          │  ┌───────────────────────────┐   │
          │  │ Wait for signal           │◀─┐│
          │  │ (approve or feedback)     │  ││
          │  └───────┬──────────┬────────┘  ││
          │  approved│          │feedback   ││
          │          │          ▼           ││
          │          │  ┌───────────────┐  ││
          │          │  │ Revise plan   │──┘│
          │          │  │ (agent call)  │   │
          │          │  └───────────────┘   │
          └──────────┼─────────────────────┘
                     ▼
          ┌─────────────────────────────────┐
          │  Phase 2: Generate Research      │
          │  (same loop pattern)             │
          └──────────┬──────────────────────┘
                     ▼
                    End
```

Each phase runs an initial agent call, then enters a **`while` loop** that waits for a human signal — either approval (exits the loop) or feedback (triggers a revision and loops again).

### Updated Architecture

```
┌─────────────────────┐       ┌──────────────────────────┐
│   Workflow API       │       │   Temporal Server         │
│   (FastAPI)          │──────▶│   (Temporal dev server)   │
│   localhost:8000     │       │   gRPC: localhost:7233    │
└─────────────────────┘       │   UI:   localhost:8233    │
         │ signals/queries     └──────────┬───────────────┘
         │                                │
         │                     ┌──────────▼───────────────┐
         │                     │   Workflow Worker         │
         └────────────────────▶│   (temporal-network)      │
                               │   ResearchWorkflow        │
                               │   ┌──────────────────┐   │
                               │   │ Plan Loop         │   │
                               │   │  generate → wait  │   │
                               │   │  → revise → wait  │   │
                               │   └──────────────────┘   │
                               │   ┌──────────────────┐   │
                               │   │ Research Loop     │   │
                               │   │  generate → wait  │   │
                               │   │  → revise → wait  │   │
                               │   └──────────────────┘   │
                               └──────────┬───────────────┘
                                          │ host.docker.internal:8081
                               ┌──────────▼───────────────┐
                               │   Strands Base Agent      │
                               │   (AWS Bedrock LLM)       │
                               │   localhost:8081          │
                               │   A2A JSON-RPC 2.0       │
                               └──────────────────────────┘
```

> The Strands Base Agent is the same real agent you configured in the [Next Steps Guide](end-to-end-how-to-next-steps.md). The difference is that the advanced workflow calls it **multiple times per workflow execution** — once per loop iteration — with different task types routed through the same `call_research_agent` activity.

---

## What You Will Build

| Component | File | Description |
|---|---|---|
| **Workflow** | `src/workflows.py` | `ResearchWorkflow` with `generate_plan_loop` and `generate_research_loop` |
| **Activities** | `src/activities.py` | `call_research_agent` activity with task-based routing, built on `foundry-temporal-agents` |
| **Models** | `src/models.py` | `ResearchRequest`, `ResearchResult`, `ModelValidation` with Pydantic validators |
| **Config** | `config/workflows.yaml` | Workflow registration |
| **Config** | `config/activities.yaml` | Activity registration |
| **API** | `temporal-workflow-api-starter/src/routers/workflows.py` | Lets the Workflow API start `ResearchWorkflow` |

---

## Step 1 — Understand the Loop Pattern

The core pattern is a **signal-driven `while` loop** inside a workflow method. Here is the simplified structure:

```python
async def generate_plan_loop(self, request):
    """Generate plan, then loop until a human approves it."""
    self.plan_iterations = 1

    # 1. Initial generation (activity call), then open the plan for review
    plan = await self.ask_agent(request, phase="generating_plan", task_request={...})
    self.open_for_review("plan", plan)

    # 2. HIL approval loop
    while not self.plan_approved:
        # Block until a signal arrives
        await workflow.wait_condition(
            self.is_plan_decision_received,
            timeout=timedelta(hours=24),
        )

        if self.plan_feedback_received and not self.plan_approved:
            # Feedback received — revise and loop again
            feedback = self.plan_feedback_comments
            self.reset_plan_feedback()
            self.plan_iterations += 1
            plan = await self.ask_agent(request, phase="revising_plan", task_request={...})
            self.open_for_review("plan", plan)

    # Loop exits when plan_approved == True
```

**Key mechanics:**

1. **`workflow.wait_condition`** blocks execution until the condition returns `True` — this happens when a signal handler sets the appropriate state.
2. **`HILSignalsMixin`** (from `foundry_temporal.signals`) provides the signal handlers (`approve_plan`, `provide_plan_feedback`, `approve_research`, `provide_feedback`) and the state they set: `plan_approved`, `plan_approved_by`, `plan_feedback_received`, `plan_feedback_comments`, `document_approved`, etc.
3. **`open_for_review`** stores the content, computes its SHA-256 digest, and calls the mixin's `open_plan_review(digest)`. An approval counts only if it carries that digest, so a reviewer can only approve the version they actually read.
4. **`reset_plan_feedback()`** clears the feedback state so the loop can wait for the _next_ decision.
5. **Iteration counters** track how many times the loop has executed, enabling versioned document keys like `research-abc123-plan-v2`.

> **Temporal guarantee**: Even if the worker crashes mid-loop, Temporal replays the workflow from its event history. The `while` loop, counters, and signal state are all reconstructed deterministically.

---

## Step 2 — Update the Data Models

Replace the contents of `src/models.py` with richer models that support the multi-phase workflow:

```python
"""
Advanced Workflow Models — Multi-phase research workflow with loop support.

Demonstrates:
- Pydantic validation with field_validator
- Flexible input formats (structured dict or natural language)
- Versioned document key generation
- Rich result metadata for observability
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchRequest(BaseModel):
    """Input model for the research workflow."""

    workflow_id: str = Field(..., description="Unique workflow identifier")
    topic: str = Field(
        ..., min_length=10, max_length=500, description="Research topic or question"
    )
    criteria: dict[str, Any] | str = Field(
        ...,
        description="Research criteria — structured dict or natural language string",
    )
    agent_url: str = Field(
        default="http://host.docker.internal:8081",
        description="Strands agent endpoint URL (host.docker.internal for Docker→host access)",
    )

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("Topic must be at least 10 characters long")
        return v.strip()

    @field_validator("workflow_id")
    @classmethod
    def validate_workflow_id(cls, v: str) -> str:
        if not v.startswith("research-"):
            raise ValueError('Workflow ID must start with "research-"')
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "workflow_id": "research-abc123",
                    "topic": "Workflow orchestration platforms comparison",
                    "criteria": {
                        "must_have": ["Durable execution", "Observability"],
                        "should_have": ["Kubernetes-native deployment"],
                    },
                    "agent_url": "http://host.docker.internal:8081",
                }
            ]
        }
    )


class ResearchResult(BaseModel):
    """Output model from completed research workflow."""

    workflow_id: str = Field(..., description="Unique workflow identifier")
    final_document_key: str = Field(
        ..., description="Key for the final approved document"
    )
    iterations: int = Field(
        ..., description="Total revision iterations (plan + document)"
    )
    status: str = Field(
        ..., description="Final status: completed, failed, timeout"
    )
    metadata: dict[str, Any] = Field(
        ..., description="Execution metadata"
    )

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = ["completed", "failed", "timeout"]
        if v not in allowed:
            raise ValueError(f"Status must be one of: {allowed}")
        return v


class ModelValidation:
    """Utility class for document key management across loop iterations."""

    @staticmethod
    def create_document_key(workflow_id: str, doc_type: str, version: int) -> str:
        """Create a versioned document key: {workflow_id}-{type}-v{version}"""
        if doc_type not in ["plan", "results"]:
            raise ValueError(f"Invalid document type: {doc_type}")
        if version < 1:
            raise ValueError(f"Version must be positive: {version}")
        return f"{workflow_id}-{doc_type}-v{version}"

    @staticmethod
    def is_valid_document_key(document_key: str) -> bool:
        """Check if a document key follows the expected format."""
        parts = document_key.split("-")
        if len(parts) < 3:
            return False
        if not parts[-1].startswith("v") or not parts[-1][1:].isdigit():
            return False
        if parts[-2] not in ["plan", "results"]:
            return False
        return int(parts[-1][1:]) > 0
```

Replace the contents of `src/__init__.py` with the models that support the multi-phase workflow:

```python
"""
TEMPLATE: Worker package

Main worker functionality for Temporal workflows with foundry-temporal integration.
"""

from .config import get_config
from .models import ResearchRequest, ResearchResult

# Conditionally import worker functions only if foundry_temporal is available
try:
    from .worker import (  # noqa: F401
        run_worker,
    )

    _worker_available = True
except ImportError:
    _worker_available = False

__all__ = [
    "get_config",
    "ResearchRequest",
    "ResearchResult",
]

if _worker_available:
    __all__.extend(
        [
            "run_worker",
        ]
    )
```

### What changed from the Next Steps setup

| Next Steps (`MyWorkflowInput`) | Advanced (`ResearchRequest`) |
|---|---|
| Simple `user_name`, `task_type` strings | Validated `workflow_id`, `topic` with length constraints |
| No validators | `field_validator` for format enforcement |
| Flat result dict | `ResearchResult` with status validation and rich metadata |
| No versioning concept | `ModelValidation` utility for iteration-versioned document keys |
| Agent URL set via [`services.yaml`](../../../config/services.yaml) | Agent URL passed per-request (default: `host.docker.internal:8081`) |

---

## Step 3 — Update the Activities

Replace the contents of `src/activities.py`. The advanced pattern routes different task types through a single `call_research_agent` activity. It is built with `strands_agent_activity` from [`foundry-temporal-agents`](https://github.com/boozallen/temporal-packages/blob/HEAD/docs/foundry/packages/foundry-temporal-agents/index.md), the same decorator behind the `call_strands_agent` activity the Next Steps setup used. Your function only builds the prompt. The decorator sends it to the agent with the `FOUNDRY_AGENT_BEARER_TOKEN` key you set in the Next Steps guide, which the agent requires:

```python
"""
Advanced Activities — One task-routed agent activity.

Demonstrates:
- A single activity handling several task types via routing
- Input validation inside the activity
- Calling the agent through foundry-temporal-agents, which sends the bearer
  token (FOUNDRY_AGENT_BEARER_TOKEN), applies the FOUNDRY_TLS_* settings, and
  heartbeats while the agent works
"""

from typing import Any

from foundry_temporal_agents import strands_agent_activity
from temporalio import activity
from temporalio.exceptions import ApplicationError


def build_task_message(task_request: dict[str, Any]) -> str:
    """Turn the workflow's task request into the prompt sent to the agent."""
    task = task_request["task"]

    if task == "analyze_and_plan":
        return (
            f"Write a research plan for this topic: {task_request['topic']}. "
            f"Criteria: {task_request['criteria']}."
        )
    if task == "revise_plan":
        return (
            "Revise this research plan based on the reviewer's feedback.\n\n"
            f"Feedback: {task_request['feedback']}\n\n"
            f"Current plan:\n{task_request['existing_document']}"
        )
    if task == "conduct_research":
        return (
            f"Research this topic: {task_request['topic']}. "
            f"Criteria: {task_request['criteria']}. "
            f"Follow this approved plan:\n{task_request['plan']}"
        )
    if task == "incorporate_feedback":
        return (
            "Revise this research document based on the reviewer's feedback.\n\n"
            f"Feedback: {task_request['feedback']}\n\n"
            f"Current document:\n{task_request['existing_document']}"
        )

    # Retrying can't fix an unknown task type, so fail without retries
    raise ApplicationError(f"Unknown task type: '{task}'", non_retryable=True)


@strands_agent_activity(
    name="call_research_agent",
    timeout_seconds=900,  # HTTP timeout for one agent call (research can be slow)
    heartbeat_timeout_seconds=60,  # heartbeat every 15 seconds during the call
)
async def call_research_agent(task_request: dict[str, Any]) -> dict[str, Any]:
    """
    Build the agent request for one task.

    The workflow calls this activity with two arguments: the agent URL and a
    task_request dict. The decorator takes the URL, passes task_request here,
    sends the returned task to the agent over A2A JSON-RPC (with the
    Authorization header), and returns the agent's response to the workflow.

    Args:
        task_request: {
            "task": str,               # Operation type
            "workflow_id": str,        # Workflow identifier
            "document_key": str,       # Versioned key of the document to produce
            "topic": str,              # (analyze_and_plan, conduct_research)
            "criteria": dict | str,    # (analyze_and_plan, conduct_research)
            "plan": str,               # (conduct_research) the approved plan
            "feedback": str,           # (revision tasks)
            "existing_document": str,  # (revision tasks) the version to revise
        }
    """
    activity.logger.info(
        f"Calling agent for task: {task_request['task']}, "
        f"document key: {task_request['document_key']}"
    )

    return {
        "task": build_task_message(task_request),
        # Sent to the agent alongside the task text
        "context": {
            "workflow_id": task_request["workflow_id"],
            "document_key": task_request["document_key"],
        },
    }
```

### What changed from the Next Steps setup

| Next Steps (`my_activity` + `call_strands_agent`) | Advanced (`call_research_agent`) |
|---|---|
| Two separate activities — `my_activity` + `call_strands_agent` from `foundry_temporal_agents` | **Single task-routed activity** — handles 4 operation types via the `task` field |
| Simple dict input | Structured `task_request` with task-specific fields |
| The workflow sends a finished prompt | The activity builds the prompt for each task type, and rejects an unknown one without retrying |
| Agent URL resolved from [`services.yaml`](../../../config/services.yaml) | Agent URL passed with each call (the workflow controls routing) |

Both send the bearer token, apply the `FOUNDRY_TLS_*` settings and heartbeat during the call, because both are built with `foundry-temporal-agents`' decorator. Both return the agent's A2A response, from which the workflow takes the text.

---

## Step 4 — Build the Loop-Based Workflow

Replace the contents of `src/workflows.py`. This is the core of the advanced pattern. Like `MyWorkflow`, it inherits its signal handlers from `HILSignalsMixin`, opens a review with the digest of the content under review before each wait, and sets the `current_phase` values the Workflow API's `/approve` endpoint checks:

```python
"""
Advanced Workflow — Multi-phase research with HIL feedback loops.

Demonstrates:
- Multi-phase orchestration (plan → research)
- Human-in-the-loop while loops using HILSignalsMixin signals
- Approvals bound to the reviewed content by a digest
- Iteration tracking with versioned document keys
- A query handler for real-time workflow status
- Timeout handling inside loops
"""

import hashlib
from datetime import timedelta
from typing import Any

from foundry_temporal.signals import HILSignalsMixin
from foundry_temporal_agents.retry import STRANDS_AGENT_RETRY_POLICY
from temporalio import workflow
from temporalio.exceptions import ApplicationError
from temporalio.workflow import execute_activity

from .models import ModelValidation, ResearchRequest, ResearchResult

# How long a reviewer has to approve or send feedback on each version
REVIEW_TIMEOUT = timedelta(hours=24)


def agent_text(result: object) -> str:
    """Return the text of an A2A result: a Message's parts or a Task's artifacts."""
    if isinstance(result, dict):
        parts = list(result.get("parts") or [])
        for artifact in result.get("artifacts") or []:
            parts.extend(artifact.get("parts") or [])
        texts = [part["text"] for part in parts if part.get("text")]
        if texts:
            return "\n".join(texts)
    return str(result)


@workflow.defn
class ResearchWorkflow(HILSignalsMixin):  # type: ignore[misc]
    """
    Multi-phase HIL Research Workflow with feedback loops.

    Execution phases:
    1. Plan Generation — agent creates initial research plan
    2. Plan Review Loop — human approves or sends feedback (loops until approved)
    3. Research Execution — agent conducts research based on approved plan
    4. Document Review Loop — human approves or sends feedback (loops until approved)
    5. Finalization — return results with iteration metadata

    The signal handlers come from HILSignalsMixin: approve_plan, provide_plan_feedback,
    approve_research, provide_feedback (and approve, cancel_workflow).
    """

    def __init__(self) -> None:
        super().__init__()  # HILSignalsMixin: review state and signal handlers
        self.workflow_id = ""
        self.plan_iterations = 0
        self.document_iterations = 0
        # The Workflow API's /approve endpoint checks this value: it relays an
        # approval only while it reads awaiting_plan_review (lane "plan") or
        # awaiting_research_review (lane "research").
        self.current_phase = "starting"
        self.review_content = ""
        self.content_digest = ""

    @workflow.run
    async def run(self, request: ResearchRequest) -> ResearchResult:
        """Execute the multi-phase workflow with two feedback loops."""
        self.workflow_id = request.workflow_id

        workflow.logger.info(
            "Starting ResearchWorkflow",
            extra={"workflow_id": self.workflow_id, "topic": request.topic},
        )

        # Phase 1+2: Generate plan and loop until approved
        plan = await self.generate_plan_loop(request)

        # Phase 3+4: Generate research and loop until approved
        await self.generate_research_loop(request, plan)

        # Phase 5: Finalize and return results
        self.current_phase = "completed"
        final_plan_key = self.document_key("plan", self.plan_iterations)
        final_document_key = self.document_key("results", self.document_iterations)

        return ResearchResult(
            workflow_id=self.workflow_id,
            final_document_key=final_document_key,
            iterations=self.plan_iterations + self.document_iterations,
            status="completed",
            metadata={
                "plan_iterations": self.plan_iterations,
                "document_iterations": self.document_iterations,
                "approved_plan_key": final_plan_key,
                "plan_approved_by": self.plan_approved_by,
                "final_document_key": final_document_key,
                "document_approved_by": self.document_approved_by,
                "completed_at": workflow.now().isoformat(),
            },
        )

    # ── Phase 1+2: Plan Generation Loop ─────────────────────────────

    async def generate_plan_loop(self, request: ResearchRequest) -> str:
        """Generate plan, then loop for human feedback until approved."""
        workflow.logger.info("Starting plan generation loop")
        self.plan_iterations = 1

        # Initial plan generation via agent
        plan = await self.ask_agent(
            request,
            phase="generating_plan",
            task_request={
                "task": "analyze_and_plan",
                "topic": request.topic,
                "criteria": request.criteria,
                "document_key": self.document_key("plan", self.plan_iterations),
            },
        )
        self.open_for_review("plan", plan)

        # ── HIL approval loop ──
        while not self.plan_approved:
            workflow.logger.info(
                f"Awaiting plan approval (iteration {self.plan_iterations})"
            )

            # Wait for an approval or feedback signal (with timeout)
            try:
                await workflow.wait_condition(
                    self.is_plan_decision_received,
                    timeout=REVIEW_TIMEOUT,
                )
            except TimeoutError:
                self.current_phase = "timed_out"
                raise ApplicationError(
                    f"No plan decision within {REVIEW_TIMEOUT} for workflow "
                    f"{self.workflow_id}",
                    non_retryable=True,
                ) from None

            # If feedback was received (not approval), revise and loop
            if self.plan_feedback_received and not self.plan_approved:
                feedback = self.plan_feedback_comments
                workflow.logger.info(f"Processing plan feedback: {feedback}")

                # Clear the feedback so the loop waits for the next decision
                self.reset_plan_feedback()
                self.plan_iterations += 1

                plan = await self.ask_agent(
                    request,
                    phase="revising_plan",
                    task_request={
                        "task": "revise_plan",
                        "feedback": feedback,
                        "existing_document": plan,
                        "document_key": self.document_key("plan", self.plan_iterations),
                    },
                )
                self.open_for_review("plan", plan)

        workflow.logger.info(
            f"Plan approved by {self.plan_approved_by} after "
            f"{self.plan_iterations} iterations"
        )
        return plan

    # ── Phase 3+4: Research Generation Loop ──────────────────────────

    async def generate_research_loop(self, request: ResearchRequest, plan: str) -> None:
        """Generate research, then loop for human feedback until approved."""
        workflow.logger.info("Starting research generation loop")
        self.document_iterations = 1

        document = await self.ask_agent(
            request,
            phase="researching",
            task_request={
                "task": "conduct_research",
                "topic": request.topic,
                "criteria": request.criteria,
                "plan": plan,
                "document_key": self.document_key("results", self.document_iterations),
            },
        )
        self.open_for_review("research", document)

        # ── HIL approval loop ──
        while not self.document_approved:
            workflow.logger.info(
                f"Awaiting research approval (iteration {self.document_iterations})"
            )

            try:
                await workflow.wait_condition(
                    self.is_document_decision_received,
                    timeout=REVIEW_TIMEOUT,
                )
            except TimeoutError:
                self.current_phase = "timed_out"
                raise ApplicationError(
                    f"No research decision within {REVIEW_TIMEOUT} for workflow "
                    f"{self.workflow_id}",
                    non_retryable=True,
                ) from None

            if self.document_feedback_received and not self.document_approved:
                feedback = self.document_feedback_comments
                workflow.logger.info(f"Processing research feedback: {feedback}")

                self.reset_document_feedback()
                self.document_iterations += 1

                document = await self.ask_agent(
                    request,
                    phase="revising_research",
                    task_request={
                        "task": "incorporate_feedback",
                        "feedback": feedback,
                        "existing_document": document,
                        "document_key": self.document_key(
                            "results", self.document_iterations
                        ),
                    },
                )
                self.open_for_review("research", document)

        workflow.logger.info(
            f"Research approved by {self.document_approved_by} after "
            f"{self.document_iterations} iterations"
        )

    # ── Helpers ──────────────────────────────────────────────────────

    async def ask_agent(
        self, request: ResearchRequest, phase: str, task_request: dict[str, Any]
    ) -> str:
        """Run one agent task through the call_research_agent activity."""
        self.current_phase = phase
        self.review_content = ""
        self.content_digest = ""

        result = await execute_activity(
            "call_research_agent",
            args=[request.agent_url, {"workflow_id": self.workflow_id, **task_request}],
            start_to_close_timeout=timedelta(minutes=20),
            heartbeat_timeout=timedelta(seconds=60),
            retry_policy=STRANDS_AGENT_RETRY_POLICY,
        )
        return agent_text(result)

    def open_for_review(self, lane: str, content: str) -> None:
        """Publish content for review and open its review lane.

        The digest binds an approval to this exact content: HILSignalsMixin
        ignores an approve_plan or approve_research signal whose content_digest
        doesn't match the one opened here.
        """
        self.review_content = content
        self.content_digest = hashlib.sha256(content.encode()).hexdigest()
        if lane == "plan":
            self.open_plan_review(self.content_digest)
            self.current_phase = "awaiting_plan_review"
        else:
            self.open_document_review(self.content_digest)
            self.current_phase = "awaiting_research_review"

    def document_key(self, doc_type: str, version: int) -> str:
        return ModelValidation.create_document_key(self.workflow_id, doc_type, version)

    # ── Query Handler ────────────────────────────────────────────────

    @workflow.query
    def get_status(self) -> dict[str, Any]:
        """Query current workflow status — callable from the API at any time."""
        return {
            "workflow_id": self.workflow_id,
            "current_phase": self.current_phase,
            "plan_iteration": self.plan_iterations,
            "document_iteration": self.document_iterations,
            "current_plan_key": (
                self.document_key("plan", self.plan_iterations)
                if self.plan_iterations
                else ""
            ),
            "current_document_key": (
                self.document_key("results", self.document_iterations)
                if self.document_iterations
                else ""
            ),
            "plan_approved": self.plan_approved,
            "plan_approved_by": self.plan_approved_by,
            "document_approved": self.document_approved,
            "document_approved_by": self.document_approved_by,
            # What the reviewer is asked to approve, and the digest /approve needs
            "content_digest": self.content_digest,
            "review_content": self.review_content,
        }
```

### Anatomy of the Loop

Let's break down the key moving parts inside `generate_plan_loop`:

```
┌─ plan_iterations = 1
│
├─ execute_activity("call_research_agent", task="analyze_and_plan")
│   └─ Plan v1, document key: research-abc123-plan-v1
├─ open_for_review("plan", plan)  →  current_phase = "awaiting_plan_review"
│
├─ while not self.plan_approved:
│   │
│   ├─ workflow.wait_condition(is_plan_decision_received, timeout=24h)
│   │   └─ BLOCKS here until a signal arrives
│   │
│   ├─ if feedback received (not approved):
│   │   ├─ reset_plan_feedback()  →  clears state for next loop
│   │   ├─ plan_iterations += 1  →  now v2
│   │   ├─ execute_activity("call_research_agent", task="revise_plan")
│   │   │   └─ Sends v1 and the feedback, gets v2
│   │   └─ open_for_review("plan", plan)  →  new digest, awaiting review again
│   │
│   └─ if approved:
│       └─ while condition is False → loop exits
│
└─ return (plan approved after N iterations)
```

**Signal flow:**
1. The API's `/approve` endpoint (lane `plan`) checks that `get_status` reports `current_phase` `awaiting_plan_review`, then sends `approve_plan(approver_id, content_digest)` → the mixin compares the digest with the one `open_plan_review` stored → `self.plan_approved = True`, `self.plan_approved_by = approver_id` → `wait_condition` unblocks → loop exits. The API then confirms `plan_approved_by` in `get_status` before it answers.
2. The API's `/signal` endpoint sends `provide_plan_feedback(approver_id, "add more detail")` → `self.plan_feedback_received = True`, `self.plan_feedback_comments = "add more detail"` → `wait_condition` unblocks → revision branch executes → loop continues

---

## Step 5 — Update the YAML Configuration

### 5.1 Update `config/workflows.yaml`

```yaml
# Advanced: Research Workflow with feedback loops
workflows:
  - module: "src.workflows"
    classes: ["ResearchWorkflow"]
    description: "Multi-phase HIL research workflow with plan and document review loops"
```

### 5.2 Update `config/activities.yaml`

```yaml
# Advanced: Task-routed agent activity
activities:
  - module: "src.activities"
    functions:
      - name: "call_research_agent"
        description: "Call the Strands agent via A2A with task routing"
        timeout_seconds: 900
```

> **Note**: The Next Steps setup registered `my_activity` and `get_service_config_activity` from `src.activities` and `call_strands_agent` from the `foundry_temporal_agents` package. In this advanced version, we replace them all with `call_research_agent` from `src.activities`, which handles task routing internally. The agent URL (`http://host.docker.internal:8081`) is now passed per-request in the workflow rather than being looked up from `services.yaml`. The retry policy (`STRANDS_AGENT_RETRY_POLICY`) and timeouts are set where the workflow calls the activity.

---

## Step 6 — Rebuild and Test

### 6.1 Rebuild the worker

Since the [Next Steps Guide](end-to-end-how-to-next-steps.md) already removed the mock agent from [`compose.yaml`](../../../compose.yaml), you only need to rebuild and restart the worker:

```bash
cd ~/temporal-stack/temporal-workflow-worker-starter
docker compose build worker
docker compose up -d worker
```

### 6.2 Verify the worker registered the new workflow

```bash
docker compose logs -f worker
```

Look for:
- `Loaded workflow: ResearchWorkflow from src.workflows`
- `Loaded activity: call_research_agent from src.activities`
- `Temporal worker started successfully`

### 6.3 Register `ResearchWorkflow` with the Workflow API

The Workflow API starts only the workflow types it lists, and it lists only `MyWorkflow`, so it answers `400 Unknown workflow type` for `ResearchWorkflow` until you add it.

In `~/temporal-stack/temporal-workflow-api-starter`, open [`src/routers/workflows.py`](https://github.com/boozallen/temporal-workflow-api-starter/blob/HEAD/src/routers/workflows.py), find `get_available_workflows()`, and add the name to its `workflow_types` set, as its `TEMPLATE: Add your workflow type names here` comment says:

```python
def get_available_workflows() -> dict[str, str]:
    ...
    workflow_types = {
        "MyWorkflow",
        "ResearchWorkflow",
    }
```

Then restart the API. Its `compose.yaml` mounts `src/` into the container, so a restart picks up the change without a rebuild:

```bash
cd ~/temporal-stack/temporal-workflow-api-starter
just down
just up
```

The same list also decides which workflows the API's status, query, signal and approve endpoints act on, so without this step those calls answer `404` for `research-test-001`.

The API's `/approve` endpoint already knows the `plan` and `research` review lanes this workflow uses: `APPROVAL_LANES` in the same file maps them to the `approve_plan` and `approve_research` signals, the `awaiting_plan_review` and `awaiting_research_review` phases, and the `plan_approved_by` and `document_approved_by` status fields.

### 6.4 Start a research workflow

The curl examples below read `$API_AUTH_TOKEN` from your shell. If you started a new
terminal since the [Getting Started Guide](end-to-end-how-to-getting-started.md),
export it again first:

```bash
export API_AUTH_TOKEN=local-dev-token-replace-with-32-chars
```

In PowerShell:

```powershell
$env:API_AUTH_TOKEN = "local-dev-token-replace-with-32-chars"
```

Start the workflow and keep the `run_id` from the response. The approvals in 6.7 and 6.8 name the run they approve:

```bash
START_RESPONSE=$(curl -s -X POST http://localhost:8000/workflows/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -d '{
    "workflow_type": "ResearchWorkflow",
    "workflow_id": "research-test-001",
    "input_data": {
      "workflow_id": "research-test-001",
      "topic": "Compare workflow orchestration platforms for microservices",
      "criteria": {
        "must_have": ["Durable execution", "Observability"],
        "should_have": ["Kubernetes-native", "Multi-language SDKs"]
      },
      "agent_url": "http://host.docker.internal:8081"
    }
  }')
echo "$START_RESPONSE"

# The run ID the approvals need
RUN_ID=$(echo "$START_RESPONSE" | sed -n 's/.*"run_id":"\([^"]*\)".*/\1/p')
echo "run_id: $RUN_ID"
```

In PowerShell:

```powershell
$start = Invoke-RestMethod -Method Post -Uri http://localhost:8000/workflows/start `
  -ContentType "application/json" `
  -Headers @{ Authorization = "Bearer $env:API_AUTH_TOKEN" } `
  -Body '{
    "workflow_type": "ResearchWorkflow",
    "workflow_id": "research-test-001",
    "input_data": {
      "workflow_id": "research-test-001",
      "topic": "Compare workflow orchestration platforms for microservices",
      "criteria": {
        "must_have": ["Durable execution", "Observability"],
        "should_have": ["Kubernetes-native", "Multi-language SDKs"]
      },
      "agent_url": "http://host.docker.internal:8081"
    }
  }'
$start

# The run ID the approvals need
$RUN_ID = $start.run_id
"run_id: $RUN_ID"
```

> **Agent URL**: The workflow uses `http://host.docker.internal:8081` — the same pattern from the [Next Steps Guide](end-to-end-how-to-next-steps.md). The worker container reaches the Strands Base Agent running on the host via Docker's `host.docker.internal` DNS name.

> **New terminal?** `RUN_ID` lives only in this shell. If you open another one, the `run_id` field of `GET /workflows/research-test-001/status` gives it back.

### 6.5 Wait for the plan, then read it

`/workflows/{id}/status` only returns Temporal's own execution metadata (run ID, status,
timestamps) — it does not call into the workflow's `get_status` query handler, so it
never has `plan_iteration`. Use `/workflows/{id}/query` instead, which does.

The agent takes a while to write the plan. Wait until `current_phase` reads `awaiting_plan_review` (press `Ctrl+C` to stop waiting, and check the worker logs, if it never does):

```bash
until curl -s "http://localhost:8000/workflows/research-test-001/query?query_name=get_status" \
    -H "Authorization: Bearer $API_AUTH_TOKEN" | grep -q '"current_phase":"awaiting_plan_review"'; do
  echo "Waiting for the plan..."; sleep 5
done
```

In PowerShell:

```powershell
do {
  Start-Sleep -Seconds 5
  $status = Invoke-RestMethod -Method Get -Uri "http://localhost:8000/workflows/research-test-001/query?query_name=get_status" `
    -Headers @{ Authorization = "Bearer $env:API_AUTH_TOKEN" }
  "current_phase: $($status.result.current_phase)"
} until ($status.result.current_phase -eq "awaiting_plan_review")
```

Then read the plan:

```bash
curl -s -X GET "http://localhost:8000/workflows/research-test-001/query?query_name=get_status" \
  -H 'accept: application/json' \
  -H "Authorization: Bearer $API_AUTH_TOKEN"
```

In PowerShell:

```powershell
Invoke-RestMethod -Method Get -Uri "http://localhost:8000/workflows/research-test-001/query?query_name=get_status" `
  -Headers @{ accept = "application/json"; Authorization = "Bearer $env:API_AUTH_TOKEN" } | ConvertTo-Json -Depth 5
```

Expected response (workflow is waiting for plan approval):
```json
{
  "workflow_id": "research-test-001",
  "query_name": "get_status",
  "result": {
    "workflow_id": "research-test-001",
    "current_phase": "awaiting_plan_review",
    "plan_iteration": 1,
    "document_iteration": 0,
    "current_plan_key": "research-test-001-plan-v1",
    "current_document_key": "",
    "plan_approved": false,
    "plan_approved_by": null,
    "document_approved": false,
    "document_approved_by": null,
    "content_digest": "<SHA-256 of review_content>",
    "review_content": "<the plan the agent wrote>"
  }
}
```

`review_content` is what the reviewer reads, and `content_digest` is what an approval of it must carry.

### 6.6 Send feedback (triggers revision loop)

The API's `/signal` endpoint needs an `approver_id` (who sends the feedback) and non-empty `comments`:

```bash
curl -X 'POST' \
  'http://localhost:8000/workflows/research-test-001/signal' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -d '{
  "signal_name": "provide_plan_feedback",
  "approver_id": "jane.doe@example.com",
  "comments": "Please add implementation timeline and cost estimates"
}'
```

In PowerShell:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/workflows/research-test-001/signal `
  -ContentType "application/json" `
  -Headers @{ accept = "application/json"; Authorization = "Bearer $env:API_AUTH_TOKEN" } `
  -Body '{
  "signal_name": "provide_plan_feedback",
  "approver_id": "jane.doe@example.com",
  "comments": "Please add implementation timeline and cost estimates"
}'
```

The workflow sends the plan and your comments to the agent (`current_phase` reads `revising_plan`), then opens the revised plan for review. Wait for it, the same way as in 6.5. The iteration count increments to 2:

```bash
until curl -s "http://localhost:8000/workflows/research-test-001/query?query_name=get_status" \
    -H "Authorization: Bearer $API_AUTH_TOKEN" | grep '"current_phase":"awaiting_plan_review"' | grep -qE '"plan_iteration":2[,}]'; do
  echo "Waiting for the revised plan..."; sleep 5
done
```

In PowerShell:

```powershell
do {
  Start-Sleep -Seconds 5
  $status = Invoke-RestMethod -Method Get -Uri "http://localhost:8000/workflows/research-test-001/query?query_name=get_status" `
    -Headers @{ Authorization = "Bearer $env:API_AUTH_TOKEN" }
  "current_phase: $($status.result.current_phase), plan_iteration: $($status.result.plan_iteration)"
} until ($status.result.current_phase -eq "awaiting_plan_review" -and $status.result.plan_iteration -eq 2)
```

### 6.7 Approve the plan (exits plan loop)

Approvals go through the API's `/approve` endpoint, not `/signal`. It needs the run ID from 6.4, who approves, the `content_digest` of the version you reviewed (from the status query), and the lane, `plan`:

```bash
PLAN_DIGEST=$(curl -s "http://localhost:8000/workflows/research-test-001/query?query_name=get_status" \
  -H "Authorization: Bearer $API_AUTH_TOKEN" | sed -n 's/.*"content_digest":"\([0-9a-f]*\)".*/\1/p')

curl -X 'POST' 'http://localhost:8000/workflows/research-test-001/approve' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -d "{\"run_id\": \"$RUN_ID\", \"approver_id\": \"jane.doe@example.com\", \"content_digest\": \"$PLAN_DIGEST\", \"lane\": \"plan\"}"
```

In PowerShell:

```powershell
$status = Invoke-RestMethod -Method Get -Uri "http://localhost:8000/workflows/research-test-001/query?query_name=get_status" `
  -Headers @{ Authorization = "Bearer $env:API_AUTH_TOKEN" }
$body = @{
  run_id = $RUN_ID
  approver_id = "jane.doe@example.com"
  content_digest = $status.result.content_digest
  lane = "plan"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://localhost:8000/workflows/research-test-001/approve `
  -ContentType "application/json" `
  -Headers @{ accept = "application/json"; Authorization = "Bearer $env:API_AUTH_TOKEN" } `
  -Body $body
```

Expected response:
```json
{
  "status": "approved",
  "workflow_id": "research-test-001",
  "run_id": "<your run_id>",
  "lane": "plan",
  "message": "Workflow approved, proceeding to completion"
}
```

A `409` means the run wasn't awaiting plan review (`Run is not awaiting review`), or the digest didn't match the plan open for review (`Approval was not recorded`). Query the status again and approve the version it shows.

The workflow now moves to Phase 3 — research generation.

### 6.8 Approve the research document (exits research loop)

Wait for the research document. This agent call usually takes longer than the plan:

```bash
until curl -s "http://localhost:8000/workflows/research-test-001/query?query_name=get_status" \
    -H "Authorization: Bearer $API_AUTH_TOKEN" | grep -q '"current_phase":"awaiting_research_review"'; do
  echo "Waiting for the research document..."; sleep 5
done
```

In PowerShell:

```powershell
do {
  Start-Sleep -Seconds 5
  $status = Invoke-RestMethod -Method Get -Uri "http://localhost:8000/workflows/research-test-001/query?query_name=get_status" `
    -Headers @{ Authorization = "Bearer $env:API_AUTH_TOKEN" }
  "current_phase: $($status.result.current_phase)"
} until ($status.result.current_phase -eq "awaiting_research_review")
```

Read it with the status query from 6.5 (`review_content`). To send feedback on it first, use the 6.6 call with `"signal_name": "provide_feedback"`, then wait until the status shows `current_phase` `awaiting_research_review` with `document_iteration` 2, as 6.6 does for the plan. Then approve it, the same way as the plan but with the lane `research`:

```bash
DOCUMENT_DIGEST=$(curl -s "http://localhost:8000/workflows/research-test-001/query?query_name=get_status" \
  -H "Authorization: Bearer $API_AUTH_TOKEN" | sed -n 's/.*"content_digest":"\([0-9a-f]*\)".*/\1/p')

curl -X 'POST' 'http://localhost:8000/workflows/research-test-001/approve' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $API_AUTH_TOKEN" \
  -d "{\"run_id\": \"$RUN_ID\", \"approver_id\": \"jane.doe@example.com\", \"content_digest\": \"$DOCUMENT_DIGEST\", \"lane\": \"research\"}"
```

In PowerShell:

```powershell
$status = Invoke-RestMethod -Method Get -Uri "http://localhost:8000/workflows/research-test-001/query?query_name=get_status" `
  -Headers @{ Authorization = "Bearer $env:API_AUTH_TOKEN" }
$body = @{
  run_id = $RUN_ID
  approver_id = "jane.doe@example.com"
  content_digest = $status.result.content_digest
  lane = "research"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://localhost:8000/workflows/research-test-001/approve `
  -ContentType "application/json" `
  -Headers @{ accept = "application/json"; Authorization = "Bearer $env:API_AUTH_TOKEN" } `
  -Body $body
```

The workflow completes and returns a `ResearchResult`. Its `status` reads `completed`, and its `result` holds the `ResearchResult`:

```bash
curl -s "http://localhost:8000/workflows/research-test-001/status" \
  -H "Authorization: Bearer $API_AUTH_TOKEN"
```

In PowerShell:

```powershell
Invoke-RestMethod -Method Get -Uri http://localhost:8000/workflows/research-test-001/status `
  -Headers @{ Authorization = "Bearer $env:API_AUTH_TOKEN" } | ConvertTo-Json -Depth 5
```

### 6.9 Monitor in Temporal UI and Agent Logs

1. Open `http://localhost:8233`
2. Select the **default** namespace
3. Click on workflow `research-test-001`
4. In the event history, observe:
   - Multiple `ActivityTaskScheduled` / `ActivityTaskCompleted` events (one per agent call)
   - `WorkflowExecutionSignaled` events for each feedback/approval signal
   - The workflow completing after both loops exit

5. Check the [Strands Base Agent](https://github.com/boozallen/strands-base-agent/blob/HEAD/docs/foundry/index.md) logs to see the real LLM-powered responses:

```bash
cd ~/temporal-stack/strands-base-agent
docker compose logs -f
```

You should see multiple incoming A2A JSON-RPC requests — one for each loop iteration (initial plan, revised plan, initial research, etc.).

---

## Key Concepts Summary

### 1. Signal-Driven Loops

```python
while not self.plan_approved:
    await workflow.wait_condition(self.is_plan_decision_received)
    if self.plan_feedback_received and not self.plan_approved:
        self.reset_plan_feedback()
        # ... revise, then open the new version for review
        self.open_for_review("plan", plan)
```

The `while` loop is the core pattern. `wait_condition` blocks until a signal changes state. The reset call clears state for the next iteration, and opening the new version for review gives it a new digest.

### 2. Versioned Document Keys

```python
self.plan_iterations += 1
key = self.document_key("plan", self.plan_iterations)
# → "research-abc123-plan-v2"
```

Each loop iteration increments a counter and generates a new versioned key. This creates an audit trail of every revision.

### 3. Multiple Signal Handlers per Phase

All four come from `HILSignalsMixin`. Each ignores a signal with an empty `approver_id`, and the approvals also ignore a `content_digest` that doesn't match the version open for review.

| Signal | Phase | Sent through | Effect |
|---|---|---|---|
| `approve_plan(approver_id, content_digest)` | Plan | `/approve`, lane `plan` | Sets `plan_approved = True` and `plan_approved_by`, exits plan loop |
| `provide_plan_feedback(approver_id, comments)` | Plan | `/signal` | Sets feedback state, triggers plan revision |
| `approve_research(approver_id, content_digest)` | Research | `/approve`, lane `research` | Sets `document_approved = True` and `document_approved_by`, exits research loop |
| `provide_feedback(approver_id, comments)` | Research | `/signal` | Sets feedback state, triggers document revision |

### 4. Query Handlers for Observability

The `get_status` query returns real-time workflow state without affecting execution — useful for building dashboards or status endpoints. The Workflow API's `/approve` endpoint relies on it too: it reads `current_phase` before relaying an approval, and the `*_approved_by` field after, to confirm the approval was recorded.

### 5. Timeout Handling

```python
try:
    await workflow.wait_condition(self.is_plan_decision_received, timeout=REVIEW_TIMEOUT)
except TimeoutError:
    raise ApplicationError("No plan decision within 24 hours", non_retryable=True) from None
```

If no signal arrives within 24 hours (`REVIEW_TIMEOUT`), the `TimeoutError` is caught and converted to an `ApplicationError`, which fails the workflow cleanly. Any other exception raised in workflow code fails only the workflow task, which Temporal retries without end.

### 6. Temporal Determinism

Everything inside the `@workflow.defn` class must be **deterministic**:
- No `datetime.now()` — use `workflow.now()`
- No direct HTTP calls — delegate to activities via `execute_activity`
- No random values — use `workflow.random()`
- Side effects happen only inside `@activity.defn` functions

The `while` loops, counters, and signal state are all replayed deterministically from Temporal's event history if the worker restarts.

---

## Comparison: Next Steps Setup vs. Advanced

| Feature | Next Steps (`MyWorkflow`) | Advanced (`ResearchWorkflow`) |
|---|---|---|
| **Structure** | Linear 3 steps | 2 phases, each with a feedback loop |
| **Agent** | [Strands Base Agent](https://github.com/boozallen/strands-base-agent/blob/HEAD/docs/foundry/index.md) (single call) | Strands Base Agent (multi-call with task routing) |
| **HIL Pattern** | Single `approve` signal | 4 signals: `approve_plan`, `provide_plan_feedback`, `approve_research`, `provide_feedback` (all from `HILSignalsMixin`) |
| **Loops** | None | `while not approved` loops in both phases |
| **Iteration Tracking** | None | `plan_iterations`, `document_iterations` counters |
| **Document Versioning** | None | `{workflow_id}-{type}-v{version}` keys |
| **Query Handlers** | `get_status` from `QueryMixin` | Its own `get_status`, with phase, iterations, approvers and the content under review |
| **Activity Pattern** | Separate `my_activity` + `call_strands_agent` from `foundry_temporal_agents` | Single task-routed `call_research_agent` in `src.activities` |
| **Agent URL** | Looked up from [`services.yaml`](../../../config/services.yaml) | Passed per-request (default: `host.docker.internal:8081`) |
| **Retry Policy** | `STRANDS_AGENT_RETRY_POLICY` for the agent call | `STRANDS_AGENT_RETRY_POLICY` for every agent call (5 attempts, exponential backoff) |
| **Timeout Handling** | Single 10-min timeout | Per-phase 24-hour timeouts with error handling |
| **Models** | Flat input/output | Validated models with `field_validator` and metadata |

---

## What's Next

1. **[Customization Guide](customization-guide.md)** — Further customize workflows and activities for your domain
2. **[Deployment Guide](../operations/deployment.md)** — Production deployment patterns
3. **[HA Worker Tuning Guide](../operations/ha-worker-tuning.md)** — High availability and production worker tuning (concurrency, scaling, monitoring)
4. **[Temporal Documentation](https://docs.temporal.io/)** — Official Temporal concepts (signals, queries, activities)

---

## Production Tuning and High Availability

Once you've built your advanced loop-based workflows, you'll need to tune your worker for production high availability. The **[HA Worker Tuning Guide](../operations/ha-worker-tuning.md)** covers:

- **Worker Identity and Multi-Instance Deployment** — Unique worker identities and horizontal scaling for HA
- **Concurrency Tuning** — Optimizing `max_concurrent_activities`, `max_concurrent_workflow_tasks`, and other settings based on workload characteristics
- **Slot Suppliers and Resource Management** — Fixed size, resource-based, and custom slot suppliers for dynamic capacity management
- **Graceful Shutdown** — Proper termination grace periods and activity completion handling
- **Health Checks and Monitoring** — Critical metrics (schedule-to-start latency, sync match rate) and Kubernetes probes
- **Production Configuration** — Environment-specific settings and configuration validation
- **Scaling Strategies** — Horizontal vs vertical scaling, auto-scaling patterns, and best practices

**Key takeaway**: For production HA, deploy multiple worker instances (minimum 3) with unique identities, tune concurrency based on your workload (I/O-bound activities vs CPU-bound workflows), and monitor critical metrics continuously.

See the [HA Worker Tuning Guide](../operations/ha-worker-tuning.md) for detailed recommendations and troubleshooting.
