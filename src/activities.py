# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
TEMPLATE: Activities demonstrating foundry package patterns

This module provides template activities for teams to customize.
Teams should replace my_activity with their specific business operations.

Key patterns demonstrated:
- Standard Temporal activities with proper error handling
- Using call_strands_agent from foundry-temporal-agents package
- Retryable vs non-retryable error classification via foundry-temporal
- Heartbeats for long-running activities
- Structured logging and observability
"""

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from foundry_temporal import (
    ValidationError,
    classify_and_wrap_error,
)
from pydantic import BaseModel
from temporalio import activity

from .services import get_service_config

# Note: call_strands_agent is available from foundry-temporal-agents package
# Import it like this in your workflows:
# from temporalio.workflow import execute_activity
# result = await execute_activity("call_strands_agent", args=[agent_url, task, query_extra_data])


# Data Models for Activities - Teams should define their own models
class MyActivityResult(BaseModel):
    """Result model for my_activity."""

    success: bool
    message: str
    data: dict[str, Any] = {}
    processing_time: float
    timestamp: str


@activity.defn
async def get_service_config_activity(service_name: str) -> dict[str, Any]:
    """Load service config in an activity to keep workflows deterministic."""
    return get_service_config(service_name)


@activity.defn
async def my_activity(data: dict[str, Any]) -> dict[str, Any]:
    """
    TEMPLATE: Example activity demonstrating basic patterns.

    Teams should customize this activity for their business logic:
    1. Update input/output types
    2. Replace processing logic with your domain logic
    3. Add domain-specific error handling
    4. Configure retry policies as needed in activities.yaml

    Error handling uses foundry-temporal error classification:
    - ValidationError → non-retryable (bad input, will never succeed)
    - ConnectionError, TimeoutError, 5xx → retryable (transient)
    - Unknown errors → classified automatically via classify_and_wrap_error
    """
    logger = activity.logger
    start_time = time.time()

    logger.info(
        "Starting my_activity template",
        extra={
            "activity_id": activity.info().activity_id,
            "input_data": data,
        },
    )

    # --- Input validation (non-retryable) ---
    name = data.get("name")
    task_type = data.get("type", "default")

    if not name:
        raise ValidationError("'name' is required in activity input data")

    # --- Business logic ---
    try:
        # Simulate some processing work
        logger.info(f"Processing {task_type} task for {name}")

        # For long-running activities, send heartbeats
        if task_type == "long_running":
            for i in range(3):
                await asyncio.sleep(2)
                activity.heartbeat(f"Processing step {i + 1}/3")
        else:
            # Short processing
            await asyncio.sleep(1)

        processing_time = time.time() - start_time

        result = MyActivityResult(
            success=True,
            message=f"Template: Successfully processed {task_type} for {name}",
            data={
                "name": name,
                "type": task_type,
                "steps_completed": 3 if task_type == "long_running" else 1,
                "template_note": "Replace this with your business logic",
            },
            processing_time=processing_time,
            timestamp=datetime.now(UTC).isoformat(),
        )

        logger.info(
            "Activity completed successfully",
            extra={
                "processing_time": processing_time,
                "result": result.model_dump(),
            },
        )

        return result.model_dump()

    except Exception as e:
        logger.error(f"Activity failed: {e}", exc_info=True)
        # Classify the error and re-raise so Temporal handles retry decisions
        raise classify_and_wrap_error(e, context="my_activity") from e
