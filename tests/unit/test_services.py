# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for services configuration management.
"""

import pytest

from src.services import get_service_config, get_services_config, set_services_config


class TestServicesConfig:
    """Test services configuration get/set functions."""

    def setup_method(self):
        """Reset cached config before each test."""
        import src.services

        src.services._services_config = None

    def test_get_services_config_lazy_loads_from_yaml(self):
        """Test get_services_config lazy-loads from config/services.yaml."""
        config = get_services_config()
        assert isinstance(config, dict)
        # The real services.yaml has mock_strands_agent
        assert "mock_strands_agent" in config
        assert "url" in config["mock_strands_agent"]

    def test_set_overrides_lazy_load(self):
        """Test set_services_config overrides lazy-loaded config."""
        custom = {"my_service": {"url": "http://localhost:8080"}}
        set_services_config(custom)
        assert get_services_config() == custom

    def test_get_service_config_success(self):
        """Test get_service_config returns specific service from YAML."""
        result = get_service_config("mock_strands_agent")
        assert "url" in result
        assert result["url"] == "http://mock-strands-agent:8080"

    def test_get_service_config_with_override(self):
        """Test get_service_config works with overridden config."""
        set_services_config(
            {"agent": {"url": "http://agent:9000", "description": "Agent service"}}
        )
        result = get_service_config("agent")
        assert result == {"url": "http://agent:9000", "description": "Agent service"}

    def test_get_service_config_not_found(self):
        """Test get_service_config raises KeyError for missing service."""
        with pytest.raises(KeyError, match="Service 'missing' not found"):
            get_service_config("missing")

    def test_config_is_cached_after_first_load(self):
        """Test that config is cached and not re-read on every call."""

        first = get_services_config()
        second = get_services_config()
        # Same object — loaded once, cached
        assert first is second

    def test_env_var_overrides_yaml_url(self, monkeypatch: pytest.MonkeyPatch):
        """Test MOCK_STRANDS_AGENT_URL overrides the YAML default url."""
        monkeypatch.setenv("MOCK_STRANDS_AGENT_URL", "http://localhost:8081")
        result = get_service_config("mock_strands_agent")
        assert result["url"] == "http://localhost:8081"

    def test_no_env_var_keeps_yaml_url(self, monkeypatch: pytest.MonkeyPatch):
        """Test the YAML default url is unchanged when no override is set."""
        monkeypatch.delenv("MOCK_STRANDS_AGENT_URL", raising=False)
        result = get_service_config("mock_strands_agent")
        assert result["url"] == "http://mock-strands-agent:8080"
