# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
Data models for workflows and activities

Pydantic models used by the MyWorkflow template.
Teams should customize these models for their specific business logic.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints


class MyWorkflowInput(BaseModel):
    """Input model for template workflow - customize for your needs."""

    user_name: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    task_type: Annotated[str, StringConstraints(min_length=1, max_length=64)] = (
        "greeting"
    )
    # Range 1-10 is a placeholder; adjust per the number of priority levels needed.
    priority: int = Field(default=1, ge=1, le=10)
    language: Annotated[str, StringConstraints(min_length=2, max_length=16)] = "en"
    # Key-count cap of 50 is a placeholder; adjust per expected metadata size.
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=50)


class MyWorkflowResult(BaseModel):
    """Result model for template workflow - customize for your needs."""

    success: bool
    message: str
    outcome: Literal["approved", "denied", "timed_out"] = "approved"
    processing_time: float | None = None
    source: str = "mock-strands-agent"
    data: dict[str, Any] = {}
