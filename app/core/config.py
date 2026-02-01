"""Application configuration using Pydantic Settings.

Loads settings from environment variables and .env file.
All settings have sensible defaults for local development.
"""

from __future__ import annotations

import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service-wide configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Server ---
    service_env: str = "development"
    host: str = "0.0.0.0"
    port: int = 15010
    debug: bool = False

    # --- Database ---
    database_url: str = (
        "postgresql://postgres:password@localhost:5432/research_mind"
    )

    # --- Workspace ---
    workspace_root: str = "/var/lib/research-mind/workspaces"

    # --- Subprocess Timeouts (seconds) ---
    subprocess_timeout_init: int = 30
    subprocess_timeout_index: int = 60
    subprocess_timeout_large: int = 600

    # --- Session Limits ---
    session_max_duration_minutes: int = 60
    session_idle_timeout_minutes: int = 30

    # --- CORS ---
    cors_origins: str = "http://localhost:15000,http://localhost:3000"

    def get_cors_origins(self) -> list[str]:
        """Parse cors_origins as JSON list or comma-separated string."""
        raw = self.cors_origins.strip()
        if raw.startswith("["):
            return json.loads(raw)
        return [o.strip() for o in raw.split(",") if o.strip()]

    # --- Feature Flags ---
    enable_agent_integration: bool = False
    enable_caching: bool = False
    enable_warm_pools: bool = False

    # --- Security ---
    path_validator_enabled: bool = True
    audit_logging_enabled: bool = True

    # --- Auth (existing, carried forward) ---
    secret_key: str = "dev-secret-change-in-production"
    algorithm: str = "HS256"


settings = Settings()
