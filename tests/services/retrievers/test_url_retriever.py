"""Tests for URL retriever with ExtractionPipeline integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.extractors.base import ExtractionResult
from app.services.extractors.exceptions import (
    ContentTooLargeError,
    ContentTypeError,
    EmptyContentError,
    NetworkError,
    RateLimitError,
)
from app.services.retrievers.url_retriever import UrlRetriever


class TestUrlRetrieverSuccess:
    """Test suite for successful URL extraction."""

    def test_extract_success_with_title(self, tmp_path: Path) -> None:
        """Successful extraction stores markdown and metadata."""
        mock_result = ExtractionResult(
            content="# Test Article\n\nThis is the extracted content.",
            title="Test Article",
            word_count=6,
            extraction_method="trafilatura",
            extraction_time_ms=150.5,
            warnings=[],
        )

        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            retriever = UrlRetriever(timeout=10)
            result = retriever.retrieve(
                source="https://example.com/article",
                target_dir=tmp_path,
                title="Custom Title",  # Override
            )

        assert result.success is True
        assert result.title == "Custom Title"  # Override used
        assert result.mime_type == "text/markdown"
        assert result.size_bytes == len(mock_result.content.encode("utf-8"))

        # Verify content file
        content_file = tmp_path / "content.md"
        assert content_file.exists()
        assert content_file.read_text() == mock_result.content

        # Verify metadata
        meta_file = tmp_path / "metadata.json"
        assert meta_file.exists()
        meta = json.loads(meta_file.read_text())
        assert meta["url"] == "https://example.com/article"
        assert meta["title"] == "Custom Title"
        assert meta["word_count"] == 6
        assert meta["extraction_method"] == "trafilatura"
        assert meta["extraction_time_ms"] == 150.5
        assert "retrieved_at" in meta

    def test_extract_uses_extracted_title_when_not_provided(
        self, tmp_path: Path
    ) -> None:
        """Uses extracted title when no override provided."""
        mock_result = ExtractionResult(
            content="Article content",
            title="Extracted Title",
            word_count=2,
            extraction_method="newspaper4k",
            extraction_time_ms=200.0,
        )

        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            retriever = UrlRetriever()
            result = retriever.retrieve(
                source="https://example.com/page",
                target_dir=tmp_path,
            )

        assert result.success is True
        assert result.title == "Extracted Title"
        meta = json.loads((tmp_path / "metadata.json").read_text())
        assert meta["title"] == "Extracted Title"

    def test_extract_falls_back_to_url_when_no_title(self, tmp_path: Path) -> None:
        """Falls back to URL when no title extracted or provided."""
        mock_result = ExtractionResult(
            content="Some content",
            title="",  # Empty title
            word_count=2,
            extraction_method="trafilatura",
            extraction_time_ms=100.0,
        )

        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            retriever = UrlRetriever()
            result = retriever.retrieve(
                source="https://example.com/untitled",
                target_dir=tmp_path,
            )

        assert result.success is True
        assert result.title == "https://example.com/untitled"

    def test_extract_includes_warnings_in_metadata(self, tmp_path: Path) -> None:
        """Extraction warnings are included in metadata."""
        mock_result = ExtractionResult(
            content="Content with warnings",
            title="Article",
            word_count=3,
            extraction_method="trafilatura",
            extraction_time_ms=100.0,
            warnings=["Image extraction failed", "Date parsing failed"],
        )

        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            retriever = UrlRetriever()
            result = retriever.retrieve(
                source="https://example.com/with-warnings",
                target_dir=tmp_path,
            )

        assert result.success is True
        meta = json.loads((tmp_path / "metadata.json").read_text())
        assert "warnings" in meta
        assert len(meta["warnings"]) == 2
        assert "Image extraction failed" in meta["warnings"]

    def test_extract_playwright_method(self, tmp_path: Path) -> None:
        """Playwright extraction method is preserved."""
        mock_result = ExtractionResult(
            content="JavaScript rendered content",
            title="SPA Page",
            word_count=3,
            extraction_method="playwright+trafilatura",
            extraction_time_ms=2500.0,
        )

        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            retriever = UrlRetriever(retry_with_js=True)
            result = retriever.retrieve(
                source="https://example.com/spa",
                target_dir=tmp_path,
            )

        assert result.success is True
        meta = json.loads((tmp_path / "metadata.json").read_text())
        assert meta["extraction_method"] == "playwright+trafilatura"

    def test_custom_metadata_merged(self, tmp_path: Path) -> None:
        """Custom metadata is merged with extraction metadata."""
        mock_result = ExtractionResult(
            content="Content",
            title="Title",
            word_count=1,
            extraction_method="trafilatura",
            extraction_time_ms=100.0,
        )

        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            retriever = UrlRetriever()
            result = retriever.retrieve(
                source="https://example.com/page",
                target_dir=tmp_path,
                metadata={"custom_key": "custom_value", "session_id": "sess_123"},
            )

        assert result.success is True
        meta = json.loads((tmp_path / "metadata.json").read_text())
        assert meta["custom_key"] == "custom_value"
        assert meta["session_id"] == "sess_123"
        assert meta["url"] == "https://example.com/page"


class TestUrlRetrieverErrors:
    """Test suite for URL extraction error handling."""

    def test_network_error(self, tmp_path: Path) -> None:
        """NetworkError returns success=False with error_type."""
        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            side_effect=NetworkError("Timeout fetching https://slow.example.com"),
        ):
            retriever = UrlRetriever()
            result = retriever.retrieve(
                source="https://slow.example.com",
                target_dir=tmp_path,
            )

        assert result.success is False
        assert "Timeout" in result.error_message
        assert result.metadata["error_type"] == "network_error"
        assert result.metadata["url"] == "https://slow.example.com"
        assert result.mime_type is None
        assert result.size_bytes == 0

    def test_content_type_error(self, tmp_path: Path) -> None:
        """ContentTypeError for non-HTML content."""
        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            side_effect=ContentTypeError("Unsupported content type: application/pdf"),
        ):
            retriever = UrlRetriever()
            result = retriever.retrieve(
                source="https://example.com/doc.pdf",
                target_dir=tmp_path,
            )

        assert result.success is False
        assert "Unsupported content type" in result.error_message
        assert result.metadata["error_type"] == "content_type_error"

    def test_empty_content_error(self, tmp_path: Path) -> None:
        """EmptyContentError when extraction produces no content."""
        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            side_effect=EmptyContentError(
                "Extracted content too short: 10 chars (min: 100)"
            ),
        ):
            retriever = UrlRetriever(retry_with_js=False)
            result = retriever.retrieve(
                source="https://example.com/empty",
                target_dir=tmp_path,
            )

        assert result.success is False
        assert "too short" in result.error_message
        assert result.metadata["error_type"] == "empty_content_error"

    def test_rate_limit_error(self, tmp_path: Path) -> None:
        """RateLimitError for HTTP 429."""
        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            side_effect=RateLimitError("Rate limited by https://api.example.com"),
        ):
            retriever = UrlRetriever()
            result = retriever.retrieve(
                source="https://api.example.com/page",
                target_dir=tmp_path,
            )

        assert result.success is False
        assert "Rate limited" in result.error_message
        assert result.metadata["error_type"] == "rate_limit_error"

    def test_content_too_large_error(self, tmp_path: Path) -> None:
        """ContentTooLargeError for oversized responses."""
        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            side_effect=ContentTooLargeError(
                "Content size 100000000 exceeds maximum 20971520"
            ),
        ):
            retriever = UrlRetriever()
            result = retriever.retrieve(
                source="https://example.com/huge",
                target_dir=tmp_path,
            )

        assert result.success is False
        assert "exceeds maximum" in result.error_message
        assert result.metadata["error_type"] == "content_too_large_error"

    def test_title_override_used_on_error(self, tmp_path: Path) -> None:
        """Title override is used when extraction fails."""
        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            side_effect=NetworkError("Connection failed"),
        ):
            retriever = UrlRetriever()
            result = retriever.retrieve(
                source="https://example.com/error",
                target_dir=tmp_path,
                title="My Custom Title",
            )

        assert result.success is False
        assert result.title == "My Custom Title"

    def test_url_used_as_title_on_error_without_override(self, tmp_path: Path) -> None:
        """URL is used as title when extraction fails and no override."""
        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            side_effect=NetworkError("Connection failed"),
        ):
            retriever = UrlRetriever()
            result = retriever.retrieve(
                source="https://example.com/failed",
                target_dir=tmp_path,
            )

        assert result.success is False
        assert result.title == "https://example.com/failed"

    def test_custom_metadata_preserved_on_error(self, tmp_path: Path) -> None:
        """Custom metadata is preserved when extraction fails."""
        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            side_effect=NetworkError("Timeout"),
        ):
            retriever = UrlRetriever()
            result = retriever.retrieve(
                source="https://example.com/error",
                target_dir=tmp_path,
                metadata={"session_id": "sess_456"},
            )

        assert result.success is False
        assert result.metadata["session_id"] == "sess_456"
        assert result.metadata["url"] == "https://example.com/error"


class TestUrlRetrieverConfig:
    """Test suite for URL retriever configuration."""

    def test_default_config_from_settings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default config values come from settings."""
        mock_settings = MagicMock()
        mock_settings.url_fetch_timeout = 45
        mock_settings.url_extraction_retry_with_js = False
        mock_settings.url_extraction_min_content_length = 200
        mock_settings.max_url_response_bytes = 10 * 1024 * 1024

        monkeypatch.setattr(
            "app.services.retrievers.url_retriever.settings", mock_settings
        )

        retriever = UrlRetriever()

        assert retriever._timeout == 45
        assert retriever._retry_with_js is False
        assert retriever._min_content_length == 200

    def test_constructor_overrides_settings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Constructor parameters override settings."""
        mock_settings = MagicMock()
        mock_settings.url_fetch_timeout = 30
        mock_settings.url_extraction_retry_with_js = True
        mock_settings.url_extraction_min_content_length = 100
        mock_settings.max_url_response_bytes = 20 * 1024 * 1024

        monkeypatch.setattr(
            "app.services.retrievers.url_retriever.settings", mock_settings
        )

        retriever = UrlRetriever(
            timeout=60,
            retry_with_js=False,
            min_content_length=500,
        )

        assert retriever._timeout == 60
        assert retriever._retry_with_js is False
        assert retriever._min_content_length == 500

    def test_extraction_config_built_correctly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ExtractionConfig is built with correct values."""
        mock_settings = MagicMock()
        mock_settings.url_fetch_timeout = 30
        mock_settings.url_extraction_retry_with_js = True
        mock_settings.url_extraction_min_content_length = 100
        mock_settings.max_url_response_bytes = 20 * 1024 * 1024

        monkeypatch.setattr(
            "app.services.retrievers.url_retriever.settings", mock_settings
        )

        mock_result = ExtractionResult(
            content="Content",
            title="Title",
            word_count=1,
            extraction_method="trafilatura",
            extraction_time_ms=100.0,
        )

        # Capture the config passed to _extract_async
        captured_config = None

        async def capture_extract(self, url, config):
            nonlocal captured_config
            captured_config = config
            return mock_result

        with patch.object(UrlRetriever, "_extract_async", capture_extract):
            retriever = UrlRetriever(
                timeout=45,
                retry_with_js=False,
                min_content_length=250,
            )
            retriever.retrieve(
                source="https://example.com/test",
                target_dir=tmp_path,
            )

        assert captured_config is not None
        assert captured_config.timeout_seconds == 45
        assert captured_config.retry_with_js is False
        assert captured_config.min_content_length == 250
        assert captured_config.max_content_size_mb == 20  # 20 MB


