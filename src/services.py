# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Services configuration management for temporal workflow workers.

Loads service configuration on demand from config/services.yaml.
This avoids issues with Temporal's workflow sandbox, which re-imports
modules in isolation and would lose any global state set externally.
"""

import os
from pathlib import Path
from typing import Any

import yaml

# Cached config — lazy-loaded on first access
_services_config: dict[str, Any] | None = None


def _load_services_config() -> dict[str, Any]:
    """Load services configuration from config/services.yaml.

    Each service's `url` can be overridden by a `<SERVICE_NAME>_URL`
    environment variable (service name upper-cased), so a host-run worker can
    reach a service published on localhost instead of the compose-network
    hostname baked into the YAML default.
    """
    config_path = Path(__file__).parent.parent / "config" / "services.yaml"
    with config_path.open() as f:
        config: dict[str, Any] = yaml.safe_load(f)
    for service_name, service_config in config.items():
        override = os.environ.get(f"{service_name.upper()}_URL")
        if override:
            service_config["url"] = override
    return config


def get_services_config() -> dict[str, Any]:
    """Get services configuration, loading from YAML on first access."""
    global _services_config
    if _services_config is None:
        _services_config = _load_services_config()
    return _services_config


def set_services_config(services: dict[str, Any]) -> None:
    """Override services configuration (useful for testing)."""
    global _services_config
    _services_config = services


def get_service_config(service_name: str) -> dict[str, Any]:
    """
    Get configuration for a specific service.

    Args:
        service_name: Name of the service to get configuration for

    Returns:
        Service configuration dictionary

    Raises:
        KeyError: If service not found
    """
    services = get_services_config()
    if service_name not in services:
        raise KeyError(
            f"Service '{service_name}' not found in configuration. "
            f"Available services: {list(services.keys())}"
        )
    service_config: dict[str, Any] = services[service_name]
    return service_config
