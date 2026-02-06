"""Business logic for chat message CRUD operations.

Includes claude-mpm subprocess integration for AI-powered chat responses.
CRITICAL: Uses claude-mpm executable exclusively. Never the native claude CLI.

Two-Stage Response Streaming:
- Stage 1 (Expandable): Plain text initialization + system JSON events (NOT persisted)
- Stage 2 (Primary): Final answer from assistant/result events (persisted to DB)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.exceptions import (
    ClaudeApiKeyNotSetError,
    ClaudeMpmFailedError,
    ClaudeMpmNotAvailableError,
    ClaudeMpmTimeoutError,
    SessionWorkspaceNotFoundError,
)
from app.models.chat_message import ChatMessage, ChatRole, ChatStatus
from app.models.session import Session
from app.schemas.chat import (
    ChatMessageResponse,
    ChatMessageWithStreamUrlResponse,
    ChatStreamChunkEvent,
    ChatStreamCompleteEvent,
    ChatStreamErrorEvent,
    ChatStreamEventType,
    ChatStreamHeartbeatEvent,
    ChatStreamResultMetadata,
    ChatStreamStage,
    ChatStreamStartEvent,
    SendChatMessageRequest,
)

logger = logging.getLogger(__name__)


class PhaseTimer:
    """Tracks elapsed time for named phases within a request."""

    def __init__(self, message_id: str):
        self.message_id = message_id
        self.start = time.monotonic()
        self.phases: list[tuple[str, float]] = []
        self._last = self.start

    def mark(self, phase_name: str) -> float:
        """Record a phase completion. Returns ms since last mark."""
        now = time.monotonic()
        elapsed_since_last = (now - self._last) * 1000
        elapsed_total = (now - self.start) * 1000
        self.phases.append((phase_name, elapsed_total))
        self._last = now
        logger.info(
            "TIMING [%s] %s: %.0fms (total: %.0fms)",
            self.message_id[:8],
            phase_name,
            elapsed_since_last,
            elapsed_total,
        )
        return elapsed_since_last

    def summary(self) -> dict:
        """Return a summary dict suitable for structured logging."""
        total = (time.monotonic() - self.start) * 1000
        return {
            "message_id": self.message_id,
            "total_ms": round(total),
            "phases": {name: round(ms) for name, ms in self.phases},
        }


def _build_response(message: ChatMessage) -> ChatMessageResponse:
    """Convert an ORM ChatMessage into a ChatMessageResponse."""
    return ChatMessageResponse(
        message_id=message.message_id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        status=message.status,
        error_message=message.error_message,
        created_at=message.created_at,
        completed_at=message.completed_at,
        token_count=message.token_count,
        duration_ms=message.duration_ms,
        metadata_json=message.metadata_json,
    )


def _build_response_with_stream_url(
    message: ChatMessage, stream_url: str | None = None
) -> ChatMessageWithStreamUrlResponse:
    """Convert an ORM ChatMessage into a ChatMessageWithStreamUrlResponse."""
    return ChatMessageWithStreamUrlResponse(
        message_id=message.message_id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        status=message.status,
        error_message=message.error_message,
        created_at=message.created_at,
        completed_at=message.completed_at,
        token_count=message.token_count,
        duration_ms=message.duration_ms,
        metadata_json=message.metadata_json,
        stream_url=stream_url,
    )


def get_session_by_id(db: DbSession, session_id: str) -> Session | None:
    """Fetch a session by ID. Returns None if not found."""
    return db.query(Session).filter(Session.session_id == session_id).first()


def create_user_message(
    db: DbSession,
    session_id: str,
    request: SendChatMessageRequest,
) -> ChatMessageWithStreamUrlResponse:
    """Create a new user chat message.

    Returns the message with a stream URL for SSE response streaming.
    """
    message_id = str(uuid4())

    message = ChatMessage(
        message_id=message_id,
        session_id=session_id,
        role=ChatRole.USER.value,
        content=request.content,
        status=ChatStatus.PENDING.value,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    stream_url = f"/api/v1/sessions/{session_id}/chat/stream/{message_id}"
    logger.info(
        "Created user message %s for session %s",
        message_id,
        session_id,
    )

    return _build_response_with_stream_url(message, stream_url)


def create_assistant_message(
    db: DbSession,
    session_id: str,
    content: str = "",
    status: str = ChatStatus.STREAMING.value,
) -> ChatMessage:
    """Create a new assistant chat message (typically for streaming responses).

    Returns the raw ORM object for further updates during streaming.
    """
    message_id = str(uuid4())

    message = ChatMessage(
        message_id=message_id,
        session_id=session_id,
        role=ChatRole.ASSISTANT.value,
        content=content,
        status=status,
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    logger.info(
        "Created assistant message %s for session %s",
        message_id,
        session_id,
    )

    return message


def get_message_by_id(
    db: DbSession,
    session_id: str,
    message_id: str,
) -> ChatMessage | None:
    """Fetch a chat message by ID within a session. Returns None if not found."""
    return (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.message_id == message_id,
        )
        .first()
    )


def list_messages(
    db: DbSession,
    session_id: str,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ChatMessageResponse], int]:
    """Return a paginated list of chat messages for a session and total count.

    Messages are ordered by created_at ascending (oldest first).
    """
    total = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).count()
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    messages = [_build_response(m) for m in rows]
    return messages, total


def update_message_status(
    db: DbSession,
    message: ChatMessage,
    status: str,
    error_message: str | None = None,
) -> ChatMessage:
    """Update a message's status and optionally set error message."""
    message.status = status
    if error_message is not None:
        message.error_message = error_message
    db.commit()
    db.refresh(message)
    return message


