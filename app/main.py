"""FastAPI application entry point for research-mind-service.

Configures middleware, exception handlers, lifecycle hooks, and routes.
"""

from __future__ import annotations

import logging
import subprocess
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.db.session import create_all_tables
from app.routes import health, api
from app.routes.indexing import router as indexing_router
from app.routes.sessions import router as sessions_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def _verify_mcp_cli() -> str | None:
    """Check that mcp-vector-search CLI is available on PATH.

    Returns the version string on success, or None if the tool is missing.
    """
    try:
        result = subprocess.run(
            ["mcp-vector-search", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = result.stdout.strip() or result.stderr.strip()
        return version if result.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
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

    cli_version = _verify_mcp_cli()
    if cli_version:
        logger.info("mcp-vector-search CLI detected: %s", cli_version)
    else:
        logger.warning(
            "mcp-vector-search CLI not found on PATH. "
            "Indexing features will be unavailable."
        )

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
