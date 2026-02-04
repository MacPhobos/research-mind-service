"""Business logic for chat message CRUD operations.

Includes claude-mpm subprocess integration for AI-powered chat responses.
CRITICAL: Uses claude-mpm executable exclusively. Never the native claude CLI.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
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
    ChatStreamHeartbeatEvent,
    ChatStreamStartEvent,
    SendChatMessageRequest,
)

logger = logging.getLogger(__name__)


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
    total = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .count()
    )
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


# ---------------------------------------------------------------------------
# claude-mpm Streaming Integration
# ---------------------------------------------------------------------------


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
    """Stream response from claude-mpm using subprocess.

    Uses line-buffered streaming since claude-mpm outputs plain text.
    Yields SSE-formatted events for real-time frontend updates.

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
    accumulated_content = ""
    token_count = 0
    last_event_time = time.time()

    try:
        # Get claude-mpm path
        claude_mpm_path = _get_claude_mpm_path()

        # Prepare environment
        env = _prepare_claude_mpm_environment(workspace_path)

        # Build command using claude-mpm exclusively
        # NOTE: --non-interactive is the oneshot mode flag
        # Working directory is set via CLAUDE_MPM_USER_PWD env var AND cwd
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
        ]

        logger.info(
            "Spawning claude-mpm subprocess in %s for message %s",
            workspace_path,
            assistant_message_id,
        )

        # Yield start event
        start_event = ChatStreamStartEvent(message_id=assistant_message_id)
        yield f"event: start\ndata: {start_event.model_dump_json()}\n\n"

        # Start subprocess with working directory set
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=workspace_path,  # Also set cwd for safety
        )

        # Stream stdout line by line
        # NOTE: claude-mpm outputs plain text, not JSON
        try:
            while True:
                # Check if we need to send a heartbeat
                current_time = time.time()
                if current_time - last_event_time > settings.sse_heartbeat_interval_seconds:
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

                line_str = line.decode("utf-8")
                if not line_str:
                    continue

                # Accumulate content
                accumulated_content += line_str
                # Rough token estimate (words)
                token_count += len(line_str.split())

                # Yield chunk event with the line
                chunk_event = ChatStreamChunkEvent(content=line_str)
                yield f"event: chunk\ndata: {chunk_event.model_dump_json()}\n\n"
                last_event_time = time.time()

            # Wait for process to complete
            await process.wait()

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

        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)

        # Yield complete event with final content
        complete_event = ChatStreamCompleteEvent(
            message_id=assistant_message_id,
            content=accumulated_content,
            token_count=token_count,
            duration_ms=duration_ms,
        )
        yield f"event: complete\ndata: {complete_event.model_dump_json()}\n\n"

        logger.info(
            "Completed streaming for message %s (tokens=%d, duration=%dms)",
            assistant_message_id,
            token_count,
            duration_ms,
        )

    except (
        ClaudeMpmNotAvailableError,
        ClaudeApiKeyNotSetError,
        SessionWorkspaceNotFoundError,
        ClaudeMpmTimeoutError,
        ClaudeMpmFailedError,
    ) as e:
        logger.exception("claude-mpm error for message %s: %s", assistant_message_id, e)
        error_event = ChatStreamErrorEvent(
            message_id=assistant_message_id,
            error=str(e),
        )
        yield f"event: error\ndata: {error_event.model_dump_json()}\n\n"
        raise

    except Exception as e:
        logger.exception(
            "Unexpected error streaming Claude response for message %s: %s",
            assistant_message_id,
            e,
        )
        error_event = ChatStreamErrorEvent(
            message_id=assistant_message_id,
            error=f"Internal error: {str(e)}",
        )
        yield f"event: error\ndata: {error_event.model_dump_json()}\n\n"
        raise
