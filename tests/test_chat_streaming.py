"""Tests for two-stage response streaming event classification and extraction.

Tests the helper functions used to classify claude-mpm JSON events
and extract metadata from result events.
"""

from __future__ import annotations

import pytest

from app.schemas.chat import (
    ChatStreamEventType,
    ChatStreamResultMetadata,
    ChatStreamStage,
)
from app.services.chat_service import (
    classify_event,
    extract_assistant_content,
    extract_metadata,
)


class TestClassifyEvent:
    """Test event classification into stages."""

    def test_system_init_event(self) -> None:
        """System init events should be classified as Stage 1 EXPANDABLE."""
        event = {
            "type": "system",
            "subtype": "init",
            "cwd": "/path/to/workspace",
            "tools": ["bash", "read"],
            "model": "claude-opus-4-5-20251101",
        }
        event_type, stage = classify_event(event)

        assert event_type == ChatStreamEventType.SYSTEM_INIT
        assert stage == ChatStreamStage.EXPANDABLE

    def test_hook_started_event(self) -> None:
        """Hook started events should be classified as Stage 1 EXPANDABLE."""
        event = {
            "type": "system",
            "subtype": "hook_started",
            "hook_id": "abc123",
            "hook_name": "SessionStart:startup",
        }
        event_type, stage = classify_event(event)

        assert event_type == ChatStreamEventType.SYSTEM_HOOK
        assert stage == ChatStreamStage.EXPANDABLE

    def test_hook_response_event(self) -> None:
        """Hook response events should be classified as Stage 1 EXPANDABLE."""
        event = {
            "type": "system",
            "subtype": "hook_response",
            "hook_id": "abc123",
            "outcome": "success",
        }
        event_type, stage = classify_event(event)

        assert event_type == ChatStreamEventType.SYSTEM_HOOK
        assert stage == ChatStreamStage.EXPANDABLE

    def test_stream_event(self) -> None:
        """Stream events (token-by-token) should be Stage 1 EXPANDABLE."""
        event = {
            "type": "stream_event",
            "content_block": {"type": "text", "text": "partial "},
        }
        event_type, stage = classify_event(event)

        assert event_type == ChatStreamEventType.STREAM_TOKEN
        assert stage == ChatStreamStage.EXPANDABLE

    def test_assistant_event(self) -> None:
        """Assistant events should be classified as Stage 2 PRIMARY."""
        event = {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "The answer is 4."}],
                "id": "msg_123",
            },
        }
        event_type, stage = classify_event(event)

        assert event_type == ChatStreamEventType.ASSISTANT
        assert stage == ChatStreamStage.PRIMARY

    def test_result_event(self) -> None:
        """Result events should be classified as Stage 2 PRIMARY."""
        event = {
            "type": "result",
            "subtype": "success",
            "result": "The answer is 4.",
            "duration_ms": 3064,
            "total_cost_usd": 0.17021,
        }
        event_type, stage = classify_event(event)

        assert event_type == ChatStreamEventType.RESULT
        assert stage == ChatStreamStage.PRIMARY

    def test_unknown_event_defaults_to_expandable(self) -> None:
        """Unknown event types should default to Stage 1 EXPANDABLE."""
        event = {
            "type": "unknown_type",
            "data": "some data",
        }
        event_type, stage = classify_event(event)

        assert event_type == ChatStreamEventType.STREAM_TOKEN
        assert stage == ChatStreamStage.EXPANDABLE

    def test_empty_event(self) -> None:
        """Empty events should default to Stage 1 EXPANDABLE."""
        event: dict = {}
        event_type, stage = classify_event(event)

        assert event_type == ChatStreamEventType.STREAM_TOKEN
        assert stage == ChatStreamStage.EXPANDABLE

    def test_system_without_subtype(self) -> None:
        """System events without subtype should be SYSTEM_INIT."""
        event = {
            "type": "system",
            "model": "claude-opus-4-5-20251101",
        }
        event_type, stage = classify_event(event)

        assert event_type == ChatStreamEventType.SYSTEM_INIT
        assert stage == ChatStreamStage.EXPANDABLE


