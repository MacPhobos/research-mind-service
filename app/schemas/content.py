"""Pydantic v2 schemas for content management endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AddContentRequest(BaseModel):
    """Body for POST /api/v1/sessions/{session_id}/content."""

    content_type: str = Field(
        ...,
        description="Content type: text, file_upload, url, git_repo, mcp_source",
    )
    title: str | None = Field(None, max_length=512, description="Content title")
    source: str | None = Field(
        None, max_length=2048, description="Source reference (URL, text, etc.)"
    )
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


class ContentItemResponse(BaseModel):
    """Single content item returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    content_id: str
    session_id: str
    content_type: str
    title: str
    source_ref: str | None = None
    storage_path: str | None = None
    status: str
    error_message: str | None = None
    size_bytes: int | None = None
    mime_type: str | None = None
    metadata_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ContentListResponse(BaseModel):
    """Paginated list of content items."""

    items: list[ContentItemResponse]
    count: int
