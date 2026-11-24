# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
TEMPLATE: Unit tests for activity implementations

These tests demonstrate how to test foundry-temporal and foundry-temporal-agents activities.
Teams should customize these tests for their specific activities and business logic.
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from src.activities import (
    MyActivityResult,
    my_activity,
)


class TestMyActivity:
    """
    TEMPLATE: Test my_activity implementation.

    Teams should customize these tests for their activity logic.
    """

    @pytest.mark.asyncio
    @patch("src.activities.activity")
    async def test_my_activity_success(self, mock_activity: Mock) -> None:
        """Test my_activity with successful processing."""
        mock_activity.logger = Mock()
        mock_activity.info.return_value = Mock(activity_id="test-activity-123")
        mock_activity.heartbeat = Mock()

        data = {"name": "Alice", "type": "data_processing"}

        result = await my_activity(data)

        # Verify result structure
        assert isinstance(result, dict)
        assert "success" in result
        assert "message" in result
        assert "data" in result
        assert "processing_time" in result
        assert "timestamp" in result

        # Verify content
        assert result["success"] is True
        assert "Alice" in result["message"]
        assert "data_processing" in result["message"]
        assert result["data"]["name"] == "Alice"
        assert result["data"]["type"] == "data_processing"

        # Verify logging was called
        mock_activity.logger.info.assert_called()

    @pytest.mark.asyncio
    @patch("src.activities.activity")
    async def test_my_activity_long_running(self, mock_activity):
        """Test my_activity with long_running type (heartbeats)."""
        mock_activity.logger = Mock()
        mock_activity.info.return_value = Mock(activity_id="test-activity-456")
        mock_activity.heartbeat = Mock()

        data = {"name": "Bob", "type": "long_running"}

        result = await my_activity(data)

        # Verify result
        assert result["success"] is True
        assert result["data"]["steps_completed"] == 3

        # Verify heartbeat was called (3 steps for long_running)
        assert mock_activity.heartbeat.call_count == 3

    @pytest.mark.asyncio
    @patch("src.activities.activity")
    async def test_my_activity_with_default_type(self, mock_activity):
        """Test my_activity with default task type."""
        mock_activity.logger = Mock()
        mock_activity.info.return_value = Mock(activity_id="test-activity-default")
        mock_activity.heartbeat = Mock()

        data = {"name": "DefaultUser"}  # No type specified

        result = await my_activity(data)

        # Verify result structure
        assert isinstance(result, dict)
        assert result["success"] is True
        assert "DefaultUser" in result["message"]

    @pytest.mark.asyncio
    @patch("src.activities.asyncio.sleep", side_effect=Exception("simulated failure"))
    @patch("src.activities.activity")
    async def test_my_activity_error_handling(self, mock_activity, mock_sleep):
        """Test my_activity error handling path.

        The activity classifies errors via classify_and_wrap_error and re-raises,
        so Temporal can decide retry behaviour.
        """
        mock_activity.logger = Mock()
        mock_activity.info.return_value = Mock(activity_id="test-activity-error")
        mock_activity.heartbeat = Mock()

        data = {"name": "ErrorUser", "type": "greeting"}

        with pytest.raises(Exception, match="simulated failure"):
            await my_activity(data)

        mock_activity.logger.error.assert_called()


# DEPRECATED: TestGreetingActivity removed - greeting_activity doesn't exist
# class TestGreetingActivity:
#     """
#     TEMPLATE: Test greeting_activity implementation.
#     Teams should add this activity to activities.py if needed.
#     """
#     pass