class TestExtractMetadata:
    """Test metadata extraction from result events."""

    def test_full_metadata_extraction(self) -> None:
        """Extract all fields from a complete result event."""
        result_event = {
            "type": "result",
            "subtype": "success",
            "result": "The answer is 4.",
            "duration_ms": 3064,
            "duration_api_ms": 2800,
            "total_cost_usd": 0.17021,
            "session_id": "sess_abc123",
            "num_turns": 1,
            "usage": {
                "output_tokens": 15,
                "input_tokens": 1200,
                "cache_read_input_tokens": 500,
            },
        }
        metadata = extract_metadata(result_event)

        assert isinstance(metadata, ChatStreamResultMetadata)
        assert metadata.duration_ms == 3064
        assert metadata.duration_api_ms == 2800
        assert metadata.cost_usd == 0.17021
        assert metadata.session_id == "sess_abc123"
        assert metadata.num_turns == 1
        assert metadata.token_count == 15
        assert metadata.input_tokens == 1200
        assert metadata.cache_read_tokens == 500

    def test_partial_metadata_extraction(self) -> None:
        """Extract available fields when some are missing."""
        result_event = {
            "type": "result",
            "duration_ms": 5000,
            "usage": {
                "output_tokens": 100,
            },
        }
        metadata = extract_metadata(result_event)

        assert metadata.duration_ms == 5000
        assert metadata.token_count == 100
        assert metadata.input_tokens is None
        assert metadata.cost_usd is None
        assert metadata.session_id is None

    def test_empty_result_event(self) -> None:
        """Handle empty result event gracefully."""
        result_event: dict = {}
        metadata = extract_metadata(result_event)

        assert metadata.duration_ms is None
        assert metadata.token_count is None
        assert metadata.cost_usd is None

    def test_missing_usage_block(self) -> None:
        """Handle result event without usage block."""
        result_event = {
            "type": "result",
            "duration_ms": 1000,
            "total_cost_usd": 0.05,
        }
        metadata = extract_metadata(result_event)

        assert metadata.duration_ms == 1000
        assert metadata.cost_usd == 0.05
        assert metadata.token_count is None
        assert metadata.input_tokens is None


class TestExtractAssistantContent:
    """Test content extraction from assistant events."""

    def test_single_text_block(self) -> None:
        """Extract text from single text block."""
        assistant_event = {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "The answer is 4."}],
            },
        }
        content = extract_assistant_content(assistant_event)

        assert content == "The answer is 4."

    def test_multiple_text_blocks(self) -> None:
        """Concatenate multiple text blocks."""
        assistant_event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "First part. "},
                    {"type": "text", "text": "Second part."},
                ],
            },
        }
        content = extract_assistant_content(assistant_event)

        assert content == "First part. Second part."

    def test_mixed_content_blocks(self) -> None:
        """Only extract text blocks, ignore others."""
        assistant_event = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Text content"},
                    {"type": "tool_use", "name": "bash", "input": "ls"},
                    {"type": "text", "text": " more text"},
                ],
            },
        }
        content = extract_assistant_content(assistant_event)

        assert content == "Text content more text"

    def test_empty_content_blocks(self) -> None:
        """Handle empty content array."""
        assistant_event = {
            "type": "assistant",
            "message": {
                "content": [],
            },
        }
        content = extract_assistant_content(assistant_event)

        assert content == ""

    def test_no_message_field(self) -> None:
        """Handle missing message field."""
        assistant_event = {"type": "assistant"}
        content = extract_assistant_content(assistant_event)

        assert content == ""

    def test_no_content_field(self) -> None:
        """Handle missing content field."""
        assistant_event = {
            "type": "assistant",
            "message": {},
        }
        content = extract_assistant_content(assistant_event)

        assert content == ""

    def test_text_block_without_text(self) -> None:
        """Handle text block with missing text field."""
        assistant_event = {
            "type": "assistant",
            "message": {
                "content": [{"type": "text"}],  # Missing "text" field
            },
        }
        content = extract_assistant_content(assistant_event)

        assert content == ""


class TestStageClassification:
    """Test stage classification values."""

    def test_expandable_stage_value(self) -> None:
        """Stage 1 EXPANDABLE should have value 1."""
        assert ChatStreamStage.EXPANDABLE == 1

    def test_primary_stage_value(self) -> None:
        """Stage 2 PRIMARY should have value 2."""
        assert ChatStreamStage.PRIMARY == 2


class TestEventTypeValues:
    """Test event type enum values."""

    def test_init_text_value(self) -> None:
        """INIT_TEXT should have string value 'init_text'."""
        assert ChatStreamEventType.INIT_TEXT.value == "init_text"

    def test_system_init_value(self) -> None:
        """SYSTEM_INIT should have string value 'system_init'."""
        assert ChatStreamEventType.SYSTEM_INIT.value == "system_init"

    def test_system_hook_value(self) -> None:
        """SYSTEM_HOOK should have string value 'system_hook'."""
        assert ChatStreamEventType.SYSTEM_HOOK.value == "system_hook"

    def test_stream_token_value(self) -> None:
        """STREAM_TOKEN should have string value 'stream_token'."""
        assert ChatStreamEventType.STREAM_TOKEN.value == "stream_token"

    def test_assistant_value(self) -> None:
        """ASSISTANT should have string value 'assistant'."""
        assert ChatStreamEventType.ASSISTANT.value == "assistant"

    def test_result_value(self) -> None:
        """RESULT should have string value 'result'."""
        assert ChatStreamEventType.RESULT.value == "result"
