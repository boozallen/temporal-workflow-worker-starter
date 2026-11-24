# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for configuration management
"""

import os
from unittest.mock import patch

import pytest

from src.config import AppConfig, get_config


@pytest.fixture(autouse=True)
def _default_engine_auth(monkeypatch):
    """Satisfy the engine-client-auth requirement for tests not exercising it directly.

    Tests that specifically exercise the auth validator clear the environment
    (`clear=True`) or pass explicit AppConfig kwargs, which take precedence over this.
    """
    monkeypatch.setenv("TEMPORAL_AUTH_TOKEN_URL", "https://auth.test/token")
    monkeypatch.setenv("TEMPORAL_AUTH_CLIENT_ID", "test-client")


class TestAppConfig:
    """Test AppConfig class functionality"""

    @patch.dict(os.environ, {}, clear=True)
    def test_default_configuration(self):
        """Test that AppConfig uses correct default values"""
        config = AppConfig(
            _env_file=None,
            temporal_auth_token_url="https://auth.test/token",
            temporal_auth_client_id="test-client",
        )  # Disable .env file loading to test code defaults

        # Verify default Temporal configuration (from code defaults)
        assert config.temporal_host == "localhost:7233"
        assert config.temporal_namespace == "default"
        assert config.task_queue == "workflow-task-queue"

        # Verify default worker configuration (from code defaults)
        assert config.worker_identity == "foundry-worker"
        assert config.log_level == "INFO"

    @patch.dict(
        os.environ,
        {
            "TEMPORAL_HOST": "prod-temporal:7233",
            "TEMPORAL_NAMESPACE": "production",
            "TASK_QUEUE": "custom-queue",
            "WORKER_IDENTITY": "prod-worker-1",
            "LOG_LEVEL": "DEBUG",
        },
    )
    def test_environment_variable_override(self):
        """Test that environment variables override defaults"""
        config = AppConfig()

        # Verify environment variables are used
        assert config.temporal_host == "prod-temporal:7233"
        assert config.temporal_namespace == "production"
        assert config.task_queue == "custom-queue"
        assert config.worker_identity == "prod-worker-1"
        assert config.log_level == "DEBUG"

    def test_case_insensitive_environment_variables(self):
        """Test that environment variables are case insensitive"""
        with patch.dict(
            os.environ,
            {
                "temporal_host": "case-test:7233",  # lowercase
                "TEMPORAL_NAMESPACE": "CASE-TEST",  # uppercase
            },
        ):
            config = AppConfig()
            assert config.temporal_host == "case-test:7233"
            assert config.temporal_namespace == "CASE-TEST"

    def test_pydantic_field_descriptions(self):
        """Test that all fields have proper descriptions for documentation"""
        # Get field info from the model class (not instance)
        field_info = AppConfig.model_fields

        # Check that key fields have descriptions
        assert "description" in str(field_info["temporal_host"])
        assert "description" in str(field_info["temporal_namespace"])
        assert "description" in str(field_info["task_queue"])
        assert "description" in str(field_info["worker_identity"])

    def test_configuration_serialization(self):
        """Test that configuration can be serialized to dict"""
        config = AppConfig(temporal_host="test:7233")

        config_dict = config.model_dump()

        # Verify key fields are present
        assert config_dict["temporal_host"] == "test:7233"
        assert "temporal_namespace" in config_dict
        assert "task_queue" in config_dict


class TestGetConfig:
    """Test get_config singleton function"""

    def setUp(self):
        """Reset the global config before each test"""
        import src.config

        src.config._config = None

    def test_get_config_singleton_behavior(self):
        """Test that get_config returns the same instance"""
        # Reset global state
        import src.config

        src.config._config = None

        # First call should create new instance
        config1 = get_config()
        assert config1 is not None
        assert isinstance(config1, AppConfig)

        # Second call should return same instance
        config2 = get_config()
        assert config2 is config1

        # Verify it's the same object
        assert id(config1) == id(config2)

    def test_get_config_preserves_state(self):
        """Test that get_config preserves configuration state"""
        import src.config

        src.config._config = None

        # Get config and verify default
        config = get_config()
        original_host = config.temporal_host

        # Modify the config (in real usage this wouldn't happen, but testing singleton)
        config.temporal_host = "modified:7233"

        # Get config again - should have modified value
        config2 = get_config()
        assert config2.temporal_host == "modified:7233"
        assert config2.temporal_host != original_host

    @patch.dict(os.environ, {"TEMPORAL_HOST": "env-test:7233"})
    def test_get_config_with_environment_variables(self):
        """Test get_config respects environment variables"""
        import src.config

        src.config._config = None

        config = get_config()
        assert config.temporal_host == "env-test:7233"

    def tearDown(self):
        """Clean up after each test"""
        import src.config

        src.config._config = None


class TestConfigurationIntegration:
    """Test configuration integration scenarios"""

    @patch.dict(
        os.environ,
        {
            "TEMPORAL_HOST": "integration-test:7233",
            "TEMPORAL_NAMESPACE": "integration",
            "TASK_QUEUE": "integration-queue",
            "WORKER_IDENTITY": "integration-worker",
        },
    )
    def test_production_like_configuration(self):
        """Test configuration suitable for production-like environments"""
        config = AppConfig()

        # Verify all production settings are configured
        assert config.temporal_host == "integration-test:7233"
        assert config.temporal_namespace == "integration"
        assert config.task_queue == "integration-queue"
        assert config.worker_identity == "integration-worker"

    def test_tls_mode_accepts_valid_values(self):
        """Test that AppConfig accepts valid TLS posture values.

        'mtls' additionally requires cert material, so it is supplied here.
        """
        cert_material = {
            "temporal_tls_cert": "/certs/client.pem",
            "temporal_tls_key": "/certs/client.key",
        }
        for mode in ("platform", "tls", "mtls"):
            config = AppConfig(
                temporal_tls_mode=mode,
                **(cert_material if mode == "mtls" else {}),
                _env_file=None,
            )
            assert config.temporal_tls_mode == mode

    @patch.dict(os.environ, {}, clear=True)
    def test_tls_mode_defaults_to_platform(self):
        """Test that temporal_tls_mode defaults to 'platform' when unset"""
        config = AppConfig(
            _env_file=None,
            temporal_auth_token_url="https://auth.test/token",
            temporal_auth_client_id="test-client",
        )
        assert config.temporal_tls_mode == "platform"

    @patch.dict(os.environ, {"TEMPORAL_TLS_MODE": "invalid"}, clear=False)
    def test_tls_mode_rejects_invalid_values(self):
        """Test that AppConfig raises ValidationError for invalid TLS mode"""
        with pytest.raises(ValueError):
            AppConfig()

    @patch.dict(os.environ, {}, clear=True)
    def test_mtls_requires_cert_and_key(self):
        """mtls without cert material must fail at startup, not connect plaintext"""
        with pytest.raises(ValueError, match="mtls requires"):
            AppConfig(temporal_tls_mode="mtls", _env_file=None)

        with pytest.raises(ValueError, match="mtls requires"):
            AppConfig(
                temporal_tls_mode="mtls",
                temporal_tls_cert="/certs/client.pem",
                _env_file=None,
            )

    @patch.dict(os.environ, {}, clear=True)
    def test_mtls_accepts_complete_cert_material(self):
        """mtls with cert and key present is valid"""
        config = AppConfig(
            temporal_tls_mode="mtls",
            temporal_tls_cert="/certs/client.pem",
            temporal_tls_key="/certs/client.key",
            temporal_tls_ca="/certs/ca.pem",
            _env_file=None,
        )
        assert config.temporal_tls_mode == "mtls"

    @patch.dict(os.environ, {}, clear=True)
    def test_tls_mode_allows_system_root_cas(self):
        """tls mode without a client cert is valid — system root CAs are used"""
        config = AppConfig(
            temporal_tls_mode="tls",
            temporal_auth_token_url="https://auth.test/token",
            temporal_auth_client_id="test-client",
            _env_file=None,
        )
        assert config.temporal_tls_mode == "tls"

    @patch.dict(os.environ, {}, clear=True)
    def test_tls_mode_rejects_cert_without_key(self):
        """A client cert with no private key is unusable and must be rejected"""
        with pytest.raises(ValueError, match="must be set together"):
            AppConfig(
                temporal_tls_mode="tls",
                temporal_tls_cert="/certs/client.pem",
                _env_file=None,
            )

    @patch.dict(os.environ, {}, clear=True)
    def test_no_engine_auth_mechanism_configured_raises(self):
        """Startup must fail when neither mTLS nor OAuth2 client-credentials is set"""
        with pytest.raises(ValueError, match="No engine client authentication"):
            AppConfig(_env_file=None)

    @patch.dict(os.environ, {}, clear=True)
    def test_no_engine_auth_mechanism_configured_raises_under_platform_tls(self):
        """The auth requirement is enforced the same way under TEMPORAL_TLS_MODE=platform"""
        with pytest.raises(ValueError, match="No engine client authentication"):
            AppConfig(temporal_tls_mode="platform", _env_file=None)

    @patch.dict(os.environ, {}, clear=True)
    def test_mtls_material_alone_satisfies_engine_auth(self):
        """mTLS client certificate material alone satisfies the auth requirement"""
        config = AppConfig(
            temporal_tls_mode="mtls",
            temporal_tls_cert="/certs/client.pem",
            temporal_tls_key="/certs/client.key",
            _env_file=None,
        )
        assert config.temporal_tls_cert == "/certs/client.pem"

    @patch.dict(os.environ, {}, clear=True)
    def test_oauth_client_credentials_alone_satisfies_engine_auth(self):
        """OAuth2 client-credentials settings alone satisfy the auth requirement"""
        config = AppConfig(
            temporal_auth_token_url="https://auth.test/token",
            temporal_auth_client_id="test-client",
            _env_file=None,
        )
        assert config.temporal_auth_token_url == "https://auth.test/token"

    @patch.dict(os.environ, {}, clear=True)
    def test_oauth_client_id_without_token_url_does_not_satisfy_engine_auth(self):
        """A client ID alone, with no token endpoint, is not a usable auth mechanism"""
        with pytest.raises(ValueError, match="No engine client authentication"):
            AppConfig(temporal_auth_client_id="test-client", _env_file=None)

    def test_configuration_for_worker_setup(self):
        """Test that configuration provides all required values for worker setup"""
        config = AppConfig()

        # Verify all required fields for foundry_temporal.WorkerConfig are available
        assert config.temporal_host is not None
        assert config.temporal_namespace is not None
        assert config.task_queue is not None
        assert config.worker_identity is not None

        # Verify types are correct
        assert isinstance(config.temporal_host, str)
        assert isinstance(config.temporal_namespace, str)
        assert isinstance(config.task_queue, str)
        assert isinstance(config.worker_identity, str)
