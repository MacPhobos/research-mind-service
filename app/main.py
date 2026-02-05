"""FastAPI application entry point for research-mind-service.

Configures middleware, exception handlers, lifecycle hooks, and routes.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db.session import create_all_tables
from app.middleware.session_validation import SessionValidationMiddleware
from app.routes import health, api
from app.routes.audit import router as audit_router
from app.routes.chat import router as chat_router
from app.routes.content import router as content_router
from app.routes.indexing import router as indexing_router
from app.routes.links import router as links_router
from app.routes.sessions import router as sessions_router

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------

# Configure root logger with level from settings
logging.basicConfig(
    level=settings.get_log_level_int(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def _verify_mcp_cli() -> str | None:
    """Check that mcp-vector-search CLI is available on PATH.

    Returns the path to the executable on success, or None if the tool is missing.
    """
    path = shutil.which("mcp-vector-search")
    if path:
        logger.debug("mcp-vector-search found at: %s", path)
        return path
    return None

def _verify_claude_mpm_cli() -> str | None:
    """Check that claude-mpm CLI is available on PATH.

    Returns the path to the executable on success, or None if the tool is missing.
    """
    path = shutil.which("claude-mpm")
    if path:
        logger.debug("claude-mpm found at: %s", path)
        return path
    return None

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup / shutdown lifecycle."""
    # --- Startup ---
    logger.info(
        "Starting research-mind-service (env=%s, port=%d)",
        settings.service_env,
        settings.port,
    )

    # Ensure tables exist (dev convenience - production uses alembic)
    if settings.service_env == "development":
        try:
            # Import models so Base.metadata knows about them
            import app.models  # noqa: F401

            create_all_tables()
            logger.info("Database tables ensured (dev mode)")
        except Exception:
            logger.warning(
                "Could not auto-create tables (database may not be available). "
                "Use 'alembic upgrade head' to create tables."
            )

    mcp_vector_search_cli_presence = _verify_mcp_cli()
    if mcp_vector_search_cli_presence:
        logger.info("mcp-vector-search CLI detected at: %s", mcp_vector_search_cli_presence)
    else:
        logger.warning(
            "mcp-vector-search CLI not found on PATH. "
            "Indexing features will be unavailable. "
            "PATH: %s", os.environ.get("PATH", "")
        )

    claude_mpm_cli_presence = _verify_claude_mpm_cli()
    if claude_mpm_cli_presence:
        logger.info("claude_mpm CLI detected at: %s", claude_mpm_cli_presence)
    else:
        logger.warning(
            "claude_mpm CLI not found on PATH. "
            "Indexing features will be unavailable. "
            "PATH: %s", os.environ.get("PATH", "")
        )

    # Ensure content sandbox root directory exists
    content_sandbox = settings.content_sandbox_root
    os.makedirs(content_sandbox, exist_ok=True)
    logger.info("Content sandbox root ensured at %s", os.path.abspath(content_sandbox))

    yield

    # --- Shutdown ---
    logger.info("Shutting down research-mind-service")


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="research-mind API",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SessionValidationMiddleware)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log every request with method, path, status, and duration."""
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    logger.info(
        "%s %s -> %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler that returns a structured JSON error."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred.",
            }
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# Existing health check at /health (no prefix)
app.include_router(health.router)

# API v1 routes
app.include_router(api.router, prefix="/api/v1")

# Session management routes (already prefixed with /api/v1/sessions)
app.include_router(sessions_router)

# Indexing routes (prefixed with /api/v1/workspaces)
app.include_router(indexing_router)

# Content management routes (prefixed with /api/v1/sessions/{session_id}/content)
app.include_router(content_router)

# Link extraction routes (prefixed with /api/v1/content)
app.include_router(links_router)

# Audit log routes (prefixed with /api/v1/sessions)
app.include_router(audit_router)

# Chat routes (prefixed with /api/v1/sessions)
app.include_router(chat_router)


# Additional health endpoint under API prefix for consistency
@app.get("/api/v1/health", tags=["health"])
async def api_health_check():
    """Health check under the /api/v1 prefix."""
    return {
        "status": "ok",
        "name": "research-mind-service",
        "version": "0.1.0",
        "environment": settings.service_env,
    }
