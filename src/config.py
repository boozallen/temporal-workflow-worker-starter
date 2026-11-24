# Copyright 2026 Booz Allen Hamilton Inc.
# SPDX-License-Identifier: Apache-2.0
"""
TEMPLATE: Configuration management for Temporal workers

This template provides essential configuration for Temporal workers with foundry-temporal.
Teams can customize this configuration class to add their specific settings.
"""

from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """
    TEMPLATE: Application configuration loaded from environment variables

    Essential configuration for Temporal workers. Teams can add their own settings below.
    """

    # TEMPLATE: Core Temporal configuration
    temporal_host: str = Field(
        default="localhost:7233", description="Temporal server host and port"
    )
    temporal_namespace: str = Field(
        default="default", description="Temporal namespace to use"
    )
    task_queue: str = Field(
        default="workflow-task-queue",
        description="Task queue name for this worker - customize this!",
    )
    temporal_tls_mode: Literal["platform", "tls", "mtls"] = Field(
        default="platform",
        description="TLS posture for Temporal connections (platform, tls, mtls)",
    )

    # TEMPLATE: Worker configuration
    worker_identity: str = Field(
        default="foundry-worker",
        description="Unique identity for this worker instance - customize this!",
    )
    max_concurrent_activities: int = Field(
        default=100, description="Maximum concurrent activities this worker can execute"
    )
    max_concurrent_workflow_tasks: int = Field(
        default=50,
        description="Maximum concurrent workflow tasks this worker can execute",
    )
    max_concurrent_local_activities: int = Field(
        default=200,
        description="Maximum concurrent local activities this worker can execute",
    )
    max_concurrent_nexus_tasks: int = Field(
        default=10, description="Maximum concurrent nexus tasks this worker can execute"
    )

    # TEMPLATE: Temporal TLS / mTLS configuration (paths to PEM files)
    temporal_tls_cert: str | None = Field(
        default=None,
        description="Path to client TLS certificate for Temporal frontend connection",
    )
    temporal_tls_key: str | None = Field(
        default=None,
        description="Path to client TLS private key for Temporal frontend connection",
    )
    temporal_tls_ca: str | None = Field(
        default=None,
        description="Path to CA certificate for verifying the Temporal frontend",
    )

    # TEMPLATE: Engine client authentication (OAuth2 client-credentials bearer
    # token). Mirrors the TEMPORAL_AUTH_* variables foundry-temporal's
    # create_temporal_client reads directly from the environment; present here
    # only so AppConfig can validate that an auth mechanism is configured.
    temporal_auth_token_url: str | None = Field(
        default=None,
        description="OAuth2 token endpoint for engine client authentication",
    )
    temporal_auth_client_id: str | None = Field(
        default=None,
        description="OAuth2 client ID for engine client authentication",
    )
    temporal_auth_client_secret: str | None = Field(
        default=None,
        description="OAuth2 client secret for engine client authentication",
    )

    # TEMPLATE: Logging configuration
    log_level: str = Field(
        default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables (like FOUNDRY_TEMPORAL_INSTALL_PATH)
    )

    @model_validator(mode="after")
    def _validate_tls_material(self) -> AppConfig:
        """Reject TLS postures whose required certificate material is missing.

        foundry-temporal raises at client-creation time for these cases; validating
        here fails the worker at startup instead, before any plaintext connection
        attempt is made (STIG V-222597, V-222598).
        """
        if self.temporal_tls_mode == "mtls" and not (
            self.temporal_tls_cert and self.temporal_tls_key
        ):
            raise ValueError(
                "TEMPORAL_TLS_MODE=mtls requires TEMPORAL_TLS_CERT and TEMPORAL_TLS_KEY"
            )
        # In 'tls' mode a client cert is optional (system root CAs are used), but a
        # cert without its private key is unusable and silently degrades the posture.
        if self.temporal_tls_mode == "tls" and bool(self.temporal_tls_cert) != bool(
            self.temporal_tls_key
        ):
            raise ValueError(
                "TEMPORAL_TLS_CERT and TEMPORAL_TLS_KEY must be set together"
            )
        return self

    @model_validator(mode="after")
    def _validate_engine_client_auth(self) -> AppConfig:
        """Require an engine client authentication mechanism, independent of TLS mode.

        TEMPORAL_TLS_MODE governs transport encryption, not client identity: under
        'platform', TLS is terminated by the mesh and the Temporal server cannot
        distinguish callers by certificate. Without this check, reachability on
        the namespace alone is sufficient to deliver signals.
        """
        has_mtls = bool(self.temporal_tls_cert and self.temporal_tls_key)
        has_oauth = bool(self.temporal_auth_token_url and self.temporal_auth_client_id)
        if not (has_mtls or has_oauth):
            raise ValueError(
                "No engine client authentication mechanism is configured. Set "
                "TEMPORAL_TLS_CERT and TEMPORAL_TLS_KEY (mutual TLS), or "
                "TEMPORAL_AUTH_TOKEN_URL and TEMPORAL_AUTH_CLIENT_ID (OAuth2 "
                "client-credentials), so that namespace access alone cannot "
                "deliver signals."
            )
        return self


# Global configuration instance
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """Get global configuration instance (singleton pattern)"""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config