def complete_message(
    db: DbSession,
    message: ChatMessage,
    content: str,
    token_count: int | None = None,
    duration_ms: int | None = None,
) -> ChatMessage:
    """Mark a message as completed with final content and stats."""
    from datetime import datetime, timezone

    message.content = content
    message.status = ChatStatus.COMPLETED.value
    message.completed_at = datetime.now(timezone.utc)
    message.token_count = token_count
    message.duration_ms = duration_ms

    db.commit()
    db.refresh(message)

    logger.info(
        "Completed message %s (tokens=%s, duration=%sms)",
        message.message_id,
        token_count,
        duration_ms,
    )

    return message


def fail_message(
    db: DbSession,
    message: ChatMessage,
    error_message: str,
) -> ChatMessage:
    """Mark a message as failed with an error message."""
    message.status = ChatStatus.ERROR.value
    message.error_message = error_message
    db.commit()
    db.refresh(message)

    logger.error(
        "Message %s failed: %s",
        message.message_id,
        error_message,
    )

    return message


def delete_message(db: DbSession, session_id: str, message_id: str) -> bool:
    """Delete a chat message by ID.

    Returns True if the message was found and deleted, False otherwise.
    """
    message = get_message_by_id(db, session_id, message_id)
    if message is None:
        return False

    db.delete(message)
    db.commit()

    logger.info("Deleted message %s from session %s", message_id, session_id)
    return True


def clear_chat_history(db: DbSession, session_id: str) -> int:
    """Delete all chat messages for a session.

    Args:
        db: Database session.
        session_id: Session UUID.

    Returns:
        Number of messages deleted.
    """
    result = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.commit()

    logger.info("Cleared %d messages from session %s", result, session_id)
    return result


# ---------------------------------------------------------------------------
# claude-mpm Streaming Integration
# ---------------------------------------------------------------------------


def classify_event(
    event: dict[str, Any],
) -> tuple[ChatStreamEventType, ChatStreamStage]:
    """Classify a JSON event from claude-mpm into event type and stage.

    Stage 1 (EXPANDABLE): System initialization and hooks - NOT persisted
    Stage 2 (PRIMARY): Assistant and result events - persisted to database

    Args:
        event: Parsed JSON event from claude-mpm stream.

    Returns:
        Tuple of (event_type, stage) for routing and display.
    """
    event_type_str = event.get("type", "")

    if event_type_str == "system":
        subtype = event.get("subtype", "")
        if subtype in ("hook_started", "hook_response"):
            return (ChatStreamEventType.SYSTEM_HOOK, ChatStreamStage.EXPANDABLE)
        # init, or any other system subtype
        return (ChatStreamEventType.SYSTEM_INIT, ChatStreamStage.EXPANDABLE)

    elif event_type_str == "stream_event":
        # Token-by-token streaming (if --include-partial-messages is used)
        return (ChatStreamEventType.STREAM_TOKEN, ChatStreamStage.EXPANDABLE)

    elif event_type_str == "assistant":
        return (ChatStreamEventType.ASSISTANT, ChatStreamStage.PRIMARY)

    elif event_type_str == "result":
        return (ChatStreamEventType.RESULT, ChatStreamStage.PRIMARY)

    # Unknown event type - default to expandable for safety
    return (ChatStreamEventType.STREAM_TOKEN, ChatStreamStage.EXPANDABLE)


