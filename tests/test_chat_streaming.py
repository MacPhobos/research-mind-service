"""Tests for two-stage response streaming event classification and extraction.

Tests the helper functions used to classify claude-mpm JSON events
and extract metadata from result events.
"""

from __future__ import annotations

import json

from app.schemas.chat import (
    ChatStreamChunkEvent,
    ChatStreamEventType,
    ChatStreamProgressEvent,
    ChatStreamResultMetadata,
    ChatStreamStage,
    ProgressPhase,
)
from app.services.chat_service import (
    PhaseTimer,
    _make_progress_sse,
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

    def test_progress_value(self) -> None:
        """PROGRESS should have string value 'progress'."""
        assert ChatStreamEventType.PROGRESS.value == "progress"


class TestProgressPhase:
    """Test ProgressPhase enum values."""

    def test_starting_value(self) -> None:
        """STARTING should have string value 'starting'."""
        assert ProgressPhase.STARTING.value == "starting"

    def test_initializing_value(self) -> None:
        """INITIALIZING should have string value 'initializing'."""
        assert ProgressPhase.INITIALIZING.value == "initializing"

    def test_thinking_value(self) -> None:
        """THINKING should have string value 'thinking'."""
        assert ProgressPhase.THINKING.value == "thinking"

    def test_complete_value(self) -> None:
        """COMPLETE should have string value 'complete'."""
        assert ProgressPhase.COMPLETE.value == "complete"

    def test_all_phases_present(self) -> None:
        """All 4 progress phases should be defined."""
        phases = [p.value for p in ProgressPhase]
        assert phases == ["starting", "initializing", "thinking", "complete"]


class TestChatStreamProgressEvent:
    """Test ChatStreamProgressEvent Pydantic model."""

    def test_starting_event(self) -> None:
        """Create a starting progress event."""
        event = ChatStreamProgressEvent(
            phase=ProgressPhase.STARTING,
            message="Starting Claude Code...",
            elapsed_ms=487,
        )
        assert event.phase == ProgressPhase.STARTING
        assert event.message == "Starting Claude Code..."
        assert event.elapsed_ms == 487

    def test_thinking_event_with_elapsed_time(self) -> None:
        """Create a thinking progress event with elapsed time in message."""
        event = ChatStreamProgressEvent(
            phase=ProgressPhase.THINKING,
            message="Thinking... (25s)",
            elapsed_ms=25000,
        )
        assert event.phase == ProgressPhase.THINKING
        assert event.message == "Thinking... (25s)"
        assert event.elapsed_ms == 25000

    def test_initializing_event_with_sync_percentage(self) -> None:
        """Create an initializing progress event with skill sync percentage."""
        event = ChatStreamProgressEvent(
            phase=ProgressPhase.INITIALIZING,
            message="Initializing... syncing skills (25%)",
            elapsed_ms=4506,
        )
        assert event.phase == ProgressPhase.INITIALIZING
        assert "25%" in event.message

    def test_complete_event(self) -> None:
        """Create a complete progress event."""
        event = ChatStreamProgressEvent(
            phase=ProgressPhase.COMPLETE,
            message="Generating answer...",
            elapsed_ms=30721,
        )
        assert event.phase == ProgressPhase.COMPLETE
        assert event.elapsed_ms == 30721

    def test_serialization_roundtrip(self) -> None:
        """Verify JSON serialization roundtrip preserves all fields."""
        event = ChatStreamProgressEvent(
            phase=ProgressPhase.THINKING,
            message="Thinking... (15s)",
            elapsed_ms=14729,
        )
        json_str = event.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["phase"] == "thinking"
        assert parsed["message"] == "Thinking... (15s)"
        assert parsed["elapsed_ms"] == 14729

        # Deserialize back
        restored = ChatStreamProgressEvent.model_validate(parsed)
        assert restored == event


class TestMakeProgressSse:
    """Test _make_progress_sse helper function."""

    def test_returns_sse_formatted_string(self) -> None:
        """_make_progress_sse should return a properly formatted SSE string."""
        timer = PhaseTimer("test-message-id")
        result = _make_progress_sse(
            ProgressPhase.STARTING,
            "Starting Claude Code...",
            timer,
        )
        assert result.startswith("event: chunk\ndata: ")
        assert result.endswith("\n\n")

    def test_chunk_event_structure(self) -> None:
        """SSE data should contain a valid ChatStreamChunkEvent."""
        timer = PhaseTimer("test-message-id")
        result = _make_progress_sse(
            ProgressPhase.THINKING,
            "Thinking... (10s)",
            timer,
        )
        # Extract the data portion
        data_line = result.split("data: ", 1)[1].rstrip("\n")
        chunk = json.loads(data_line)

        assert chunk["event_type"] == "progress"
        assert chunk["stage"] == 1  # EXPANDABLE
        assert chunk["raw_json"] is None

        # content should be a JSON-encoded progress event
        progress = json.loads(chunk["content"])
        assert progress["phase"] == "thinking"
        assert progress["message"] == "Thinking... (10s)"
        assert isinstance(progress["elapsed_ms"], int)
        assert progress["elapsed_ms"] >= 0

    def test_stage_is_always_expandable(self) -> None:
        """Progress events should always be Stage 1 (EXPANDABLE)."""
        timer = PhaseTimer("test-message-id")
        for phase in ProgressPhase:
            result = _make_progress_sse(phase, "test", timer)
            data_line = result.split("data: ", 1)[1].rstrip("\n")
            chunk = json.loads(data_line)
            assert chunk["stage"] == 1, f"Phase {phase.value} should be stage 1"

    def test_elapsed_ms_increases(self) -> None:
        """elapsed_ms should reflect time since timer start."""
        import time

        timer = PhaseTimer("test-message-id")
        # Small sleep to ensure elapsed_ms > 0
        time.sleep(0.01)
        result = _make_progress_sse(
            ProgressPhase.STARTING,
            "Starting...",
            timer,
        )
        data_line = result.split("data: ", 1)[1].rstrip("\n")
        chunk = json.loads(data_line)
        progress = json.loads(chunk["content"])
        assert progress["elapsed_ms"] >= 10  # At least 10ms after sleep

    def test_all_phases_produce_valid_output(self) -> None:
        """All progress phases should produce valid SSE output."""
        timer = PhaseTimer("test-message-id")
        messages = {
            ProgressPhase.STARTING: "Starting Claude Code...",
            ProgressPhase.INITIALIZING: "Initializing environment...",
            ProgressPhase.THINKING: "Thinking... (15s)",
            ProgressPhase.COMPLETE: "Generating answer...",
        }
        for phase, message in messages.items():
            result = _make_progress_sse(phase, message, timer)
            # Verify it can be parsed as a valid chunk event
            data_line = result.split("data: ", 1)[1].rstrip("\n")
            chunk_data = json.loads(data_line)
            chunk_event = ChatStreamChunkEvent.model_validate(chunk_data)
            assert chunk_event.event_type == ChatStreamEventType.PROGRESS
            assert chunk_event.stage == ChatStreamStage.EXPANDABLE

            # Verify the inner progress event
            progress = ChatStreamProgressEvent.model_validate_json(chunk_event.content)
            assert progress.phase == phase
            assert progress.message == message
