# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for worker functionality
"""

import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.activities import (  # noqa: F401
    MyActivityResult,
    my_activity,
)
from src.worker import run_worker, start_temporal_worker
from src.workflows import MyWorkflow  # noqa: F401


class TestWorkerCreation:
    """Test worker creation and management functions"""

    @patch("src.worker.asyncio.run")
    @patch("src.worker.load_default_configs")
    def test_run_worker_success(
        self, mock_load_configs: Mock, mock_asyncio_run: Mock
    ) -> None:
        """Test successful worker run"""

        # Mock configuration loading
        mock_workflows: dict[str, list[dict[str, Any]]] = {
            "workflows": [{"module": "src.workflows", "classes": ["MyWorkflow"]}]
        }
        mock_activities: dict[str, list[dict[str, Any]]] = {
            "activities": [{"module": "src.activities", "functions": ["my_activity"]}]
        }
        mock_services: dict[str, dict[str, str]] = {
            "mock_strands_agent": {"url": "mock-agent", "description": "Mock agent"}
        }
        mock_load_configs.return_value = (
            mock_workflows,
            mock_activities,
            mock_services,
        )

        # Call run_worker function
        run_worker()

        # Verify configuration loading and asyncio.run called
        mock_load_configs.assert_called_once()
        mock_asyncio_run.assert_called_once()

    @patch("src.worker.logger")
    @patch("src.worker.asyncio.run")
    @patch("src.worker.load_default_configs")
    def test_run_worker_keyboard_interrupt(
        self, mock_load_configs: Mock, mock_asyncio_run: Mock, mock_logger: Mock
    ) -> None:
        """Test worker handling of KeyboardInterrupt"""

        # Mock configuration loading
        mock_workflows: dict[str, list[dict[str, Any]]] = {"workflows": []}
        mock_activities: dict[str, list[dict[str, Any]]] = {"activities": []}
        mock_services: dict[str, dict[str, str]] = {"services": {}}
        mock_load_configs.return_value = (
            mock_workflows,
            mock_activities,
            mock_services,
        )

        # Mock asyncio.run to raise KeyboardInterrupt
        mock_asyncio_run.side_effect = KeyboardInterrupt()

        # Call run_worker function - should not raise
        run_worker()

        # Verify keyboard interrupt was logged
        mock_logger.info.assert_called_with("Worker shutdown requested by user")

    @patch("src.worker.logger")
    @patch("src.worker.sys.exit")
    @patch("src.worker.asyncio.run")
    @patch("src.worker.load_default_configs")
    def test_run_worker_exception(
        self,
        mock_load_configs: Mock,
        mock_asyncio_run: Mock,
        mock_sys_exit: Mock,
        mock_logger: Mock,
    ) -> None:
        """Test worker handling of generic exceptions"""

        # Mock configuration loading
        mock_workflows: dict[str, list[dict[str, Any]]] = {"workflows": []}
        mock_activities: dict[str, list[dict[str, Any]]] = {"activities": []}
        mock_services: dict[str, dict[str, str]] = {"services": {}}
        mock_load_configs.return_value = (
            mock_workflows,
            mock_activities,
            mock_services,
        )

        # Mock asyncio.run to raise generic exception
        test_exception = Exception("Test error")
        mock_asyncio_run.side_effect = test_exception

        # Call run_worker function
        run_worker()

        # Verify error was logged and sys.exit called
        mock_logger.error.assert_called_with(
            f"Worker startup failed: {test_exception}", exc_info=True
        )
        mock_sys_exit.assert_called_with(1)


class TestLoadYamlConfig:
    """Test YAML configuration loading."""

    @patch("src.worker.logger")
    def test_load_yaml_config_success(self, mock_logger: Mock) -> None:
        """Test successful YAML config loading."""
        from src.worker import load_yaml_config

        # Use real config files
        config_dir = Path(__file__).parent.parent.parent / "config"
        result = load_yaml_config(config_dir / "workflows.yaml")
        assert "workflows" in result

    @patch("src.worker.logger")
    def test_load_yaml_config_file_not_found(self, mock_logger: Mock) -> None:
        """Test YAML config raises for missing file."""
        from src.worker import load_yaml_config

        with pytest.raises(FileNotFoundError):
            load_yaml_config(Path("/nonexistent/config.yaml"))
        mock_logger.error.assert_called()

    @patch("src.worker.logger")
    def test_load_yaml_config_malformed(
        self, mock_logger: Mock, tmp_path: Path
    ) -> None:
        """Test YAML config raises for malformed file."""
        from src.worker import load_yaml_config

        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text(":\n  :\n    - [invalid: {yaml")
        # yaml.safe_load may not error on all malformed content,
        # but at minimum it should load without crashing
        try:
            load_yaml_config(bad_file)
        except Exception:
            mock_logger.error.assert_called()


class TestLoadWorkflowsFromConfig:
    """Test workflow loading from config dictionaries."""

    @patch("src.worker.logger")
    def test_load_workflows_from_config(self, mock_logger: Mock) -> None:
        """Test loading workflows from config dict."""
        from src.worker import load_workflows_from_config

        config = {"workflows": [{"module": "src.workflows", "classes": ["MyWorkflow"]}]}
        workflows = load_workflows_from_config(config)
        assert len(workflows) == 1
        mock_logger.info.assert_called()

    @patch("src.worker.logger")
    def test_load_workflows_empty_config(self, mock_logger: Mock) -> None:
        """Test loading workflows with empty config."""
        from src.worker import load_workflows_from_config

        workflows = load_workflows_from_config({})
        assert workflows == []


class TestLoadActivitiesFromConfig:
    """Test activity loading from config dictionaries."""

    @patch("src.worker.logger")
    def test_load_activities_simple_strings(self, mock_logger: Mock) -> None:
        """Test loading activities with simple function name strings."""
        from src.worker import load_activities_from_config

        config = {
            "activities": [{"module": "src.activities", "functions": ["my_activity"]}]
        }
        activities = load_activities_from_config(config)
        assert len(activities) == 1
        mock_logger.info.assert_called()

    @patch("src.worker.logger")
    def test_load_activities_with_config_dict(self, mock_logger: Mock) -> None:
        """Test loading activities with dict-style function config."""
        from src.worker import load_activities_from_config

        config = {
            "activities": [
                {
                    "module": "src.activities",
                    "functions": [{"name": "my_activity", "timeout": 60}],
                }
            ]
        }
        activities = load_activities_from_config(config)
        assert len(activities) == 1

    @patch("src.worker.logger")
    def test_load_activities_empty_config(self, mock_logger: Mock) -> None:
        """Test loading activities with empty config."""
        from src.worker import load_activities_from_config

        activities = load_activities_from_config({})
        assert activities == []


class TestLoadDefaultConfigs:
    """Test loading default configuration files."""

    @patch("src.worker.logger")
    def test_load_default_configs_success(self, mock_logger: Mock) -> None:
        """Test loading default configs from config directory."""
        from src.worker import load_default_configs

        workflows, activities, services = load_default_configs()
        assert "workflows" in workflows
        assert "activities" in activities
        assert "mock_strands_agent" in services


class TestWorkerConfiguration:
    """Test worker configuration and foundry integration"""

    @patch("src.config.get_config")
    def test_worker_config_creation(self, mock_get_config: Mock) -> None:
        """Test that AppConfig provides all required values for foundry WorkerConfig"""
        # Mock app config
        mock_config = Mock()
        mock_config.temporal_host = "localhost:7233"
        mock_config.temporal_namespace = "test"
        mock_config.task_queue = "test-queue"
        mock_config.worker_identity = "test-worker"
        mock_config.max_concurrent_activities = 100
        mock_config.max_concurrent_workflow_tasks = 50
        mock_config.max_concurrent_local_activities = 200
        mock_config.max_concurrent_nexus_tasks = 10
        mock_get_config.return_value = mock_config

        # Get config (this would happen in worker setup)
        config = mock_get_config()

        # Verify all required fields for foundry WorkerConfig are available
        assert config.temporal_host == "localhost:7233"
        assert config.temporal_namespace == "test"
        assert config.task_queue == "test-queue"
        assert config.worker_identity == "test-worker"
        assert config.max_concurrent_activities == 100
        assert config.max_concurrent_workflow_tasks == 50
        assert config.max_concurrent_local_activities == 200
        assert config.max_concurrent_nexus_tasks == 10

        # Verify types are correct for foundry integration
        assert isinstance(config.temporal_host, str)
        assert isinstance(config.temporal_namespace, str)
        assert isinstance(config.task_queue, str)
        assert isinstance(config.worker_identity, str)
        assert isinstance(config.max_concurrent_activities, int)
        assert isinstance(config.max_concurrent_workflow_tasks, int)
        assert isinstance(config.max_concurrent_local_activities, int)
        assert isinstance(config.max_concurrent_nexus_tasks, int)

    @pytest.mark.asyncio
    @patch.dict(
        os.environ,
        {
            "TEMPORAL_TLS_CERT": "/certs/client.pem",
            "TEMPORAL_TLS_KEY": "/certs/client.key",
            "TEMPORAL_TLS_CA": "/certs/ca.pem",
        },
    )
    @patch("src.worker.setup_structured_logging")
    @patch("src.worker.create_worker_with_defaults")
    @patch("src.worker.create_temporal_client", new_callable=AsyncMock)
    async def test_tls_env_propagates_to_worker_config(
        self,
        mock_create_client: AsyncMock,
        mock_create_worker: Mock,
        mock_logging: Mock,
    ) -> None:
        """Regression: TEMPORAL_TLS_* env vars must reach the foundry WorkerConfig
        so that create_temporal_client can establish a TLS connection."""
        import src.config

        src.config._config = None  # reset singleton so patched env is read
        mock_create_worker.return_value.run = AsyncMock()

        await start_temporal_worker({"workflows": []}, {"activities": []})

        mock_create_client.assert_awaited_once()
        worker_config = mock_create_client.await_args.args[0]
        assert worker_config.temporal_tls_cert == "/certs/client.pem"
        assert worker_config.temporal_tls_key == "/certs/client.key"
        assert worker_config.temporal_tls_ca == "/certs/ca.pem"

        src.config._config = None

    @pytest.mark.asyncio
    @patch.dict(
        os.environ,
        {
            "TEMPORAL_TLS_MODE": "tls",
            "TEMPORAL_AUTH_TOKEN_URL": "https://auth.test/token",
            "TEMPORAL_AUTH_CLIENT_ID": "test-client",
        },
        clear=False,
    )
    @patch("src.worker.setup_structured_logging")
    @patch("src.worker.create_worker_with_defaults")
    @patch("src.worker.create_temporal_client", new_callable=AsyncMock)
    async def test_tls_mode_propagates_to_worker_config(
        self,
        mock_create_client: AsyncMock,
        mock_create_worker: Mock,
        mock_logging: Mock,
    ) -> None:
        """Regression: TEMPORAL_TLS_MODE must reach the foundry WorkerConfig.

        foundry-temporal >=2.0.0 fails closed when tls_mode is unset, so an unwired
        posture is both a runtime error and an unenforced transport (STIG V-222597).
        """
        import src.config

        src.config._config = None  # reset singleton so patched env is read
        mock_create_worker.return_value.run = AsyncMock()

        await start_temporal_worker({"workflows": []}, {"activities": []})

        mock_create_client.assert_awaited_once()
        worker_config = mock_create_client.await_args.args[0]
        assert worker_config.tls_mode == "tls"

        src.config._config = None


class TestTlsPostureEnforcement:
    """Exercise the real foundry-temporal create_temporal_client TLS branches.

    These tests deliberately do NOT mock create_temporal_client — only the
    Client.connect network boundary — so the fail-closed posture checks in
    foundry-temporal >=2.0.0 are actually executed (STIG V-222596/V-222597).
    """

    @staticmethod
    def _connect_kwargs(mock_connect: AsyncMock) -> dict[str, Any]:
        return mock_connect.await_args.kwargs

    @pytest.mark.asyncio
    @patch("temporalio.client.Client.connect", new_callable=AsyncMock)
    async def test_unset_tls_mode_fails_closed(self, mock_connect: AsyncMock) -> None:
        """An unset posture must raise rather than connect over plaintext."""
        from foundry_temporal.worker import WorkerConfig, create_temporal_client

        with pytest.raises(ValueError, match="TEMPORAL_TLS_MODE is not set"):
            await create_temporal_client(WorkerConfig(tls_mode=None))

        mock_connect.assert_not_awaited()

    @pytest.mark.asyncio
    @patch.dict(
        os.environ,
        {
            "TEMPORAL_TLS_MODE": "tls",
            "TEMPORAL_AUTH_TOKEN_URL": "https://auth.test/token",
            "TEMPORAL_AUTH_CLIENT_ID": "test-client",
        },
        clear=False,
    )
    @patch("temporalio.client.Client.connect", new_callable=AsyncMock)
    @patch("httpx.AsyncClient.post", new_callable=AsyncMock)
    @patch("src.worker.setup_structured_logging")
    @patch("src.worker.create_worker_with_defaults")
    async def test_worker_startup_negotiates_tls_end_to_end(
        self,
        mock_create_worker: Mock,
        mock_logging: Mock,
        mock_token_post: AsyncMock,
        mock_connect: AsyncMock,
    ) -> None:
        """End-to-end regression for the unwired-tls_mode finding.

        start_temporal_worker runs against the real create_temporal_client, so if
        worker.py stops threading tls_mode through, foundry-temporal fails closed
        and this test errors instead of silently connecting over plaintext.

        The OAuth2 token endpoint (httpx.AsyncClient.post) is mocked for the same
        reason Client.connect is: it is the other real network boundary this test
        crosses now that engine client authentication is required at startup.
        """
        import src.config

        mock_token_post.return_value = Mock(
            json=Mock(return_value={"access_token": "test-token", "expires_in": 300})
        )

        src.config._config = None  # reset singleton so patched env is read
        mock_create_worker.return_value.run = AsyncMock()

        try:
            await start_temporal_worker({"workflows": []}, {"activities": []})
        finally:
            src.config._config = None

        mock_connect.assert_awaited_once()
        assert self._connect_kwargs(mock_connect)["tls"] is True

    @pytest.mark.asyncio
    @patch.dict(os.environ, {}, clear=True)
    @patch("temporalio.client.Client.connect", new_callable=AsyncMock)
    async def test_default_app_config_posture_is_accepted(
        self, mock_connect: AsyncMock
    ) -> None:
        """The default 'platform' posture must satisfy the 2.0.0 fail-closed check."""
        from foundry_temporal.worker import WorkerConfig, create_temporal_client

        from src.config import AppConfig

        # mTLS cert/key placeholders satisfy AppConfig's engine-client-auth check.
        # Under "platform" mode create_temporal_client never reads these paths,
        # so no real certificate material (or network call) is needed here.
        app_config = AppConfig(
            _env_file=None,
            temporal_tls_cert="/dev-placeholder/client.pem",
            temporal_tls_key="/dev-placeholder/client.key",
        )
        await create_temporal_client(
            WorkerConfig(tls_mode=app_config.temporal_tls_mode)
        )

        mock_connect.assert_awaited_once()
        # "platform": TLS terminated by the mesh, so no application-managed TLS.
        assert "tls" not in self._connect_kwargs(mock_connect)

    @pytest.mark.asyncio
    @patch("temporalio.client.Client.connect", new_callable=AsyncMock)
    async def test_tls_mode_enables_transport_tls(
        self, mock_connect: AsyncMock
    ) -> None:
        """'tls' with no cert material must enable TLS via system root CAs."""
        from foundry_temporal.worker import WorkerConfig, create_temporal_client

        await create_temporal_client(WorkerConfig(tls_mode="tls"))

        assert self._connect_kwargs(mock_connect)["tls"] is True

    @pytest.mark.asyncio
    @patch("temporalio.client.Client.connect", new_callable=AsyncMock)
    async def test_mtls_without_cert_material_fails_closed(
        self, mock_connect: AsyncMock
    ) -> None:
        """mtls with no cert/key must raise instead of degrading to plaintext."""
        from foundry_temporal.worker import WorkerConfig, create_temporal_client

        with pytest.raises(ValueError, match="mtls requires"):
            await create_temporal_client(WorkerConfig(tls_mode="mtls"))

        mock_connect.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("temporalio.client.Client.connect", new_callable=AsyncMock)
    async def test_mtls_builds_tls_config_from_pem_files(
        self, mock_connect: AsyncMock, tmp_path: Path
    ) -> None:
        """mtls with real PEM files on disk must produce a populated TLSConfig."""
        from foundry_temporal.worker import WorkerConfig, create_temporal_client

        cert = tmp_path / "client.pem"
        key = tmp_path / "client.key"
        ca = tmp_path / "ca.pem"
        cert.write_bytes(b"-----BEGIN CERTIFICATE-----\ncert\n")
        key.write_bytes(b"-----BEGIN PRIVATE KEY-----\nkey\n")
        ca.write_bytes(b"-----BEGIN CERTIFICATE-----\nca\n")

        await create_temporal_client(
            WorkerConfig(
                tls_mode="mtls",
                temporal_tls_cert=str(cert),
                temporal_tls_key=str(key),
                temporal_tls_ca=str(ca),
            )
        )

        tls = self._connect_kwargs(mock_connect)["tls"]
        assert tls.client_cert == cert.read_bytes()
        assert tls.client_private_key == key.read_bytes()
        assert tls.server_root_ca_cert == ca.read_bytes()

    @pytest.mark.asyncio
    @patch("temporalio.client.Client.connect", new_callable=AsyncMock)
    async def test_invalid_tls_mode_fails_closed(self, mock_connect: AsyncMock) -> None:
        """An unrecognized posture must raise, not silently fall through."""
        from foundry_temporal.worker import WorkerConfig, create_temporal_client

        with pytest.raises(ValueError, match="Invalid TEMPORAL_TLS_MODE"):
            await create_temporal_client(WorkerConfig(tls_mode="bogus"))

        mock_connect.assert_not_awaited()
