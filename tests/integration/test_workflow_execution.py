# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
TEMPLATE: Integration tests for end-to-end workflow execution

These tests demonstrate integration testing patterns for foundry-temporal workflows.
Teams should customize these tests for their specific workflow requirements.

NOTE: Full integration tests require a running Temporal server.
Use external Temporal server or full infrastructure for testing.
"""

import asyncio
import hashlib
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import (
    SandboxedWorkflowRunner,
    SandboxRestrictions,
)

from src.activities import get_service_config_activity, my_activity
from src.config import get_config
from src.models import MyWorkflowInput

# Import template components for integration testing
from src.workflows import MyWorkflow

# `coverage` touches platform.python_implementation() the first time its own
# lazily-loaded submodules import, which can happen while sandboxed workflow
# code is executing under pytest-cov. Pass that one module through rather
# than disabling the sandbox outright, since the deployed worker always runs
# MyWorkflow sandboxed (see src/worker.py) and this keeps that check live.
_SANDBOX_RUNNER = SandboxedWorkflowRunner(
    restrictions=SandboxRestrictions.default.with_passthrough_modules("coverage")
)


@activity.defn(name="call_strands_agent")
async def _stub_call_strands_agent(
    agent_url: str, task: str, query_extra_data: dict, session_id: str | None
) -> str:
    """Stand-in for the real call_strands_agent activity - avoids a live HTTP call."""
    return "Stub agent response"


class TestWorkflowIntegration:
    """
    TEMPLATE: Integration tests for workflow execution patterns.

    These tests demonstrate how teams can test workflows with foundry-temporal.
    Teams should customize for their specific workflows and business logic.
    """

    @pytest.mark.integration
    def test_workflow_structure_integration(self):
        """
        Test that workflows are properly structured for integration.

        This verifies workflow and activity registration patterns.
        """
        # Test workflow classes exist and are importable
        assert MyWorkflow is not None
        # Note: GreetingWorkflow is not implemented in this template

        # Test activities exist and are callable
        assert callable(my_activity)

    @pytest.mark.integration
    def test_configuration_integration(self, monkeypatch):
        """
        Test that configuration works for integration scenarios.

        This verifies configuration loading and validation.
        """
        monkeypatch.setenv("TEMPORAL_AUTH_TOKEN_URL", "https://auth.test/token")
        monkeypatch.setenv("TEMPORAL_AUTH_CLIENT_ID", "test-client")
        config = get_config()

        # Verify essential configuration is available
        assert hasattr(config, "temporal_host")
        assert hasattr(config, "task_queue")
        assert hasattr(config, "worker_identity")

        # Verify configuration has reasonable defaults
        assert config.task_queue is not None
        assert config.worker_identity is not None

    @pytest.mark.integration
    def test_foundry_package_integration(self):
        """
        Test foundry package integration patterns.

        This verifies foundry packages can be imported and used.
        """
        # Test foundry-temporal integration
        from foundry_temporal import (
            HILSignalsMixin,
            ValidationError,
            classify_and_wrap_error,
        )
        from foundry_temporal.worker import (
            WorkerConfig,
            create_temporal_client,
            create_worker_with_defaults,
        )

        # Verify classes/functions can be imported
        assert WorkerConfig is not None
        assert create_temporal_client is not None
        assert create_worker_with_defaults is not None
        assert HILSignalsMixin is not None
        assert classify_and_wrap_error is not None
        assert issubclass(ValidationError, Exception)

        # Test foundry-temporal-agents integration
        from foundry_temporal_agents.activities import call_strands_agent

        # Verify activity can be imported
        assert call_strands_agent is not None

    @pytest.mark.integration
    def test_data_model_integration(self):
        """
        Test data model integration with Temporal serialization.

        This verifies Pydantic models work with Temporal's data handling.
        """
        from src.models import MyWorkflowInput, MyWorkflowResult

        # Test input model serialization
        input_data = MyWorkflowInput(
            user_name="Integration Test User",
            task_type="integration_test",
            priority=5,
            metadata={"test": "integration"},
        )

        # Verify serialization works (Temporal uses this)
        serialized = input_data.model_dump()
        assert isinstance(serialized, dict)
        assert serialized["user_name"] == "Integration Test User"

        # Test result model serialization
        result_data = MyWorkflowResult(
            success=True,
            message="Integration test completed",
            processing_time=1.0,
            data={"integration": True},
        )

        serialized_result = result_data.model_dump()
        assert isinstance(serialized_result, dict)
        assert serialized_result["success"] is True


class TestReviewApprovalGateIntegration:
    """
    Integration tests for the review-approval gate against a real (embedded,
    time-skipping) Temporal server - exercising actual signal and query dispatch
    rather than calling workflow methods directly as plain Python calls.
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_approval_bound_to_queried_digest_completes_approved(self):
        """Querying the content under review, then approving with its digest,
        completes the workflow with outcome="approved"."""
        task_queue = f"review-gate-{uuid.uuid4()}"
        async with (
            await WorkflowEnvironment.start_time_skipping() as env,
            Worker(
                env.client,
                task_queue=task_queue,
                workflows=[MyWorkflow],
                activities=[
                    my_activity,
                    get_service_config_activity,
                    _stub_call_strands_agent,
                ],
                workflow_runner=_SANDBOX_RUNNER,
            ),
        ):
            handle = await env.client.start_workflow(
                MyWorkflow.run,
                MyWorkflowInput(user_name="Alice", task_type="greeting"),
                id=f"review-gate-approved-{uuid.uuid4()}",
                task_queue=task_queue,
            )

            # Poll the query until the review phase is open, then approve
            # using the digest the query itself reports.
            async def _review_opened() -> dict[str, str]:
                while True:
                    content = await handle.query(MyWorkflow.get_review_content)
                    if content["content_digest"]:
                        return content
                    await asyncio.sleep(0.1)

            review = await asyncio.wait_for(_review_opened(), timeout=10)
            expected_digest = hashlib.sha256(review["content"].encode()).hexdigest()
            assert review["content_digest"] == expected_digest

            await handle.signal(
                MyWorkflow.approve, args=["alice", review["content_digest"]]
            )

            result = await handle.result()
            assert result.success is True
            assert result.outcome == "approved"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cancel_during_review_completes_denied(self):
        """A cancel_workflow signal sent during the open review phase completes
        the workflow with outcome="denied"."""
        task_queue = f"review-gate-{uuid.uuid4()}"
        async with (
            await WorkflowEnvironment.start_time_skipping() as env,
            Worker(
                env.client,
                task_queue=task_queue,
                workflows=[MyWorkflow],
                activities=[
                    my_activity,
                    get_service_config_activity,
                    _stub_call_strands_agent,
                ],
                workflow_runner=_SANDBOX_RUNNER,
            ),
        ):
            handle = await env.client.start_workflow(
                MyWorkflow.run,
                MyWorkflowInput(user_name="Bob", task_type="greeting"),
                id=f"review-gate-denied-{uuid.uuid4()}",
                task_queue=task_queue,
            )

            async def _review_opened() -> None:
                while True:
                    content = await handle.query(MyWorkflow.get_review_content)
                    if content["content_digest"]:
                        return
                    await asyncio.sleep(0.1)

            await asyncio.wait_for(_review_opened(), timeout=10)

            await handle.signal(MyWorkflow.cancel_workflow, "bob")

            result = await handle.result()
            assert result.success is False
            assert result.outcome == "denied"
            assert result.data["cancelled_by"] == "bob"


