"""Tests for extraction exceptions."""

from __future__ import annotations

from app.services.extractors.exceptions import (
    ContentTooLargeError,
    ContentTypeError,
    EmptyContentError,
    ExtractionError,
    NetworkError,
    RateLimitError,
)


class TestExceptionHierarchy:
    """Test that all exceptions inherit from ExtractionError."""

    def test_network_error_inherits_from_extraction_error(self) -> None:
        """Test NetworkError is a subclass of ExtractionError."""
        assert issubclass(NetworkError, ExtractionError)

    def test_content_type_error_inherits_from_extraction_error(self) -> None:
        """Test ContentTypeError is a subclass of ExtractionError."""
        assert issubclass(ContentTypeError, ExtractionError)

    def test_empty_content_error_inherits_from_extraction_error(self) -> None:
        """Test EmptyContentError is a subclass of ExtractionError."""
        assert issubclass(EmptyContentError, ExtractionError)

    def test_rate_limit_error_inherits_from_extraction_error(self) -> None:
        """Test RateLimitError is a subclass of ExtractionError."""
        assert issubclass(RateLimitError, ExtractionError)

    def test_content_too_large_error_inherits_from_extraction_error(self) -> None:
        """Test ContentTooLargeError is a subclass of ExtractionError."""
        assert issubclass(ContentTooLargeError, ExtractionError)

    def test_extraction_error_inherits_from_exception(self) -> None:
        """Test ExtractionError is a subclass of Exception."""
        assert issubclass(ExtractionError, Exception)


class TestExceptionMessages:
    """Test that exceptions can carry messages."""

    def test_network_error_with_message(self) -> None:
        """Test NetworkError can carry a message."""
        error = NetworkError("Connection timeout")
        assert str(error) == "Connection timeout"

    def test_content_type_error_with_message(self) -> None:
        """Test ContentTypeError can carry a message."""
        error = ContentTypeError("Unsupported: application/pdf")
        assert str(error) == "Unsupported: application/pdf"

    def test_empty_content_error_with_message(self) -> None:
        """Test EmptyContentError can carry a message."""
        error = EmptyContentError("Only 50 chars extracted")
        assert str(error) == "Only 50 chars extracted"

    def test_rate_limit_error_with_message(self) -> None:
        """Test RateLimitError can carry a message."""
        error = RateLimitError("Rate limited by example.com")
        assert str(error) == "Rate limited by example.com"

    def test_content_too_large_error_with_message(self) -> None:
        """Test ContentTooLargeError can carry a message."""
        error = ContentTooLargeError("Content exceeds 50MB limit")
        assert str(error) == "Content exceeds 50MB limit"


class TestExceptionCatching:
    """Test that exceptions can be caught at different levels."""

    def test_catch_all_extraction_errors(self) -> None:
        """Test that all specific errors can be caught as ExtractionError."""
        errors = [
            NetworkError("test"),
            ContentTypeError("test"),
            EmptyContentError("test"),
            RateLimitError("test"),
            ContentTooLargeError("test"),
        ]

        for error in errors:
            try:
                raise error
            except ExtractionError as e:
                assert str(e) == "test"
            except Exception:
                assert (
                    False
                ), f"Expected {type(error).__name__} to be caught as ExtractionError"

    def test_catch_specific_errors(self) -> None:
        """Test that specific errors can be caught individually."""
        try:
            raise NetworkError("network issue")
        except NetworkError as e:
            assert "network issue" in str(e)
        except ExtractionError:
            assert False, "Should have caught as NetworkError, not ExtractionError"