# DEPRECATED: Tests for mock_agent_activity which is now commented out
# class TestMockAgentActivity:
#     """
#     TEMPLATE: Test mock_agent_activity implementation.
#
#     Teams should customize for their agent activity patterns.
#     """
#
#     @pytest.mark.asyncio
#     @patch("src.activities.activity")
#     async def test_mock_agent_activity_success(self, mock_activity):
#         """Test mock_agent_activity with successful processing."""
#         mock_activity.logger = Mock()
#
#         request = AgentRequest(
#             prompt="Generate a greeting for Alice",
#             context={"language": "en"},
#             timeout_seconds=30,
#         )
#
#         result = await mock_agent_activity(request)
#
#         # Verify result structure
#         assert isinstance(result, dict)
#         assert "result" in result
#         assert "success" in result
#         assert "agent_name" in result
#         assert "processing_time" in result
#
#         # Verify content
#         assert result["success"] is True
#         assert result["agent_name"] == "mock-strands-agent"
#         assert "Alice" in result["result"] or "greeting" in result["result"].lower()
#         assert result["processing_time"] >= 0
#
#         # Verify logging was called
#         mock_activity.logger.info.assert_called()
#
#     def test_agent_request_model(self):
#         """Test AgentRequest model validation."""
#         # Test valid request
#         request = AgentRequest(
#             prompt="Test prompt", context={"key": "value"}, timeout_seconds=60
#         )
#
#         assert request.prompt == "Test prompt"
#         assert request.context == {"key": "value"
#         assert request.timeout_seconds == 60
#
#         # Test defaults
#         minimal_request = AgentRequest(prompt="Simple test")
#         assert minimal_request.context == {}
#         assert minimal_request.timeout_seconds == 30
#
#     def test_agent_response_model(self):
#         """Test AgentResponse model validation."""
#         response = AgentResponse(
#             result="Test response",
#             success=True,
#             agent_name="test-agent",
#             processing_time=1.5,
#         )
#
#         assert response.result == "Test response"
#         assert response.success is True
#         assert response.agent_name == "test-agent"
#         assert response.processing_time == 1.5


# DEPRECATED: TestHttpRequestActivity removed - http_request_activity doesn't exist
# class TestHttpRequestActivity:
#     """
#     TEMPLATE: Test http_request_activity implementation.
#     Teams should add this activity to activities.py if needed.
#     """
#     pass


class TestActivityDataModels:
    """
    TEMPLATE: Test activity data model validation.

    Teams should add tests for their specific data models.
    """

    def test_my_activity_result_model(self):
        """Test MyActivityResult model validation."""
        # Test successful result
        result = MyActivityResult(
            success=True,
            message="Processing completed",
            data={"items": 5},
            processing_time=2.3,
            timestamp=datetime.utcnow().isoformat(),
        )

        assert result.success is True
        assert result.message == "Processing completed"
        assert result.data == {"items": 5}
        assert result.processing_time == 2.3

        # Test serialization
        serialized = result.model_dump()
        assert serialized["success"] is True
        assert "timestamp" in serialized

    def test_my_activity_result_error(self):
        """Test MyActivityResult model for error cases."""
        error_result = MyActivityResult(
            success=False,
            message="Processing failed",
            data={"error_code": "TIMEOUT"},
            processing_time=5.0,
            timestamp=datetime.utcnow().isoformat(),
        )

        assert error_result.success is False
        assert error_result.data["error_code"] == "TIMEOUT"


class TestActivityIntegrationPatterns:
    """
    TEMPLATE: Integration-style tests for activity patterns.

    These test activity structure without full Temporal execution.
    Teams should expand these for their activities.
    """

    def test_all_template_activities_importable(self):
        """Test that all template activities can be imported successfully."""
        # This ensures the activity module structure is correct
        from src.activities import (
            MyActivityResult,
            my_activity,
        )

        # Verify functions are callable
        assert callable(my_activity)
        assert MyActivityResult is not None

    def test_activity_decorators(self):
        """Test that activities have proper Temporal decorators."""

        # Verify activities are callable (decorators are mocked in tests)
        assert callable(my_activity)

    # DEPRECATED: Test disabled because agent models don't exist
    # def test_activity_error_handling_patterns(self):
    #     """Test common activity error handling patterns teams will need."""
    #     # Teams should add their own data models and test them here
    #     pass


# Teams can add more test classes here for their specific activities:
#
# class TestYourCustomActivity:
#     """Test your custom activity implementation."""
#
#     @pytest.mark.asyncio
#     @patch("src.activities.activity")
#     async def test_your_activity_logic(self, mock_activity):
#         """Test your specific activity logic."""
#         pass
#
# class TestYourAgentActivity:
#     """Test your agent activity implementation."""
#
#     @pytest.mark.asyncio
#     @patch("src.activities.activity")
#     async def test_your_agent_activity(self, mock_activity):
#         """Test your agent activity logic."""
#         pass