class TestUrlRetrieverErrorMapping:
    """Test suite for error type mapping."""

    def test_get_error_type_network(self) -> None:
        """NetworkError maps to 'network_error'."""
        retriever = UrlRetriever()
        assert retriever._get_error_type(NetworkError("test")) == "network_error"

    def test_get_error_type_content_type(self) -> None:
        """ContentTypeError maps to 'content_type_error'."""
        retriever = UrlRetriever()
        assert (
            retriever._get_error_type(ContentTypeError("test")) == "content_type_error"
        )

    def test_get_error_type_empty_content(self) -> None:
        """EmptyContentError maps to 'empty_content_error'."""
        retriever = UrlRetriever()
        assert (
            retriever._get_error_type(EmptyContentError("test"))
            == "empty_content_error"
        )

    def test_get_error_type_rate_limit(self) -> None:
        """RateLimitError maps to 'rate_limit_error'."""
        retriever = UrlRetriever()
        assert retriever._get_error_type(RateLimitError("test")) == "rate_limit_error"

    def test_get_error_type_content_too_large(self) -> None:
        """ContentTooLargeError maps to 'content_too_large_error'."""
        retriever = UrlRetriever()
        assert (
            retriever._get_error_type(ContentTooLargeError("test"))
            == "content_too_large_error"
        )

    def test_get_error_type_generic(self) -> None:
        """Generic ExtractionError maps to 'extraction_error'."""
        from app.services.extractors.exceptions import ExtractionError

        retriever = UrlRetriever()
        assert retriever._get_error_type(ExtractionError("test")) == "extraction_error"