class TestDockerIntegration:
    """
    TEMPLATE: Docker-based integration test patterns.

    These tests demonstrate how to test with Docker compose infrastructure.
    Teams should expand these for their deployment testing needs.
    """

    @pytest.mark.integration
    @pytest.mark.docker
    def test_docker_compose_configuration(self):
        """
        Test Docker compose configuration is valid.

        This verifies the compose.yaml setup for integration testing.
        """
        from pathlib import Path

        import yaml

        # Read compose.yaml file
        compose_file = Path(__file__).parent.parent.parent / "compose.yaml"
        assert compose_file.exists(), "compose.yaml file should exist"

        with compose_file.open() as f:
            compose_config = yaml.safe_load(f)

        # Verify essential services exist
        services = compose_config.get("services", {})
        assert "worker" in services

        # Verify network configuration
        assert "networks" in compose_config

    @pytest.mark.integration
    @pytest.mark.docker
    @pytest.mark.slow
    def test_environment_configuration(self):
        """
        Test environment configuration for Docker deployment.

        This verifies env.template has required configuration.
        """
        from pathlib import Path

        env_template = Path(__file__).parent.parent.parent / "env.template"
        assert env_template.exists(), "env.template file should exist"

        with env_template.open() as f:
            env_content = f.read()

        # Verify essential environment variables are defined
        required_vars = [
            "TEMPORAL_HOST",
            "TEMPORAL_NAMESPACE",
            "TASK_QUEUE",
            "WORKER_IDENTITY",
        ]

        for var in required_vars:
            assert var in env_content, (
                f"Environment variable {var} should be in template"
            )


