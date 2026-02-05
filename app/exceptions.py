"""Custom exceptions for the research-mind service.

Provides specific exception classes for claude-mpm integration and chat service errors.
"""

from __future__ import annotations


class ChatServiceError(Exception):
    """Base exception for chat service errors."""

    pass


class ClaudeMpmNotAvailableError(ChatServiceError):
    """Raised when claude-mpm CLI is not available on PATH.

    Error Code: CLAUDE_MPM_NOT_AVAILABLE
    """

    pass


class ClaudeMpmTimeoutError(ChatServiceError):
    """Raised when claude-mpm subprocess times out.

    Error Code: CLAUDE_MPM_TIMEOUT
    """

    pass


class ClaudeMpmFailedError(ChatServiceError):
    """Raised when claude-mpm process returns non-zero exit code.

    Error Code: CLAUDE_MPM_FAILED
    """

    pass


class ClaudeApiKeyNotSetError(ChatServiceError):
    """Raised when ANTHROPIC_API_KEY is not set in the environment.

    Error Code: CLAUDE_API_KEY_NOT_SET
    """

    pass


class SessionNotIndexedError(ChatServiceError):
    """Raised when session is not indexed but chat is requested.

    Error Code: SESSION_NOT_INDEXED
    """

    pass


class SessionWorkspaceNotFoundError(ChatServiceError):
    """Raised when session workspace directory does not exist.

    Error Code: SESSION_WORKSPACE_NOT_FOUND
    """

    pass


class ChatStreamExpiredError(ChatServiceError):
    """Raised when attempting to connect to a stream that has already completed.

    Error Code: CHAT_STREAM_EXPIRED
    """

    pass


# ---------------------------------------------------------------------------
# Export Exceptions
# ---------------------------------------------------------------------------


class ExportError(Exception):
    """Base exception for export-related errors."""

    pass


class InvalidExportFormatError(ExportError):
    """Raised when an invalid export format is specified.

    Error Code: INVALID_FORMAT
    """

    def __init__(self, format_value: str) -> None:
        self.format_value = format_value
        super().__init__(
            f"Invalid export format: {format_value}. Must be 'pdf' or 'markdown'."
        )


class NoChatMessagesError(ExportError):
    """Raised when there are no messages to export.

    Error Code: NO_CHAT_MESSAGES
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"No chat messages found for session {session_id}")


class ExportGenerationError(ExportError):
    """Raised when export file generation fails.

    Error Code: EXPORT_GENERATION_FAILED
    """

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        message = "Failed to generate export file"
        if detail:
            message = f"{message}. {detail}"
        super().__init__(message)


class NotAssistantMessageError(ExportError):
    """Raised when trying to export from a non-assistant message.

    Error Code: NOT_ASSISTANT_MESSAGE
    """

    def __init__(self, message_id: str) -> None:
        self.message_id = message_id
        super().__init__(
            f"Message {message_id} is not an assistant message. "
            "Single export must target assistant messages."
        )


class NoPrecedingUserMessageError(ExportError):
    """Raised when assistant message has no preceding user question.

    Error Code: NO_PRECEDING_USER_MESSAGE
    """

    def __init__(self, message_id: str) -> None:
        self.message_id = message_id
        super().__init__(
            f"No preceding user message found for assistant message {message_id}"
        )