def extract_metadata(result_event: dict[str, Any]) -> ChatStreamResultMetadata:
    """Extract metadata from a result event.

    The result event contains rich information about the API call including
    token usage, timing, and cost information.

    Args:
        result_event: The parsed result JSON event from claude-mpm.

    Returns:
        ChatStreamResultMetadata with extracted fields.
    """
    usage = result_event.get("usage", {})

    return ChatStreamResultMetadata(
        duration_ms=result_event.get("duration_ms"),
        duration_api_ms=result_event.get("duration_api_ms"),
        cost_usd=result_event.get("total_cost_usd"),
        session_id=result_event.get("session_id"),
        num_turns=result_event.get("num_turns"),
        token_count=usage.get("output_tokens"),
        input_tokens=usage.get("input_tokens"),
        cache_read_tokens=usage.get("cache_read_input_tokens"),
    )


def extract_assistant_content(assistant_event: dict[str, Any]) -> str:
    """Extract text content from an assistant message event.

    The assistant event contains a message object with content blocks.
    We extract and concatenate all text blocks.

    Args:
        assistant_event: The parsed assistant JSON event from claude-mpm.

    Returns:
        Concatenated text content from the assistant message.
    """
    message = assistant_event.get("message", {})
    content_blocks = message.get("content", [])
    text_parts: list[str] = []

    for block in content_blocks:
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))

    return "".join(text_parts)


def _get_claude_mpm_path() -> str:
    """Get the path to claude-mpm CLI.

    Uses configured path if set, otherwise searches PATH.
    Raises ClaudeMpmNotAvailableError if not found.
    """
    if settings.claude_mpm_cli_path:
        if os.path.isfile(settings.claude_mpm_cli_path):
            return settings.claude_mpm_cli_path
        raise ClaudeMpmNotAvailableError(
            f"Configured claude-mpm path not found: {settings.claude_mpm_cli_path}"
        )

    path = shutil.which("claude-mpm")
    if not path:
        raise ClaudeMpmNotAvailableError(
            "claude-mpm CLI is not available on PATH. "
            "Install with: pipx install 'claude-mpm[monitor]'"
        )
    return path


def _prepare_claude_mpm_environment(workspace_path: str) -> dict[str, str]:
    """Prepare environment variables for claude-mpm subprocess.

    Args:
        workspace_path: The session workspace directory.

    Returns:
        Environment dictionary with required variables.

    Raises:
        ClaudeApiKeyNotSetError: If ANTHROPIC_API_KEY is not set.
        SessionWorkspaceNotFoundError: If workspace directory does not exist.
    """
    env = os.environ.copy()

    # Verify workspace exists
    if not os.path.isdir(workspace_path):
        raise SessionWorkspaceNotFoundError(
            f"Session workspace directory not found: {workspace_path}"
        )

    # Set working directory via env var (claude-mpm specific)
    env["CLAUDE_MPM_USER_PWD"] = workspace_path

    # Disable telemetry for privacy
    env["DISABLE_TELEMETRY"] = "1"

    return env


