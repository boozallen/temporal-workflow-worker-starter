# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Pytest configuration and fixtures for temporal workflow worker tests.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(scope="session")
def event_loop() -> Generator[Any]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def app_config():
    """Create test configuration."""
    from src.config import AppConfig

    # Use test environment variables
    os.environ["TEMPORAL_HOST"] = "localhost:7233"
    os.environ["TEMPORAL_NAMESPACE"] = "default"
    os.environ["TASK_QUEUE"] = "test-task-queue"
    os.environ["WORKER_IDENTITY"] = "test-worker"
    os.environ["TEMPORAL_AUTH_TOKEN_URL"] = "https://auth.test/token"
    os.environ["TEMPORAL_AUTH_CLIENT_ID"] = "test-client"

    return AppConfig()


@pytest.fixture
def workflow_input():
    """Create a sample workflow input for testing."""
    from src.models import MyWorkflowInput

    return MyWorkflowInput(
        user_name="Test User",
        task_type="greeting",
        priority=1,
        language="en",
        metadata={"test_data": "sample data", "test_param": "test_value"},
    )


@pytest.fixture
def workflow_result():
    """Create a sample workflow result for testing."""
    from src.models import MyWorkflowResult

    return MyWorkflowResult(
        success=True,
        message="Hello Test User!",
        processing_time=2.5,
        source="mock_strands_agent",
        data={
            "user_name": "Test User",
            "task_type": "greeting",
            "priority": 1,
            "language": "en",
        },
    )


@pytest.fixture
def mock_activity() -> AsyncMock:
    """Create a mock activity for testing."""
    mock = AsyncMock()
    mock.return_value = {"status": "completed", "data": "test data"}
    return mock


@pytest.fixture
def yaml_config_path() -> Path:
    """Path to test YAML config files."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_workflows_config() -> dict[str, Any]:
    """Sample workflows configuration for testing."""
    return {
        "workflows": [
            {
                "name": "TestWorkflow",
                "module": "src.workflows",
                "class": "TestWorkflow",
                "task_queue": "test-task-queue",
            }
        ]
    }


@pytest.fixture
def sample_activities_config() -> dict[str, Any]:
    """Sample activities configuration for testing."""
    return {
        "activities": [
            {
                "name": "test_activity_1",
                "module": "src.activities",
                "function": "test_activity_1",
            },
            {
                "name": "test_activity_2",
                "module": "src.activities",
                "function": "test_activity_2",
            },
        ]
    }


@pytest.fixture
def mock_temporal_client():
    """Create a mock Temporal client for testing."""
    mock_client = AsyncMock()
    mock_client.get_workflow_handle.return_value = AsyncMock()
    mock_client.start_workflow.return_value = AsyncMock()
    return mock_client


@pytest.fixture(autouse=True)
def disable_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop AppConfig from reading the developer's .env, so results don't depend on it."""
    from src.config import AppConfig

    monkeypatch.setitem(AppConfig.model_config, "env_file", None)


@pytest.fixture(autouse=True)
def reset_config_cache():
    """Reset the global config cache before each test."""
    import src.config

    src.config._config = None
    yield
    src.config._config = None


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow running tests")
    config.addinivalue_line("markers", "workflow: Workflow execution tests")
    config.addinivalue_line("markers", "activity: Activity execution tests")
