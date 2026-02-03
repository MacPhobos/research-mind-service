"""Pydantic v2 schemas for session endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateSessionRequest(BaseModel):
    """Body for POST /api/v1/sessions."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1024)


class UpdateSessionRequest(BaseModel):
    """Body for PATCH /api/v1/sessions/{session_id} (future use)."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1024)
    status: str | None = Field(None, max_length=50)


class SessionResponse(BaseModel):
    """Single session returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    session_id: str
    name: str
    description: str | None = None
    workspace_path: str
    created_at: datetime
    last_accessed: datetime
    status: str
    archived: bool
    ttl_seconds: int | None = None
    is_indexed: bool = False
    content_count: int = 0


class SessionListResponse(BaseModel):
    """Paginated list of sessions."""

    sessions: list[SessionResponse]
    count: int
