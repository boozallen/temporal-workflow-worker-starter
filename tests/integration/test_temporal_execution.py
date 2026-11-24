# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Integration tests for Temporal workflow execution using an in-process test server.

These tests use temporalio.testing.WorkflowEnvironment.start_local() to spin up
an embedded Temporal server — no external cluster, AWS credentials, or other
external dependencies are required.

Covers:
- Workflow registration (worker starts with the workflow registered)
- Worker startup (worker connects and polls successfully)
- Activity execution (workflow invokes activity, gets result)
"""

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from temporalio import activity, workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import (
    SandboxedWorkflowRunner,
    SandboxRestrictions,
)

from src.models import MyWorkflowInput, MyWorkflowResult
from src.workflows import MyWorkflow

# `coverage` touches platform.python_implementation() the first time its own
# lazily-loaded submodules import, which can happen while sandboxed workflow
# code is executing under pytest-cov. Pass that one module through rather
# than disabling the sandbox outright, since the deployed worker always runs
# MyWorkflow sandboxed (see src/worker.py) and this keeps that check live.
_SANDBOX_RUNNER = SandboxedWorkflowRunner(
    restrictions=SandboxRestrictions.default.with_passthrough_modules("coverage")
)

# --- Stub activities for integration testing ---
# These replace external-service-dependent activities so we can test the
# Temporal execution mechanics (registration, dispatch, serialization)
# without network calls.


@activity.defn(name="my_activity")
async def stub_my_activity(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": True,
        "message": f"Processed {data.get('type', 'default')} for {data.get('name', 'unknown')}",
    }


@activity.defn(name="get_service_config_activity")
async def stub_get_service_config(service_name: str) -> dict[str, Any]:
    return {"url": "http://localhost:9999/stub-agent", "description": "stub"}


@activity.defn(name="call_strands_agent")
async def stub_call_strands_agent(
    agent_url: str,
    task: str,
    query_extra_data: dict[str, Any] | None,
    session_id: str | None,
) -> str:
    return "Stub agent response"


# Module-level workflow for the isolated activity test (Temporal requires this)
@workflow.defn(name="ActivityTestHarness")
class ActivityTestHarness:
    @workflow.run
    async def run(self, data: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            "my_activity",
            data,
            start_to_close_timeout=timedelta(seconds=10),
        )


# --- Fixtures ---


@pytest.fixture(scope="module")
async def env():
    """Start an in-process Temporal test server for the module."""
    async with await WorkflowEnvironment.start_local() as environment:
        yield environment


@pytest.fixture
def task_queue() -> str:
    return "integration-test-queue"


async def _approve(handle, approver_id: str = "integration-tester") -> None:
    """Wait for the review phase to open, then approve with its digest."""

    async def _review_opened() -> dict[str, str]:
        while True:
            content = await handle.query(MyWorkflow.get_review_content)
            if content["content_digest"]:
                return content
            await asyncio.sleep(0.1)

    content = await asyncio.wait_for(_review_opened(), timeout=10)
    await handle.signal(
        MyWorkflow.approve, args=[approver_id, content["content_digest"]]
    )


def _make_worker(client, task_queue, workflows=None, activities=None):
    """Create a worker with coverage passed through the sandbox (required under pytest-cov)."""
    return Worker(
        client,
        task_queue=task_queue,
        workflows=workflows or [MyWorkflow],
        activities=activities
        or [stub_my_activity, stub_get_service_config, stub_call_strands_agent],
        workflow_runner=_SANDBOX_RUNNER,
    )


# --- Tests ---


@pytest.mark.integration
@pytest.mark.workflow
class TestWorkflowRegistrationAndExecution:
    """Test that workflows register and execute correctly on a real Temporal server."""

    @pytest.mark.asyncio
    async def test_worker_starts_and_registers_workflow(
        self, env: WorkflowEnvironment, task_queue: str
    ):
        """AC2: Worker startup — worker connects, registers workflow, and polls."""
        async with _make_worker(env.client, task_queue):
            # Worker started successfully — it registered the workflow and is
            # polling the task queue. Verify the server is responsive.
            handle = await env.client.start_workflow(
                MyWorkflow.run,
                MyWorkflowInput(user_name="Startup Tester", task_type="ping"),
                id="integration-test-startup",
                task_queue=task_queue,
                execution_timeout=timedelta(seconds=30),
            )
            # If we can describe the workflow, registration worked
            desc = await handle.describe()
            assert desc.status is not None
            # Clean up — approve so it completes
            await _approve(handle)
            await handle.result()

    @pytest.mark.asyncio
    async def test_workflow_execution_end_to_end(
        self, env: WorkflowEnvironment, task_queue: str
    ):
        """AC2: Workflow registration + activity execution — full run through."""
        async with _make_worker(env.client, task_queue):
            handle = await env.client.start_workflow(
                MyWorkflow.run,
                MyWorkflowInput(
                    user_name="Integration Tester",
                    task_type="test",
                    priority=1,
                ),
                id="integration-test-workflow-e2e",
                task_queue=task_queue,
                execution_timeout=timedelta(seconds=30),
            )

            # Give workflow time to reach the approval wait
            await asyncio.sleep(2)

            # Send the approve signal to unblock step 3
            await _approve(handle)

            result: MyWorkflowResult = await handle.result()

            assert result.success is True
            assert (
                "Integration Tester" in result.message
                or "Integration Tester" in str(result.data)
            )
            assert result.data["steps_completed"] == 3

    @pytest.mark.asyncio
    async def test_activity_execution_returns_correct_data(
        self, env: WorkflowEnvironment, task_queue: str
    ):
        """AC2: Activity execution — verify activity is dispatched and returns data."""
        async with _make_worker(env.client, task_queue):
            handle = await env.client.start_workflow(
                MyWorkflow.run,
                MyWorkflowInput(
                    user_name="Activity Tester",
                    task_type="greeting",
                    priority=2,
                ),
                id="integration-test-activity-exec",
                task_queue=task_queue,
                execution_timeout=timedelta(seconds=30),
            )

            await asyncio.sleep(2)
            await _approve(handle)
            result: MyWorkflowResult = await handle.result()

            # Verify the activity results flowed through
            assert result.data["activity_result"]["success"] is True
            assert "Activity Tester" in result.data["activity_result"]["message"]
            assert result.data["agent_result"] == "Stub agent response"

    @pytest.mark.asyncio
    async def test_workflow_registers_on_custom_task_queue(
        self, env: WorkflowEnvironment
    ):
        """Workflow can be registered on any task queue name."""
        custom_queue = "custom-integration-queue"
        async with _make_worker(env.client, custom_queue):
            handle = await env.client.start_workflow(
                MyWorkflow.run,
                MyWorkflowInput(user_name="Queue Tester", task_type="queue_test"),
                id="integration-test-custom-queue",
                task_queue=custom_queue,
                execution_timeout=timedelta(seconds=30),
            )
            await asyncio.sleep(2)
            await _approve(handle)
            result = await handle.result()
            assert result.success is True


@pytest.mark.integration
@pytest.mark.activity
class TestActivityExecution:
    """Test activity execution in isolation via the Temporal runtime."""

    @pytest.mark.asyncio
    async def test_my_activity_via_worker(
        self, env: WorkflowEnvironment, task_queue: str
    ):
        """Activity executes correctly when dispatched by Temporal."""
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[ActivityTestHarness],
            activities=[stub_my_activity],
            workflow_runner=_SANDBOX_RUNNER,
        ):
            result = await env.client.execute_workflow(
                ActivityTestHarness.run,
                {"name": "TestUser", "type": "unit"},
                id="integration-test-activity-direct",
                task_queue=task_queue,
                execution_timeout=timedelta(seconds=10),
            )

            assert result["success"] is True
            assert "TestUser" in result["message"]
