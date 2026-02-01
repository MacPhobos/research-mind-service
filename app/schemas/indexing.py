"""Pydantic v2 schemas for indexing endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class IndexWorkspaceRequest(BaseModel):
    """Body for POST /api/v1/workspaces/{workspace_id}/index."""

    force: bool = Field(True, description="Force re-index from scratch")
    timeout: int | None = Field(
        None,
        ge=10,
        le=600,
        description="Custom timeout in seconds (10-600)",
    )


class IndexStatusResponse(BaseModel):
    """Response for GET /api/v1/workspaces/{workspace_id}/index/status."""

    model_config = ConfigDict(from_attributes=True)

    workspace_id: str
    is_indexed: bool
    status: str
    message: str


class IndexResultResponse(BaseModel):
    """Response for POST /api/v1/workspaces/{workspace_id}/index."""

    model_config = ConfigDict(from_attributes=True)

    workspace_id: str
    success: bool
    status: str
    elapsed_seconds: float
    stdout: str | None = None
    stderr: str | None = None