class TestTemplateIntegration:
    """
    TEMPLATE: Template structure integration testing patterns.

    These demonstrate how teams can test their template structure and core files.
    """

    @pytest.mark.integration
    def test_template_files_exist(self):
        """
        Test that template files exist and are structured correctly.
        """
        from pathlib import Path

        template_root = Path(__file__).parent.parent.parent

        # Verify core template files exist
        core_files = [
            "src/workflows.py",
            "src/activities.py",
            "src/worker.py",
            "src/config.py",
        ]

        for file_name in core_files:
            template_file = template_root / file_name
            assert template_file.exists(), f"Template file {file_name} should exist"

    @pytest.mark.integration
    def test_documentation_integration(self):
        """
        Test that documentation is properly integrated.
        """
        from pathlib import Path

        docs_dir = Path(__file__).parent.parent.parent / "docs" / "foundry"
        assert docs_dir.exists()

        # Verify documentation files exist. Paths are relative to docs/foundry/ and
        # match the section layout the docs site expects (docs-path: docs/foundry).
        doc_files = [
            "index.md",
            "getting-started/getting-started.md",
            "guides/customization-guide.md",
            "operations/deployment.md",
        ]

        for file_name in doc_files:
            doc_file = docs_dir / file_name
            assert doc_file.exists(), f"Documentation file {file_name} should exist"


# Teams can add more integration test classes here:
#
# @pytest.mark.integration
# class TestYourWorkflowIntegration:
#     """Integration tests for your specific workflows."""
#
#     @pytest.mark.asyncio
#     async def test_your_workflow_end_to_end(self):
#         """Test your workflow from start to finish."""
#         pass
#
# @pytest.mark.integration
# @pytest.mark.docker
# class TestYourDeploymentIntegration:
#     """Integration tests for your deployment scenarios."""
#
#     def test_your_deployment_config(self):
#         """Test your deployment configuration."""
#         pass


# Integration test execution notes for teams:
#
# 1. Unit tests (tests/unit/): Fast, isolated, mock dependencies
#    - Run with: pytest tests/unit/
#    - Test workflow logic without Temporal runtime
#
# 2. Integration tests (tests/integration/): Test component integration
#    - Run with: pytest tests/integration/
#    - Test foundry package integration
#    - Test configuration and Docker setup
#
# 3. End-to-end tests: Test with running Temporal server
#    - Start: docker-compose up worker (with external Temporal server)
#    - Run: python -m src.worker
#    - Verify: Check Temporal UI at http://localhost:8080
#
# 4. Performance tests: Test with load and real scenarios
#    - Run multiple workflows concurrently
#    - Test with real agent integrations
#    - Monitor resource usage and timing