async def stream_claude_mpm_response(
    workspace_path: str,
    user_content: str,
    assistant_message_id: str,
) -> AsyncGenerator[str, None]:
    """Stream response from claude-mpm using subprocess with two-stage parsing.

    Two-Stage Response Streaming:
    - Stage 1 (EXPANDABLE): Plain text init + system JSON events (NOT persisted)
    - Stage 2 (PRIMARY): Final answer from assistant/result events (persisted)

    Output format from claude-mpm with --output-format stream-json --verbose:
    1. Plain text initialization (claude-mpm banner, agent sync, etc.)
    2. JSON streaming events (system, assistant, result)

    Parsing strategy:
    1. Stream plain text lines as INIT_TEXT events (Stage 1)
    2. Detect JSON start (line begins with '{')
    3. Parse JSON events, classify into Stage 1 (system) or Stage 2 (assistant/result)
    4. Extract final answer and metadata from result event
    5. Only Stage 2 content is persisted to database

    CRITICAL: Uses claude-mpm exclusively, NOT native claude CLI.
    See /docs/research/claude-mpm-cli-research.md for details.

    Args:
        workspace_path: The session workspace directory path (extracted from
            Session ORM object before calling to avoid DetachedInstanceError).
        user_content: The user's question/prompt.
        assistant_message_id: UUID of the assistant message being streamed.

    Yields:
        SSE-formatted event strings (event: <type>\ndata: <json>\n\n)

    Raises:
        ClaudeMpmNotAvailableError: claude-mpm not found on PATH.
        ClaudeApiKeyNotSetError: ANTHROPIC_API_KEY not set.
        SessionWorkspaceNotFoundError: Session workspace not found.
        ClaudeMpmTimeoutError: Subprocess timed out.
        ClaudeMpmFailedError: Subprocess returned non-zero exit code.
    """
    start_time = time.time()
    timer = PhaseTimer(assistant_message_id)
    timer.mark("function_entry")
    stage2_content = ""  # Primary answer (persisted to database)
    metadata: ChatStreamResultMetadata | None = None
    json_mode = False  # Track when we enter JSON streaming mode
    last_event_time = time.time()
    # Fallback: collect all plain text output in case JSON events don't provide content
    all_text_output: list[str] = []

    try:
        # Get claude-mpm path
        claude_mpm_path = _get_claude_mpm_path()
        timer.mark("cli_path_resolved")

        # Prepare environment
        env = _prepare_claude_mpm_environment(workspace_path)
        timer.mark("env_prepared")

        # Build command using claude-mpm exclusively
        # NOTE: --non-interactive is the oneshot mode flag
        # Working directory is set via CLAUDE_MPM_USER_PWD env var AND cwd
        # Pass `-- --output-format stream-json --verbose` to native claude CLI
        cmd = [
            claude_mpm_path,
            "run",
            "--non-interactive",  # Oneshot mode
            "--no-hooks",  # Skip hooks for speed
            "--no-tickets",  # Skip ticket creation
            "--launch-method",
            "subprocess",  # Required for output capture
            "-i",
            user_content,  # Input prompt
            "--",  # Pass remaining args to native claude CLI
            "--output-format",
            "stream-json",  # Enable JSON streaming output
            "--verbose",  # Include verbose system events
        ]
        timer.mark("command_built")

        logger.info(
            "Spawning claude-mpm subprocess in %s for message %s (JSON streaming mode)",
            workspace_path,
            assistant_message_id,
        )
        # Debug: log the full command being executed
        cmd_display = cmd.copy()
        # Truncate user content in display to avoid huge logs
        if "-i" in cmd_display:
            i_idx = cmd_display.index("-i")
            if i_idx + 1 < len(cmd_display):
                content = cmd_display[i_idx + 1]
                cmd_display[i_idx + 1] = f"<user_prompt:{len(content)}chars>"
        logger.debug("COMMAND: %s", " ".join(cmd_display))

        # Yield start event
        start_event = ChatStreamStartEvent(message_id=assistant_message_id)
        yield f"event: start\ndata: {start_event.model_dump_json()}\n\n"

        # Start subprocess with working directory set
        # Use configurable buffer limit to prevent LimitOverrunError when
        # claude-mpm returns large tool results (e.g., file contents)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=workspace_path,  # Also set cwd for safety
            limit=settings.subprocess_stream_buffer_limit,
        )
        timer.mark("subprocess_spawned")

        # Stream stdout line by line with two-stage parsing
        first_byte_logged = False
        first_stage2_logged = False
        try:
            while True:
                # Check if we need to send a heartbeat
                current_time = time.time()
                if (
                    current_time - last_event_time
                    > settings.sse_heartbeat_interval_seconds
                ):
                    heartbeat_event = ChatStreamHeartbeatEvent(
                        timestamp=datetime.now(timezone.utc).isoformat()
                    )
                    yield f"event: heartbeat\ndata: {heartbeat_event.model_dump_json()}\n\n"
                    last_event_time = current_time

                try:
                    line = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=settings.claude_mpm_timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    raise ClaudeMpmTimeoutError(
                        f"claude-mpm response timed out after "
                        f"{settings.claude_mpm_timeout_seconds} seconds"
                    )

                if not line:
                    break

                line_str = line.decode("utf-8").rstrip()
                if not line_str:
                    continue

                if not first_byte_logged:
                    timer.mark("first_stdout_byte")
                    first_byte_logged = True

                # Debug: log every line received from claude-mpm
                logger.debug(
                    "RAW LINE from claude-mpm for message %s: %s",
                    assistant_message_id,
                    repr(line_str[:200]) if len(line_str) > 200 else repr(line_str),
                )

                # Detect JSON mode start (line begins with '{')
                if not json_mode and line_str.startswith("{"):
                    json_mode = True
                    timer.mark("json_mode_entered")
                    logger.debug(
                        "Entered JSON streaming mode for message %s",
                        assistant_message_id,
                    )

                if json_mode:
                    # Parse JSON events
                    try:
                        event = json.loads(line_str)
                        event_type, stage = classify_event(event)
                        logger.debug(
                            "PARSED JSON event for message %s: type=%s, stage=%s, raw_type=%s",
                            assistant_message_id,
                            event_type.value,
                            stage.value,
                            event.get("type", "MISSING"),
                        )

                        if stage == ChatStreamStage.EXPANDABLE:
                            # Stage 1: System events go to expandable (NOT persisted)
                            chunk_event = ChatStreamChunkEvent(
                                content=line_str,
                                event_type=event_type,
                                stage=stage,
                                raw_json=event,
                            )
                            yield f"event: {event_type.value}\ndata: {chunk_event.model_dump_json()}\n\n"

                        else:
                            # Stage 2: Assistant/Result events (persisted)
                            if not first_stage2_logged:
                                timer.mark("first_stage2_event")
                                first_stage2_logged = True
                            if event_type == ChatStreamEventType.ASSISTANT:
                                # Debug: capture JSON structure before extraction
                                logger.debug(
                                    "ASSISTANT event for message %s: keys=%s, has_message=%s, event_preview=%s",
                                    assistant_message_id,
                                    list(event.keys()),
                                    "message" in event,
                                    json.dumps(event)[:1000],
                                )
                                content = extract_assistant_content(event)
                                # Debug: capture extraction result
                                logger.debug(
                                    "ASSISTANT extracted content for message %s: length=%d, empty=%s",
                                    assistant_message_id,
                                    len(content),
                                    content == "",
                                )
                                stage2_content = content
                                logger.info(
                                    "ASSISTANT event: extracted stage2_content for message %s (length=%d)",
                                    assistant_message_id,
                                    len(stage2_content),
                                )
                                chunk_event = ChatStreamChunkEvent(
                                    content=content,
                                    event_type=event_type,
                                    stage=stage,
                                    raw_json=event,
                                )
                                yield f"event: {event_type.value}\ndata: {chunk_event.model_dump_json()}\n\n"

                            elif event_type == ChatStreamEventType.RESULT:
                                # Debug: capture JSON structure for result event
                                logger.debug(
                                    "RESULT event for message %s: keys=%s, result_preview=%s",
                                    assistant_message_id,
                                    list(event.keys()),
                                    repr(event.get("result", ""))[:500]
                                    if event.get("result")
                                    else "<no result field>",
                                )
                                # Extract final answer and metadata
                                result_content = event.get("result", "")
                                if result_content:
                                    stage2_content = result_content
                                    logger.info(
                                        "RESULT event: extracted stage2_content for message %s (length=%d)",
                                        assistant_message_id,
                                        len(stage2_content),
                                    )
                                else:
                                    logger.warning(
                                        "RESULT event: empty result field for message %s",
                                        assistant_message_id,
                                    )
                                metadata = extract_metadata(event)
                                chunk_event = ChatStreamChunkEvent(
                                    content=result_content,
                                    event_type=event_type,
                                    stage=stage,
                                    raw_json=event,
                                )
                                yield f"event: {event_type.value}\ndata: {chunk_event.model_dump_json()}\n\n"

                    except json.JSONDecodeError:
                        # If JSON parsing fails in JSON mode, treat as plain text
                        # Also collect for fallback content persistence
                        all_text_output.append(line_str)
                        logger.warning(
                            "Failed to parse JSON in JSON mode for message %s: %s",
                            assistant_message_id,
                            line_str[:100],
                        )
                        chunk_event = ChatStreamChunkEvent(
                            content=line_str,
                            event_type=ChatStreamEventType.INIT_TEXT,
                            stage=ChatStreamStage.EXPANDABLE,
                            raw_json=None,
                        )
                        yield f"event: {ChatStreamEventType.INIT_TEXT.value}\ndata: {chunk_event.model_dump_json()}\n\n"

                else:
                    # Plain text mode (initialization) - Stage 1 (NOT persisted)
                    # Collect text as fallback for content persistence
                    all_text_output.append(line_str)
                    chunk_event = ChatStreamChunkEvent(
                        content=line_str,
                        event_type=ChatStreamEventType.INIT_TEXT,
                        stage=ChatStreamStage.EXPANDABLE,
                        raw_json=None,
                    )
                    yield f"event: {ChatStreamEventType.INIT_TEXT.value}\ndata: {chunk_event.model_dump_json()}\n\n"

                last_event_time = time.time()

            # Wait for process to complete
            await process.wait()
            timer.mark("stream_complete")

            if process.returncode != 0:
                stderr = await process.stderr.read()
                error_msg = stderr.decode("utf-8") if stderr else "Unknown error"
                raise ClaudeMpmFailedError(
                    f"claude-mpm process failed with exit code {process.returncode}: "
                    f"{error_msg}"
                )

        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise

        # Calculate duration (fallback if not in metadata)
        duration_ms = int((time.time() - start_time) * 1000)

        # Use metadata values if available, otherwise use fallbacks
        final_token_count = metadata.token_count if metadata else None
        final_duration_ms = metadata.duration_ms if metadata else duration_ms

        # Fallback: if stage2_content is empty but we collected plain text, use that
        if not stage2_content and all_text_output:
            # Join all collected text lines as the content
            stage2_content = "\n".join(all_text_output)
            logger.warning(
                "FALLBACK: No ASSISTANT/RESULT events received for message %s, "
                "using collected plain text output (length=%d)",
                assistant_message_id,
                len(stage2_content),
            )

        # Error logging if stage2_content is still empty
        if not stage2_content:
            logger.error(
                "EMPTY CONTENT at stream completion for message %s: "
                "stage2_content is empty, all_text_output has %d lines (total %d chars)",
                assistant_message_id,
                len(all_text_output),
                sum(len(line) for line in all_text_output),
            )

        # Log final stage2_content before creating complete event
        logger.info(
            "Creating complete event for message %s: stage2_content length=%d, first_100=%s",
            assistant_message_id,
            len(stage2_content),
            repr(stage2_content[:100]) if stage2_content else "<empty>",
        )

        # Yield complete event with Stage 2 content only (this is what gets persisted)
        complete_event = ChatStreamCompleteEvent(
            message_id=assistant_message_id,
            content=stage2_content,
            metadata=metadata,
            # Legacy fields for backwards compatibility
            token_count=final_token_count,
            duration_ms=final_duration_ms,
        )
        yield f"event: complete\ndata: {complete_event.model_dump_json()}\n\n"
        timer.mark("response_finalized")

        logger.info(
            "Completed streaming for message %s (tokens=%s, duration=%sms, cost=$%s)",
            assistant_message_id,
            final_token_count,
            final_duration_ms,
            metadata.cost_usd if metadata else None,
        )

        timing_summary = timer.summary()
        logger.info(
            "TIMING SUMMARY [%s]: %s",
            assistant_message_id[:8],
            json.dumps(timing_summary),
        )

    except (
        ClaudeMpmNotAvailableError,
        ClaudeApiKeyNotSetError,
        SessionWorkspaceNotFoundError,
        ClaudeMpmTimeoutError,
        ClaudeMpmFailedError,
    ) as e:
        timer.mark("error_occurred")
        timing_summary = timer.summary()
        logger.exception("claude-mpm error for message %s: %s", assistant_message_id, e)
        logger.error(
            "TIMING SUMMARY (ERROR) [%s]: %s",
            assistant_message_id[:8],
            json.dumps(timing_summary),
        )
        error_event = ChatStreamErrorEvent(
            message_id=assistant_message_id,
            error=str(e),
        )
        yield f"event: error\ndata: {error_event.model_dump_json()}\n\n"
        raise

    except Exception as e:
        timer.mark("error_occurred")
        timing_summary = timer.summary()
        logger.exception(
            "Unexpected error streaming Claude response for message %s: %s",
            assistant_message_id,
            e,
        )
        logger.error(
            "TIMING SUMMARY (ERROR) [%s]: %s",
            assistant_message_id[:8],
            json.dumps(timing_summary),
        )
        error_event = ChatStreamErrorEvent(
            message_id=assistant_message_id,
            error=f"Internal error: {str(e)}",
        )
        yield f"event: error\ndata: {error_event.model_dump_json()}\n\n"
        raise
