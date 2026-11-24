# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
TEMPLATE: Unit tests for workflow implementations

These tests demonstrate how to test foundry-temporal workflows.
Teams should customize these tests for their specific workflows and business logic.
"""

import asyncio
import hashlib
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.models import MyWorkflowInput, MyWorkflowResult
from src.workflows import MyWorkflow


class TestMyWorkflow:
    """
    TEMPLATE: Test MyWorkflow implementation.

    Teams should customize these tests for their workflow logic.
    """

    def test_workflow_initialization(self):
        """Test that MyWorkflow initializes correctly."""
        workflow = MyWorkflow()

        # Verify initialization state
        assert workflow._status == "initialized"
        assert workflow._progress == 0
        assert workflow._result_data == {}

    def test_workflow_has_required_methods(self):
        """Test that MyWorkflow has all required signal and query methods."""
        workflow = MyWorkflow()

        # Test HILSignalsMixin signal handlers exist
        assert hasattr(workflow, "approve")

        # Test main workflow method exists
        assert hasattr(workflow, "run")
        assert callable(workflow.run)

    @pytest.mark.asyncio
    @patch("src.workflows.workflow")
    @patch("src.workflows.execute_activity", new_callable=AsyncMock)
    async def test_workflow_run_three_steps(self, mock_execute_activity, mock_workflow):
        """Test that workflow.run executes 3 steps in order:
        1. my_activity
        2. get_service_config_activity
        3. call_strands_agent (foundry-temporal-agents)
        4. Wait for approve signal (HIL)
        """
        # Setup mocks
        mock_workflow.logger = Mock()
        mock_workflow.info.return_value = Mock(workflow_id="test-wf-001")

        # First execute_activity call → my_activity result
        # Second execute_activity call → get_service_config_activity result
        # Third execute_activity call → call_strands_agent result
        mock_execute_activity.side_effect = [
            {"success": True, "message": "Activity processed"},  # my_activity
            {"url": "http://mock-agent:8080"},  # get_service_config_activity
            "Agent response for user",  # call_strands_agent
        ]

        # Make wait_condition resolve immediately (simulate approval received)
        mock_workflow.wait_condition = AsyncMock()

        wf = MyWorkflow()
        input_data = MyWorkflowInput(
            user_name="Alice", task_type="greeting", language="en"
        )

        result = await wf.run(input_data)

        # --- Verify 3 steps executed in order ---

        # Step 1: my_activity called first
        first_call = mock_execute_activity.call_args_list[0]
        assert first_call[0][0] == "my_activity"

        # Step 2: get_service_config_activity called second
        second_call = mock_execute_activity.call_args_list[1]
        assert second_call[0][0] == "get_service_config_activity"

        # Step 3: call_strands_agent called third
        third_call = mock_execute_activity.call_args_list[2]
        assert third_call[0][0] == "call_strands_agent"

        # Step 3: approve signal wait
        mock_workflow.wait_condition.assert_awaited_once()

        # Verify exactly 3 activity calls (my_activity + get_service_config_activity + call_strands_agent)
        assert mock_execute_activity.await_count == 3

        # Verify final result
        assert isinstance(result, MyWorkflowResult)
        assert result.success is True
        assert result.outcome == "approved"
        assert "Activity processed" in result.message
        assert "Agent response for user" in result.message
        assert result.data["steps_completed"] == 3
        assert wf._status == "completed"
        assert wf._progress == 100

    @pytest.mark.asyncio
    @patch("src.workflows.workflow")
    @patch("src.workflows.execute_activity", new_callable=AsyncMock)
    async def test_get_review_content_query_exposes_content_and_digest(
        self, mock_execute_activity, mock_workflow
    ):
        """The review-content query returns the content and digest bound to the open review."""
        mock_workflow.logger = Mock()
        mock_workflow.info.return_value = Mock(workflow_id="test-wf-004")
        mock_execute_activity.side_effect = [
            {"success": True, "message": "Activity processed"},
            {"url": "http://mock-agent:8080"},
            "Agent response for user",
        ]

        wf = MyWorkflow()

        async def _query_while_open(*_args: object, **_kwargs: object) -> None:
            response = wf.get_review_content()
            expected_digest = hashlib.sha256(response["content"].encode()).hexdigest()
            assert response["content_digest"] == expected_digest
            assert wf._review_open is True

        mock_workflow.wait_condition = AsyncMock(side_effect=_query_while_open)

        input_data = MyWorkflowInput(
            user_name="Alice", task_type="greeting", language="en"
        )
        await wf.run(input_data)

    def test_approve_signal_requires_open_review_and_matching_digest(self):
        """Approval only releases the gate while review is open and the digest matches."""
        wf = MyWorkflow()
        assert wf.approved is False

        # No review phase open yet: approval is a silent no-op.
        wf.approve("alice", "some-digest")
        assert wf.approved is False

        digest = hashlib.sha256(b"content under review").hexdigest()
        wf.open_review(digest)

        # Review is open but the digest does not match: no-op.
        wf.approve("alice", "wrong-digest")
        assert wf.approved is False

        # Matching digest and a non-empty approver releases the gate.
        wf.approve("alice", digest)
        assert wf.approved is True
        assert wf.approved_by == "alice"

    @pytest.mark.asyncio
    @patch("src.workflows.workflow")
    @patch("src.workflows.execute_activity", new_callable=AsyncMock)
    async def test_cancel_during_review_yields_denied_outcome(
        self, mock_execute_activity, mock_workflow
    ):
        """A cancel signal received while review is open ends the run denied."""
        mock_workflow.logger = Mock()
        mock_workflow.info.return_value = Mock(workflow_id="test-wf-002")
        mock_execute_activity.side_effect = [
            {"success": True, "message": "Activity processed"},
            {"url": "http://mock-agent:8080"},
            "Agent response",
        ]

        wf = MyWorkflow()

        def _simulate_cancel(*_args: object, **_kwargs: object) -> None:
            wf.cancel_workflow("alice")

        mock_workflow.wait_condition = AsyncMock(side_effect=_simulate_cancel)

        input_data = MyWorkflowInput(
            user_name="Alice", task_type="greeting", language="en"
        )
        result = await wf.run(input_data)

        assert result.success is False
        assert result.outcome == "denied"
        assert result.data["cancelled_by"] == "alice"
        assert wf._status == "denied"

    @pytest.mark.asyncio
    @patch("src.workflows.workflow")
    @patch("src.workflows.execute_activity", new_callable=AsyncMock)
    async def test_review_timeout_yields_timed_out_outcome_without_raising(
        self, mock_execute_activity, mock_workflow
    ):
        """A review timeout ends the run timed out instead of raising."""
        mock_workflow.logger = Mock()
        mock_workflow.info.return_value = Mock(workflow_id="test-wf-003")
        mock_execute_activity.side_effect = [
            {"success": True, "message": "Activity processed"},
            {"url": "http://mock-agent:8080"},
            "Agent response",
        ]

        wf = MyWorkflow()
        mock_workflow.wait_condition = AsyncMock(side_effect=asyncio.TimeoutError)

        input_data = MyWorkflowInput(
            user_name="Alice", task_type="greeting", language="en"
        )
        result = await wf.run(input_data)

        assert result.success is False
        assert result.outcome == "timed_out"
        assert wf._status == "timed_out"

    def test_workflow_state_management(self):
        """Test workflow state management during execution."""
        workflow = MyWorkflow()

        # Test initial state
        assert workflow._status == "initialized"
        assert workflow._progress == 0

        # Test state updates
        workflow._status = "running"
        workflow._progress = 50
        workflow._result_data = {"step1": "completed"}

        assert workflow._status == "running"
        assert workflow._progress == 50
        assert workflow._result_data["step1"] == "completed"


# DEPRECATED: Tests for GreetingWorkflow which doesn't exist
# class TestGreetingWorkflow:
#     """
#     TEMPLATE: Test GreetingWorkflow implementation.
#
#     Teams should customize for their simple workflow patterns.
#     """
#
#     def test_workflow_initialization(self):
#         """Test that GreetingWorkflow initializes correctly."""
#         workflow = GreetingWorkflow()
#
#         # GreetingWorkflow is simpler - just verify it can be created
#         assert hasattr(workflow, "run")
#         assert callable(workflow.run)
#
#     def test_workflow_has_required_methods(self):
#         """Test that GreetingWorkflow has required methods."""
#         workflow = GreetingWorkflow()
#
#         # Test main workflow method exists
#         assert hasattr(workflow, "run")
#         assert callable(workflow.run)


