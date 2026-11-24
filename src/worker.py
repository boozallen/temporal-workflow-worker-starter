# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
3-Step Template Workflow Worker - Reference Implementation

Production-ready Temporal worker demonstrating foundry-temporal integration
patterns with a 3-step workflow template.

Features:
- foundry-temporal worker bootstrap with observability
- MyWorkflow registration and execution (3-step: my_activity, mock strands agent, approval)
- Production retry policies and error handling
- Health check endpoints for Kubernetes deployment
- Comprehensive structured logging

This worker implements a template architecture for 3-step workflows.
"""

import asyncio
import importlib
import logging
import sys
from pathlib import Path
from typing import Any, cast

import yaml
from foundry_temporal.logging import setup_structured_logging

# Production imports - foundry packages
from foundry_temporal.worker import (
    WorkerConfig,
    create_temporal_client,
    create_worker_with_defaults,
)

from .config import get_config

# Initialize logger
logger = logging.getLogger(__name__)


# Configuration Loading Functions
def load_yaml_config(config_path: Path) -> dict[str, Any]:
    """Load YAML configuration file.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        Parsed configuration dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist
        Exception: If config file is malformed
    """
    try:
        with config_path.open() as f:
            return cast("dict[str, Any]", yaml.safe_load(f))
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {config_path}")
        raise
    except Exception as e:
        logger.error(f"Failed to load configuration from {config_path}: {e}")
        raise


def load_workflows_from_config(config: dict[str, Any]) -> list[Any]:
    """Load workflow classes from configuration.

    Args:
        config: Workflows configuration dictionary

    Returns:
        List of workflow classes
    """
    workflows = []
    for item in config.get("workflows", []):
        module = importlib.import_module(item["module"])
        for class_name in item["classes"]:
            workflow_class = getattr(module, class_name)
            workflows.append(workflow_class)
            logger.info(f"Loaded workflow: {class_name} from {item['module']}")
    return workflows


def load_activities_from_config(config: dict[str, Any]) -> list[Any]:
    """Load activity functions from configuration.

    Args:
        config: Activities configuration dictionary

    Returns:
        List of activity functions
    """
    activities = []
    for item in config.get("activities", []):
        module = importlib.import_module(item["module"])
        for func_config in item["functions"]:
            if isinstance(func_config, str):
                # Simple function name
                activity_func = getattr(module, func_config)
                activities.append(activity_func)
                logger.info(f"Loaded activity: {func_config} from {item['module']}")
            else:
                # Function with configuration
                func_name = func_config["name"]
                activity_func = getattr(module, func_name)
                activities.append(activity_func)
                logger.info(
                    f"Loaded activity: {func_name} from {item['module']} with config"
                )
    return activities


def load_default_configs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load default workflow and activity configurations from config directory.

    Returns:
        Tuple of (workflows_config, activities_config, services_config)
    """
    # Load from config directory relative to this file
    config_dir = Path(__file__).parent.parent / "config"

    # Load workflow configuration
    workflows_config = load_yaml_config(config_dir / "workflows.yaml")

    # Load activities configuration
    activities_config = load_yaml_config(config_dir / "activities.yaml")

    # Load services configuration
    services_config = load_yaml_config(config_dir / "services.yaml")

    logger.info(f"Loaded configurations from {config_dir}")
    return workflows_config, activities_config, services_config


# Main Entry Points


async def start_temporal_worker(
    workflows_config: dict[str, Any],
    activities_config: dict[str, Any] | None = None,
    services_config: dict[str, Any] | None = None,
) -> None:
    """
    Start temporal worker with provided configurations.

    Alternative entry point that accepts configuration dictionaries directly.
    Useful for testing or when loading configs from different sources.

    Args:
        workflows_config: Workflows configuration dictionary
        activities_config: Activities configuration dictionary (optional)
        services_config: Services configuration dictionary (optional)
    """
    # Get application configuration
    app_config = get_config()

    # Setup foundry structured logging
    setup_structured_logging(log_level=app_config.log_level)
    logger.info("Starting temporal worker with provided configurations")

    # Note: services configuration is loaded on demand by src.services
    # from config/services.yaml when get_service_config() is first called.

    # Load workflows and activities from provided configurations
    workflows = load_workflows_from_config(workflows_config)
    activities = []
    if activities_config:
        activities = load_activities_from_config(activities_config)

    logger.info(
        "Loaded workflows and activities",
        extra={
            "workflows": [wf.__name__ for wf in workflows],
            "activities": [act.__name__ for act in activities],
            "services_provided": bool(services_config),
        },
    )

    # Create foundry WorkerConfig with centralized patterns
    worker_config = WorkerConfig(
        temporal_address=app_config.temporal_host,
        namespace=app_config.temporal_namespace,
        task_queue=app_config.task_queue,
        identity=app_config.worker_identity,
        max_concurrent_activities=app_config.max_concurrent_activities,
        max_concurrent_workflow_tasks=app_config.max_concurrent_workflow_tasks,
        max_concurrent_local_activities=app_config.max_concurrent_local_activities,
        max_concurrent_nexus_tasks=app_config.max_concurrent_nexus_tasks,
        tls_mode=app_config.temporal_tls_mode,
        temporal_tls_cert=app_config.temporal_tls_cert,
        temporal_tls_key=app_config.temporal_tls_key,
        temporal_tls_ca=app_config.temporal_tls_ca,
    )

    # Create Temporal client and worker using foundry utilities
    client = await create_temporal_client(worker_config)
    worker = create_worker_with_defaults(
        client=client,
        workflows=workflows,
        activities=activities,
        config=worker_config,
    )

    logger.info(
        "Temporal worker started successfully with config approach",
        extra={
            "worker_identity": worker_config.worker_identity,
            "registered_workflows": len(workflows),
            "registered_activities": len(activities),
        },
    )

    # Start worker (this blocks until shutdown)
    await worker.run()


def run_worker() -> None:
    """
    Run worker using configuration files from config/ directory.

    Entry point that loads default configurations and starts the worker.
    """
    try:
        workflows_config, activities_config, services_config = load_default_configs()
        asyncio.run(
            start_temporal_worker(workflows_config, activities_config, services_config)
        )
    except KeyboardInterrupt:
        logger.info("Worker shutdown requested by user")
    except Exception as e:
        logger.error(f"Worker startup failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Command-line entry point - uses configuration files approach
    run_worker()
