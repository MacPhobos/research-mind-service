"""Pydantic v2 schemas for chat endpoints."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Two-Stage Streaming Enums
# ---------------------------------------------------------------------------


class ChatStreamEventType(str, Enum):
    """SSE event types for two-stage streaming.

    Stage 1 (Expandable): Process output shown in collapsible accordion
    - INIT_TEXT: Plain text initialization (claude-mpm banner, agent sync, etc.)
    - SYSTEM_INIT: JSON system initialization event (cwd, tools, model, etc.)
    - SYSTEM_HOOK: JSON hook start/complete events
    - STREAM_TOKEN: Token-by-token streaming delta (if available)

    Stage 2 (Primary): Final answer shown prominently
    - ASSISTANT: Complete assistant message
    - RESULT: Final result with full metadata

    Lifecycle:
    - START: Session started, message_id returned
    - ERROR: Error occurred during processing
    - HEARTBEAT: Keep-alive ping
    """

    START = "start"
    INIT_TEXT = "init_text"  # Plain text initialization (Stage 1)
    SYSTEM_INIT = "system_init"  # JSON system init event (Stage 1)
    SYSTEM_HOOK = "system_hook"  # JSON hook events (Stage 1)
    STREAM_TOKEN = "stream_token"  # Token-by-token if available (Stage 1)
    ASSISTANT = "assistant"  # Complete assistant message (Stage 2)
    RESULT = "result"  # Final result with metadata (Stage 2)
    ERROR = "error"
    HEARTBEAT = "heartbeat"


class ChatStreamStage(int, Enum):
    """Stage classification for SSE events.

    EXPANDABLE (1): Full process output (plain text + system JSON)
        - Streamed to UI in real-time
        - Shown in collapsible accordion
        - NOT persisted to database

    PRIMARY (2): Final answer (assistant + result)
        - Shown prominently in chat
        - Persisted to database
    """

    EXPANDABLE = 1  # Stage 1: Process output (not persisted)
    PRIMARY = 2  # Stage 2: Final answer (persisted)


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
# SSE Event Schemas (Two-Stage Streaming)
# ---------------------------------------------------------------------------


class ChatStreamResultMetadata(BaseModel):
    """Metadata extracted from claude-mpm result event.

    Contains token usage, timing, and cost information from the Claude API.
    """

    token_count: int | None = None  # output_tokens from usage
    input_tokens: int | None = None  # input_tokens from usage
    cache_read_tokens: int | None = None  # cache_read_input_tokens
    duration_ms: int | None = None  # Total duration from result event
    duration_api_ms: int | None = None  # API call duration
    cost_usd: float | None = None  # total_cost_usd from result event
    session_id: str | None = None  # Claude session ID for correlation
    num_turns: int | None = None  # Number of conversation turns


class ChatStreamStartEvent(BaseModel):
    """Event sent when streaming starts."""

    message_id: str
    status: Literal["streaming"] = "streaming"


class ChatStreamChunkEvent(BaseModel):
    """Two-stage streaming event with stage classification.

    Replaces the old simple chunk event format. Each chunk is now classified
    into a stage (EXPANDABLE or PRIMARY) for proper UI routing.
    """

    content: str
    event_type: ChatStreamEventType
    stage: ChatStreamStage
    raw_json: dict[str, Any] | None = None  # Original JSON event for debugging


class ChatStreamCompleteEvent(BaseModel):
    """Event sent when streaming completes successfully.

    Only stage2_content (the final answer) is persisted to the database.
    Stage 1 content is ephemeral and only shown in the expandable accordion.
    """

    message_id: str
    status: Literal["completed"] = "completed"
    content: str  # Final answer (stage2_content) - this is what gets persisted
    metadata: ChatStreamResultMetadata | None = None
    # Legacy fields for backwards compatibility during transition
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


# ---------------------------------------------------------------------------
# Chat Export Schemas
# ---------------------------------------------------------------------------


class ChatExportFormat(str, Enum):
    """Supported export formats for chat history."""

    PDF = "pdf"
    MARKDOWN = "markdown"


class ChatExportRequest(BaseModel):
    """Request body for chat export endpoints."""

    format: ChatExportFormat
    include_metadata: bool = True
    include_timestamps: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "format": "pdf",
                    "include_metadata": True,
                    "include_timestamps": True,
                }
            ]
        }
    )
