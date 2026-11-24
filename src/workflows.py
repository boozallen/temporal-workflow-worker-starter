# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
TEMPLATE: Example Workflows using foundry-temporal

This module provides template workflows demonstrating foundry-temporal patterns.
Teams should customize these workflows for their specific business logic.

Key patterns demonstrated:
- BaseWorkflow from foundry-temporal for common patterns
- Proper data models with Pydantic
- Activity execution with timeouts and retries
- Signals and queries for workflow interaction
- Error handling and logging
"""

import hashlib
from datetime import timedelta
from typing import Any

# Import foundry-temporal signals and queries for HITL patterns
from foundry_temporal.queries import QueryMixin
from foundry_temporal.signals import HILSignalsMixin

# Import foundry-temporal-agents retry policies
from foundry_temporal_agents.retry import STRANDS_AGENT_RETRY_POLICY

# foundry-temporal patterns - using standard Temporal workflow with foundry patterns
from temporalio import workflow

# Real foundry-temporal-agents integration - using execute_activity pattern
from temporalio.workflow import execute_activity

# Import data models
from .models import MyWorkflowInput, MyWorkflowResult


@workflow.defn
class MyWorkflow(HILSignalsMixin, QueryMixin):  # type: ignore[misc]
    """
    TEMPLATE: Comprehensive workflow demonstrating foundry-temporal patterns.

    This workflow demonstrates both key design document requirements:
    1. Human-in-the-Loop (HITL) patterns via signals and queries
    2. Mock Agent integration via foundry-temporal-agents

    Teams should customize this workflow for their business logic:
    1. Update input/output models
    2. Replace mock_agent_activity with their own activities
    3. Modify orchestration logic
    4. Add error handling specific to their domain
    """

    def __init__(self) -> None:
        """Initialize workflow with foundry pattern state management."""
        super().__init__()  # Initializes HILSignalsMixin, then QueryMixin via the MRO
        self._status = "initialized"
        self._progress = 0
        self._result_data: dict[str, Any] = {}
        self._priority = 1
        self._message = ""
        self._review_content: str = ""

    @workflow.run
    async def run(self, input_data: MyWorkflowInput) -> MyWorkflowResult:
        """
        Main workflow execution with 3 steps:
        1. Call to my_activity for initial processing
        2. Call to mock-strands-agent via call_strands_agent activity
        3. Wait for human approval via approve signal

        Teams should customize this method with their business orchestration.
        """
        logger = workflow.logger
        self._status = "running"
        self._progress = 0

        logger.info(
            "Starting 3-step workflow",
            extra={
                "user_name": input_data.user_name,
                "task_type": input_data.task_type,
                "priority": self._priority,
            },
        )

        # STEP 1: Call my_activity for initial processing
        self._progress = 33
        logger.info("Step 1/3: Calling my_activity for initial processing")

        activity_data = {
            "name": input_data.user_name,
            "type": input_data.task_type,
            "priority": self._priority,
            "language": input_data.language,
        }

        # Call my_activity
        activity_result = await execute_activity(
            "my_activity",
            args=[activity_data],
            start_to_close_timeout=timedelta(minutes=2),
        )

        logger.info("Step 1/3 completed: my_activity processing successful")

        # STEP 2: Call mock-strands-agent via call_strands_agent activity
        self._progress = 66
        logger.info(
            "Step 2/3: Calling mock-strands-agent via call_strands_agent activity"
        )

        service_config = await execute_activity(
            "get_service_config_activity",
            args=["mock_strands_agent"],
            start_to_close_timeout=timedelta(seconds=10),
        )
        agent_url = service_config["url"]
        task_prompt = f"Generate a personalized {input_data.task_type} for {input_data.user_name} in {input_data.language}. Initial processing: {activity_result.get('message', 'completed')}"
        query_extra_data = {
            "workflow_id": workflow.info().workflow_id,
            "user_name": input_data.user_name,
            "task_type": input_data.task_type,
            "language": input_data.language,
            "priority": self._priority,
            "activity_result": activity_result,
        }

        # Call foundry-temporal-agents call_strands_agent activity
        agent_result = await execute_activity(
            "call_strands_agent",
            args=[
                agent_url,
                task_prompt,
                query_extra_data,
                None,
            ],  # agent_url, task, query_extra_data, session_id
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=STRANDS_AGENT_RETRY_POLICY,
            heartbeat_timeout=timedelta(seconds=30),  # More reasonable for agent calls
        )

        # Handle agent result
        agent_message = (
            str(agent_result) if agent_result else f"Hello {input_data.user_name}!"
        )

        logger.info("Step 2/3 completed: Agent call successful")

        # Combine results from both activities
        self._message = f"Activity: {activity_result.get('message', 'processed')} | Agent: {agent_message}"

        # STEP 3: Open the review phase and wait for an approval or cancellation
        # bound to the content under review (using HILSignalsMixin)
        self._review_content = self._message
        content_digest = hashlib.sha256(self._review_content.encode()).hexdigest()
        self.open_review(content_digest)

        # QueryMixin.get_status() reports current_phase; the gateway's
        # approve route (temporal-workflow-api-starter) requires it to read
        # "awaiting_review" before it will relay an approval signal.
        self.current_phase = "awaiting_review"
        self._status = "waiting_for_approval"
        self._progress = 90
        logger.info("Step 3/3: Waiting for human approval via approve signal")

        # Block workflow execution until a bound approval or a cancellation is
        # received, or the review times out.
        try:
            await workflow.wait_condition(
                lambda: self.approved or self.cancelled,
                timeout=timedelta(minutes=10),  # Timeout after 10 minutes
            )
        except TimeoutError:
            self.current_phase = "timed_out"
            self._status = "timed_out"
            logger.info("Step 3/3: Review timed out with no approval or cancellation")
            return MyWorkflowResult(
                success=False,
                message="Review timed out before a decision was received",
                outcome="timed_out",
                data={"steps_completed": 2},
            )

        if self.cancelled:
            self.current_phase = "denied"
            self._status = "denied"
            logger.info(
                "Step 3/3: Review cancelled",
                extra={"cancelled_by": self.cancelled_by},
            )
            return MyWorkflowResult(
                success=False,
                message="Review was cancelled before approval",
                outcome="denied",
                data={"steps_completed": 2, "cancelled_by": self.cancelled_by},
            )

        logger.info("Step 3/3 completed: Approval received - finalizing workflow")

        # Final processing
        self._result_data = {
            "user_name": input_data.user_name,
            "task_type": input_data.task_type,
            "priority": self._priority,
            "language": input_data.language,
            "activity_result": activity_result,
            "agent_result": agent_message,
            "steps_completed": 3,
            "approved_by": self.approved_by,
        }

        self._progress = 100
        self.current_phase = "completed"
        self._status = "completed"

        logger.info("3-step workflow completed successfully")

        return MyWorkflowResult(
            success=True,
            message=self._message,
            outcome="approved",
            data=self._result_data,
        )

    @workflow.query
    def get_review_content(self) -> dict[str, str]:
        """Return the content currently open for review and its digest."""
        return {
            "content": self._review_content,
            "content_digest": self._expected_digest or "",
        }
