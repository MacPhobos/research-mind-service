"""Pydantic v2 schemas for link extraction and batch URL content endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


# -----------------------------------------------------------------------------
# Request Schemas
# -----------------------------------------------------------------------------


class ExtractLinksRequest(BaseModel):
    """Request body for POST /api/v1/sessions/{session_id}/content/extract-links."""

    url: HttpUrl = Field(..., description="URL to extract links from")
    include_external: bool = Field(
        default=True, description="Whether to include external links"
    )


class BatchUrlItem(BaseModel):
    """Single URL item within a batch add content request."""

    url: HttpUrl = Field(..., description="URL to add as content")
    title: str | None = Field(
        default=None, max_length=512, description="Optional title override"
    )


class BatchAddContentRequest(BaseModel):
    """Request body for POST /api/v1/sessions/{session_id}/content/batch."""

    urls: list[BatchUrlItem] = Field(
        ..., min_length=1, max_length=500, description="List of URLs to add (1-500)"
    )
    source_url: str | None = Field(
        default=None,
        max_length=2048,
        description="Source URL where links were extracted from",
    )

    @field_validator("urls")
    @classmethod
    def validate_urls_not_empty(cls, v: list[BatchUrlItem]) -> list[BatchUrlItem]:
        """Ensure at least one URL is provided."""
        if not v:
            raise ValueError("At least one URL must be provided")
        return v


# -----------------------------------------------------------------------------
# Response Schemas
# -----------------------------------------------------------------------------


class ExtractedLinkSchema(BaseModel):
    """Single extracted link from a page."""

    url: str = Field(..., description="The extracted link URL")
    text: str | None = Field(default=None, description="Link text/anchor text")
    is_external: bool = Field(..., description="Whether link points to external domain")
    source_element: str | None = Field(
        default=None, description="HTML element type (a, img, etc.)"
    )


class CategorizedLinksSchema(BaseModel):
    """Links grouped by page section/category."""

    main_content: list[ExtractedLinkSchema] = Field(
        default_factory=list, description="Links from main content area"
    )
    navigation: list[ExtractedLinkSchema] = Field(
        default_factory=list, description="Links from navigation elements"
    )
    sidebar: list[ExtractedLinkSchema] = Field(
        default_factory=list, description="Links from sidebar areas"
    )
    footer: list[ExtractedLinkSchema] = Field(
        default_factory=list, description="Links from footer area"
    )
    other: list[ExtractedLinkSchema] = Field(
        default_factory=list, description="Links from other/unclassified areas"
    )


class ExtractedLinksResponse(BaseModel):
    """Response for POST /api/v1/sessions/{session_id}/content/extract-links."""

    source_url: str = Field(..., description="URL that was analyzed")
    page_title: str | None = Field(default=None, description="Title of the page")
    extracted_at: datetime = Field(..., description="Timestamp of extraction")
    link_count: int = Field(..., ge=0, description="Total number of links extracted")
    categories: CategorizedLinksSchema = Field(
        ..., description="Links organized by page section"
    )


class BatchContentItemResponse(BaseModel):
    """Result for a single URL in batch add response."""

    content_id: str | None = Field(
        default=None, description="Content ID if successfully created"
    )
    url: str = Field(..., description="The URL that was processed")
    status: Literal["success", "error", "duplicate"] = Field(
        ..., description="Processing status"
    )
    title: str | None = Field(default=None, description="Content title")
    error: str | None = Field(default=None, description="Error message if failed")


class BatchContentResponse(BaseModel):
    """Response for POST /api/v1/sessions/{session_id}/content/batch."""

    session_id: str = Field(..., description="Session ID")
    total_count: int = Field(..., ge=0, description="Total URLs submitted")
    success_count: int = Field(..., ge=0, description="Number of successful additions")
    error_count: int = Field(..., ge=0, description="Number of failed additions")
    duplicate_count: int = Field(..., ge=0, description="Number of duplicate URLs")
    items: list[BatchContentItemResponse] = Field(
        ..., description="Per-URL results"
    )