class TestWorkflowInputModels:
    """
    TEMPLATE: Test workflow input model validation.

    Teams should add tests for their specific data models.
    """

    def test_example_workflow_input_model(self):
        """Test MyWorkflowInput model validation."""
        # Test valid input
        input_data = MyWorkflowInput(
            user_name="Alice",
            task_type="data_processing",
            priority=5,
            metadata={"department": "engineering"},
        )

        assert input_data.user_name == "Alice"
        assert input_data.task_type == "data_processing"
        assert input_data.priority == 5
        assert input_data.metadata == {"department": "engineering"}

        # Test defaults
        minimal_input = MyWorkflowInput(user_name="Bob")
        assert minimal_input.task_type == "greeting"
        assert minimal_input.priority == 1
        assert minimal_input.metadata == {}

    def test_example_workflow_result_model(self):
        """Test MyWorkflowResult model validation."""
        # Test successful result
        result = MyWorkflowResult(
            success=True,
            message="Task completed successfully",
            processing_time=1.5,
            data={"steps": 3},
        )

        assert result.success is True
        assert result.message == "Task completed successfully"
        assert result.processing_time == 1.5
        assert result.data == {"steps": 3}

        # Test error result
        error_result = MyWorkflowResult(
            success=False, message="Task failed", data={"error": "timeout"}
        )

        assert error_result.success is False
        assert error_result.processing_time is None
        assert error_result.data == {"error": "timeout"}

    # DEPRECATED: Tests for GreetingWorkflow models which don't exist
    # def test_greeting_workflow_input_model(self):
    #     """Test GreetingWorkflowInput model validation."""
    #     # Test with defaults
    #     input_data = GreetingWorkflowInput(name="Charlie")
    #     assert input_data.name == "Charlie"
    #     assert input_data.language == "en"
    #     assert input_data.use_agent is False
    #
    #     # Test with custom values
    #     custom_input = GreetingWorkflowInput(
    #         name="Maria", language="es", use_agent=True
    #     )
    #     assert custom_input.name == "Maria"
    #     assert custom_input.language == "es"
    #     assert custom_input.use_agent is True
    #
    # def test_greeting_workflow_result_model(self):
    #     """Test GreetingWorkflowResult model validation."""
    #     import time
    #
    #     result = GreetingWorkflowResult(
    #         greeting="Hello, Alice!", timestamp=time.time(), source="template"
    #     )
    #
    #     assert result.greeting == "Hello, Alice!"
    #     assert result.timestamp > 0
    #     assert result.source == "template"


