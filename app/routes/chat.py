"""Chat message REST endpoints with SSE streaming support.

Provides endpoints for sending chat messages and streaming AI responses
using claude-mpm subprocess integration.

CRITICAL: Uses claude-mpm exclusively, NOT native claude CLI.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db, get_session_local
from app.exceptions import (
    ChatServiceError,
    ChatStreamExpiredError,
    ClaudeApiKeyNotSetError,
    ClaudeMpmFailedError,
    ClaudeMpmNotAvailableError,
    ClaudeMpmTimeoutError,
    SessionWorkspaceNotFoundError,
)
from app.models.chat_message import ChatStatus
from app.schemas.chat import (
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatMessageWithStreamUrlResponse,
    ChatStreamCompleteEvent,
    ChatStreamErrorEvent,
    SendChatMessageRequest,
)
from app.services import chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["chat"])


@router.post(
    "/{session_id}/chat",
    response_model=ChatMessageWithStreamUrlResponse,
    status_code=201,
)
def send_chat_message(
    session_id: str,
    request: SendChatMessageRequest,
    db: Session = Depends(get_db),
) -> ChatMessageWithStreamUrlResponse:
    """Send a new chat message and get a stream URL for the response.

    Creates both a user message and a placeholder assistant message.
    The assistant message will be populated via the SSE stream endpoint.

    The session must be indexed before chat is available.
    """
    # Verify session exists
    session = chat_service.get_session_by_id(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Session '{session_id}' not found",
                }
            },
        )

    # Verify session is indexed
    if not session.is_indexed():
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "SESSION_NOT_INDEXED",
                    "message": "Session must be indexed before chat is available",
                }
            },
        )

    # Create user message
    user_response = chat_service.create_user_message(db, session_id, request)

    # Create placeholder assistant message with status="pending"
    assistant_message = chat_service.create_assistant_message(
        db,
        session_id,
        content="",
        status=ChatStatus.PENDING.value,
    )

    # Build stream URL pointing to the assistant message
    stream_url = f"/api/v1/sessions/{session_id}/chat/stream/{assistant_message.message_id}"

    # Update the user response with the correct stream URL
    # (pointing to assistant message, not user message)
    return ChatMessageWithStreamUrlResponse(
        message_id=user_response.message_id,
        session_id=user_response.session_id,
        role=user_response.role,
        content=user_response.content,
        status=user_response.status,
        error_message=user_response.error_message,
        created_at=user_response.created_at,
        completed_at=user_response.completed_at,
        token_count=user_response.token_count,
        duration_ms=user_response.duration_ms,
        metadata_json=user_response.metadata_json,
        stream_url=stream_url,
    )


@router.get("/{session_id}/chat/stream/{message_id}")
async def stream_chat_response(
    session_id: str,
    message_id: str,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Stream the AI response for a chat message using Server-Sent Events.

    Invokes claude-mpm subprocess to generate response and streams
    output line-by-line to the client.

    SSE Event Types:
    - start: {"message_id": "...", "status": "streaming"}
    - chunk: {"content": "line of text"}
    - complete: {"message_id": "...", "status": "completed", ...}
    - error: {"message_id": "...", "status": "error", "error": "..."}
    - heartbeat: {"timestamp": "ISO8601"} (every 15 seconds)
    """
    # Get session
    session = chat_service.get_session_by_id(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Session '{session_id}' not found",
                }
            },
        )

    # Get assistant message
    assistant_message = chat_service.get_message_by_id(db, session_id, message_id)
    if assistant_message is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "CHAT_MESSAGE_NOT_FOUND",
                    "message": f"Message '{message_id}' not found",
                }
            },
        )

    # Verify message is in a streamable state
    if assistant_message.status not in (
        ChatStatus.PENDING.value,
        ChatStatus.STREAMING.value,
    ):
        raise HTTPException(
            status_code=410,
            detail={
                "error": {
                    "code": "CHAT_STREAM_EXPIRED",
                    "message": "Stream has already completed or failed",
                }
            },
        )

    # Find the most recent user message before this assistant message
    # (the one that triggered this response)
    messages, _ = chat_service.list_messages(db, session_id, limit=100)
    user_message = None
    for msg in reversed(messages):
        if msg.role == "user" and msg.created_at < assistant_message.created_at:
            user_message = msg
            break

    if user_message is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "CHAT_MESSAGE_NOT_FOUND",
                    "message": "Associated user message not found",
                }
            },
        )

    # Update assistant message status to streaming
    chat_service.update_message_status(
        db, assistant_message, ChatStatus.STREAMING.value
    )

    # Extract primitive values from ORM objects BEFORE the generator starts
    # This prevents DetachedInstanceError when db session closes
    workspace_path = session.workspace_path
    user_content = user_message.content
    assistant_msg_id = message_id
    user_msg_id = user_message.message_id  # Extract user message ID for later use

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events from claude-mpm subprocess.

        Updates the assistant message in the database when streaming
        completes or fails.

        IMPORTANT: Content is extracted from 'assistant' and 'result' events
        as they arrive, NOT from the 'complete' event. This ensures content
        is captured even if the client disconnects before complete event.
        """
        final_content = ""
        final_token_count: int | None = None
        final_duration_ms: int | None = None
        error_occurred = False
        error_message: str | None = None

        try:
            async for event in chat_service.stream_claude_mpm_response(
                workspace_path, user_content, assistant_msg_id
            ):
                # Extract content from assistant event AS IT ARRIVES
                # This ensures content is captured even if client disconnects
                if event.startswith("event: assistant\n"):
                    try:
                        for line in event.split("\n"):
                            if line.startswith("data: "):
                                data_json = line[6:]  # Remove "data: " prefix
                                chunk_data = json.loads(data_json)
                                content = chunk_data.get("content", "")
                                if content:
                                    final_content = content
                                    logger.debug(
                                        "Captured content from assistant event: length=%d",
                                        len(final_content),
                                    )
                                break
                    except json.JSONDecodeError as e:
                        logger.warning(
                            "Failed to parse assistant event: %s, event=%s",
                            e,
                            event[:200],
                        )

                # Extract content from result event (backup/alternative source)
                elif event.startswith("event: result\n"):
                    try:
                        for line in event.split("\n"):
                            if line.startswith("data: "):
                                data_json = line[6:]  # Remove "data: " prefix
                                chunk_data = json.loads(data_json)
                                result_content = chunk_data.get("result", "")
                                if result_content and not final_content:
                                    final_content = result_content
                                    logger.debug(
                                        "Captured content from result event: length=%d",
                                        len(final_content),
                                    )
                                break
                    except json.JSONDecodeError as e:
                        logger.warning(
                            "Failed to parse result event: %s, event=%s",
                            e,
                            event[:200],
                        )

                # Parse complete event for metadata only (token_count, duration_ms)
                # Content should already be captured from assistant/result events
                elif event.startswith("event: complete\n"):
                    try:
                        for line in event.split("\n"):
                            if line.startswith("data: "):
                                data_json = line[6:]  # Remove "data: " prefix
                                complete_data = json.loads(data_json)
                                # Only use content from complete if not already captured
                                if not final_content:
                                    final_content = complete_data.get("content", "")
                                final_token_count = complete_data.get("token_count")
                                final_duration_ms = complete_data.get("duration_ms")
                                logger.info(
                                    "Parsed complete event for message %s: content_length=%d, token_count=%s",
                                    assistant_msg_id,
                                    len(final_content),
                                    final_token_count,
                                )
                                break
                    except json.JSONDecodeError as e:
                        logger.error(
                            "Failed to parse complete event: %s, event=%s",
                            e,
                            event[:200],
                        )

                elif event.startswith("event: error\n"):
                    # Extract error message using robust line-by-line parsing
                    try:
                        for line in event.split("\n"):
                            if line.startswith("data: "):
                                data_json = line[6:]  # Remove "data: " prefix
                                error_data = json.loads(data_json)
                                error_occurred = True
                                error_message = error_data.get("error", "Unknown error")
                                break
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse error event: {e}, event={event[:200]}")
                        error_occurred = True
                        error_message = "Unknown streaming error"

                yield event

        except (
            ClaudeMpmNotAvailableError,
            ClaudeApiKeyNotSetError,
            SessionWorkspaceNotFoundError,
            ClaudeMpmTimeoutError,
            ClaudeMpmFailedError,
        ) as e:
            error_occurred = True
            error_message = str(e)
            # The error event was already yielded by the service

        except Exception as e:
            logger.exception("Streaming error for message %s: %s", assistant_msg_id, e)
            error_occurred = True
            error_message = f"Internal error: {str(e)}"
            error_event = ChatStreamErrorEvent(
                message_id=assistant_msg_id,
                error=error_message,
            )
            yield f"event: error\ndata: {error_event.model_dump_json()}\n\n"

        finally:
            # Update message in database with final state
            # Use a new session since we're in an async context
            try:
                SessionLocal = get_session_local()
                with SessionLocal() as final_db:
                    # Update assistant message
                    final_message = chat_service.get_message_by_id(
                        final_db, session_id, assistant_msg_id
                    )
                    if final_message:
                        if error_occurred:
                            chat_service.fail_message(
                                final_db,
                                final_message,
                                error_message or "Unknown error",
                            )
                        else:
                            logger.info(
                                "Saving message %s to database: content_length=%d",
                                assistant_msg_id,
                                len(final_content),
                            )
                            chat_service.complete_message(
                                final_db,
                                final_message,
                                final_content,
                                token_count=final_token_count,
                                duration_ms=final_duration_ms,
                            )

                    # Also mark the user message as completed
                    # Find and update the user message that triggered this response
                    user_msg = chat_service.get_message_by_id(
                        final_db, session_id, user_msg_id
                    )
                    if user_msg and user_msg.status == "pending":
                        if error_occurred:
                            # If assistant failed, mark user message as error too
                            chat_service.fail_message(
                                final_db,
                                user_msg,
                                "Assistant response failed",
                            )
                        else:
                            # Mark user message as completed
                            chat_service.complete_message(
                                final_db,
                                user_msg,
                                user_msg.content,  # Keep original content
                                token_count=None,
                                duration_ms=None,
                            )
                            logger.info(
                                "Marked user message %s as completed",
                                user_msg_id,
                            )
            except Exception as db_error:
                logger.exception(
                    "Failed to update message %s after streaming: %s",
                    assistant_msg_id,
                    db_error,
                )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/{session_id}/chat", response_model=ChatMessageListResponse)
def list_chat_messages(
    session_id: str,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> ChatMessageListResponse:
    """List all chat messages for a session with pagination."""
    # Verify session exists
    session = chat_service.get_session_by_id(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Session '{session_id}' not found",
                }
            },
        )

    messages, total = chat_service.list_messages(
        db, session_id, limit=limit, offset=offset
    )
    return ChatMessageListResponse(messages=messages, count=total)


@router.get(
    "/{session_id}/chat/{message_id}",
    response_model=ChatMessageResponse,
)
def get_chat_message(
    session_id: str,
    message_id: str,
    db: Session = Depends(get_db),
) -> ChatMessageResponse:
    """Get a single chat message by ID."""
    # Verify session exists
    session = chat_service.get_session_by_id(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Session '{session_id}' not found",
                }
            },
        )

    message = chat_service.get_message_by_id(db, session_id, message_id)
    if message is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "CHAT_MESSAGE_NOT_FOUND",
                    "message": f"Chat message '{message_id}' not found in session '{session_id}'",
                }
            },
        )

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


@router.delete(
    "/{session_id}/chat/{message_id}",
    status_code=204,
    response_model=None,
)
def delete_chat_message(
    session_id: str,
    message_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a chat message."""
    # Verify session exists
    session = chat_service.get_session_by_id(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Session '{session_id}' not found",
                }
            },
        )

    deleted = chat_service.delete_message(db, session_id, message_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "CHAT_MESSAGE_NOT_FOUND",
                    "message": f"Chat message '{message_id}' not found in session '{session_id}'",
                }
            },
        )


@router.delete(
    "/{session_id}/chat",
    status_code=204,
    response_model=None,
)
def clear_chat_history(
    session_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Clear all chat messages for a session."""
    # Verify session exists
    session = chat_service.get_session_by_id(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Session '{session_id}' not found",
                }
            },
        )

    chat_service.clear_chat_history(db, session_id)
