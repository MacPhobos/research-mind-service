"""Exception hierarchy for content extraction."""

from __future__ import annotations


class ExtractionError(Exception):
    """Base exception for all extraction errors."""

    pass


class NetworkError(ExtractionError):
    """Raised for network-related failures (timeout, connection, DNS)."""

    pass


class ContentTypeError(ExtractionError):
    """Raised when content type cannot be detected or is unsupported."""

    pass


class EmptyContentError(ExtractionError):
    """Raised when extraction produces insufficient content."""

    pass


class RateLimitError(ExtractionError):
    """Raised when HTTP 429 is received."""

    pass


class ContentTooLargeError(ExtractionError):
    """Raised when content exceeds size limits."""

    pass
