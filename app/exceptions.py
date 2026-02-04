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
