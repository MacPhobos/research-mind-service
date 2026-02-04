"""Pydantic v2 schemas for chat endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SendChatMessageRequest(BaseModel):
    """Body for POST /api/v1/sessions/{session_id}/chat."""

    content: str = Field(..., min_length=1, max_length=10000)


class ChatMessageResponse(BaseModel):
    """Single chat message returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    message_id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    status: Literal["pending", "streaming", "completed", "error"]
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    token_count: int | None = None
    duration_ms: int | None = None
    metadata_json: dict[str, Any] | None = None


class ChatMessageWithStreamUrlResponse(ChatMessageResponse):
    """Chat message response with stream URL for SSE connection."""

    stream_url: str | None = None


class ChatMessageListResponse(BaseModel):
    """Paginated list of chat messages."""

    messages: list[ChatMessageResponse]
    count: int


# ---------------------------------------------------------------------------
# SSE Event Schemas
# ---------------------------------------------------------------------------


class ChatStreamStartEvent(BaseModel):
    """Event sent when streaming starts."""

    message_id: str
    status: Literal["streaming"] = "streaming"


class ChatStreamChunkEvent(BaseModel):
    """Event sent for each content chunk."""

    content: str


class ChatStreamCompleteEvent(BaseModel):
    """Event sent when streaming completes successfully."""

    message_id: str
    status: Literal["completed"] = "completed"
    content: str
    token_count: int | None = None
    duration_ms: int | None = None


class ChatStreamErrorEvent(BaseModel):
    """Event sent when an error occurs during streaming."""

    message_id: str
    status: Literal["error"] = "error"
    error: str


class ChatStreamHeartbeatEvent(BaseModel):
    """Event sent periodically to keep connection alive."""

    timestamp: str
