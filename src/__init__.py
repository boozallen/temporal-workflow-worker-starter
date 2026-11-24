# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
TEMPLATE: Worker package

Main worker functionality for Temporal workflows with foundry-temporal integration.
"""

from .config import get_config
from .models import MyWorkflowInput, MyWorkflowResult

# Conditionally import worker functions only if foundry_temporal is available
try:
    from .worker import (  # noqa: F401
        run_worker,
    )

    _worker_available = True
except ImportError:
    _worker_available = False

__all__ = [
    "get_config",
    "MyWorkflowInput",
    "MyWorkflowResult",
]

if _worker_available:
    __all__.extend(
        [
            "run_worker",
        ]
    )
