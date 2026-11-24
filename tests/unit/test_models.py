# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Simple unit test for Pydantic models
"""

import pytest
from pydantic import ValidationError

from src.models import MyWorkflowInput, MyWorkflowResult


def test_my_workflow_input_validation() -> None:
    """Test MyWorkflowInput model validation works"""

    # Valid input
    input_data = MyWorkflowInput(user_name="John Doe", task_type="greeting")

    assert input_data.user_name == "John Doe"
    assert input_data.task_type == "greeting"
    assert input_data.priority == 1  # Default value
    assert input_data.language == "en"  # Default value
    assert input_data.metadata == {}  # Default value

    # Invalid input - missing required field should fail
    with pytest.raises(ValidationError):
        MyWorkflowInput(task_type="greeting")  # type: ignore[call-arg] # Missing required user_name


def test_user_name_exceeds_max_length() -> None:
    with pytest.raises(ValidationError):
        MyWorkflowInput(user_name="a" * 257)


def test_user_name_empty_string() -> None:
    with pytest.raises(ValidationError):
        MyWorkflowInput(user_name="")


def test_priority_below_minimum() -> None:
    with pytest.raises(ValidationError):
        MyWorkflowInput(user_name="test", priority=0)


def test_priority_above_maximum() -> None:
    with pytest.raises(ValidationError):
        MyWorkflowInput(user_name="test", priority=11)


def test_metadata_exceeds_max_keys() -> None:
    with pytest.raises(ValidationError):
        MyWorkflowInput(user_name="test", metadata={f"key_{i}": i for i in range(51)})


def test_valid_inputs_at_boundary_values() -> None:
    result = MyWorkflowInput(
        user_name="a" * 256,
        task_type="a" * 64,
        language="en",
        priority=10,
        metadata={f"key_{i}": i for i in range(50)},
    )
    assert len(result.user_name) == 256
    assert len(result.task_type) == 64
    assert result.priority == 10
    assert len(result.metadata) == 50


def test_my_workflow_result_creation() -> None:
    """Test MyWorkflowResult model creation"""

    # Success result
    result = MyWorkflowResult(
        success=True,
        message="Hello John Doe!",
        data={"user_name": "John Doe", "task_type": "greeting"},
    )

    assert result.success is True
    assert result.message == "Hello John Doe!"
    assert result.data == {"user_name": "John Doe", "task_type": "greeting"}
    assert result.processing_time is None  # Default value
    assert result.source == "mock-strands-agent"  # Default value

    # Custom result
    custom_result = MyWorkflowResult(
        success=False,
        message="Failed to process",
        processing_time=1.5,
        source="real_agent",
        data={"error": "timeout"},
    )

    assert custom_result.success is False
    assert custom_result.message == "Failed to process"
    assert custom_result.processing_time == 1.5
    assert custom_result.source == "real_agent"
    assert custom_result.data == {"error": "timeout"}
