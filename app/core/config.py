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
    # Use postgresql+psycopg:// dialect (psycopg v3 driver)
    database_url: str = (
        "postgresql+psycopg://postgres:password@localhost:5432/research_mind"
    )

    # --- Content Sandbox ---
    # Root directory for all session data (content and indexes)
    # Each session gets: {content_sandbox_root}/{session_id}/
    #   - Content subdirs: {content_id_1}/, {content_id_2}/, etc.
    #   - Index data: .mcp-vector-search/
    # Development: ./content_sandboxes (relative to service root)
    # Production: /var/lib/research-mind/content_sandboxes
    content_sandbox_root: str = "./content_sandboxes"

    # --- Content Retrieval Limits ---
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB max file upload
    max_text_bytes: int = 10 * 1024 * 1024  # 10 MB max text content
    max_url_response_bytes: int = 20 * 1024 * 1024  # 20 MB max URL response
    max_workspace_bytes: int = 500 * 1024 * 1024  # 500 MB per session workspace
    url_fetch_timeout: int = 30  # seconds

    # --- URL Content Extraction ---
    url_extraction_retry_with_js: bool = True  # Retry with Playwright if static extraction fails
    url_extraction_min_content_length: int = 100  # Minimum chars for valid extraction
    git_clone_timeout: int = 120  # seconds
    git_clone_depth: int = 1  # shallow clone depth
    allowed_upload_extensions: str = ".pdf,.docx,.txt,.md,.csv,.html,.json,.xml"

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