class TestWorkflowModelSerialization:
    """
    TEMPLATE: Test model serialization for foundry-temporal patterns.

    Teams should ensure their models serialize correctly for Temporal.
    """

    def test_input_model_serialization(self):
        """Test workflow input models serialize correctly."""
        input_data = MyWorkflowInput(
            user_name="Test User",
            task_type="test_task",
            priority=3,
            metadata={"key": "value"},
        )

        # Test serialization (Temporal uses this internally)
        serialized = input_data.model_dump()
        assert serialized["user_name"] == "Test User"
        assert serialized["task_type"] == "test_task"
        assert serialized["priority"] == 3
        assert serialized["metadata"] == {"key": "value"}

    def test_result_model_serialization(self):
        """Test workflow result models serialize correctly."""
        result = MyWorkflowResult(
            success=True,
            message="Test completed",
            processing_time=2.1,
            data={"items": 5},
        )

        # Test serialization
        serialized = result.model_dump()
        assert serialized["success"] is True
        assert serialized["message"] == "Test completed"
        assert serialized["processing_time"] == 2.1
        assert serialized["data"] == {"items": 5}


class TestWorkflowIntegrationPatterns:
    """
    TEMPLATE: Integration-style tests for workflow patterns.

    These test workflow structure without full Temporal execution.
    Teams should expand these for their workflows.
    """

    def test_example_workflow_structure(self):
        """Test MyWorkflow has proper structure for foundry-temporal."""
        workflow = MyWorkflow()

        # Verify workflow follows foundry-temporal patterns (standard Temporal workflow)
        # Since we use standard Temporal workflows, just verify the workflow instance exists
        assert workflow is not None

        # Verify workflow class exists (decorators are mocked in tests)
        assert MyWorkflow is not None

    # DEPRECATED: Test for GreetingWorkflow which doesn't exist
    # def test_greeting_workflow_structure(self):
    #     """Test GreetingWorkflow has proper structure."""
    #     workflow = GreetingWorkflow()
    #
    #     # Verify workflow follows foundry-temporal patterns (standard Temporal workflow)
    #     # Since we use standard Temporal workflows, just verify the workflow instance exists
    #     assert workflow is not None
    #
    #     # Verify workflow class exists (decorators are mocked in tests)
    #     assert GreetingWorkflow is not None

    def test_workflow_input_validation_patterns(self):
        """Test that workflows can handle various input patterns."""
        # Test that input models handle edge cases teams might encounter

        # Empty metadata
        input1 = MyWorkflowInput(user_name="Test", metadata={})
        assert input1.metadata == {}

        # Default metadata handling
        input2 = MyWorkflowInput(user_name="Test")
        assert input2.metadata == {}

        # Unicode names (common in global deployments)
        input3 = MyWorkflowInput(user_name="María José")
        assert input3.user_name == "María José"

    def test_error_result_patterns(self):
        """Test error handling result patterns."""
        # Test error result structure teams will need
        error_result = MyWorkflowResult(
            success=False,
            message="Activity timeout occurred",
            data={
                "error_type": "timeout",
                "failed_activity": "example_activity",
                "retry_count": 3,
            },
        )

        assert error_result.success is False
        assert "timeout" in error_result.message
        assert error_result.data["error_type"] == "timeout"
        assert error_result.data["retry_count"] == 3


# Teams can add more test classes here for their specific workflows:
#
# class TestYourCustomWorkflow:
#     """Test your custom workflow implementation."""
#
#     def test_your_workflow_logic(self):
#         """Test your specific workflow logic."""
#         pass
#
# class TestYourWorkflowModels:
#     """Test your custom data models."""
#
#     def test_your_input_model(self):
#         """Test your input model validation."""
#         pass
