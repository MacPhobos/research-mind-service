"""Tests for extraction pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.extractors.base import ExtractionConfig
from app.services.extractors.exceptions import (
    ContentTooLargeError,
    ContentTypeError,
    EmptyContentError,
    NetworkError,
    RateLimitError,
)
from app.services.extractors.pipeline import ExtractionPipeline


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
<article>
<h1>Test Article</h1>
<p>This is a substantial test article with enough content to pass the minimum
length requirement. It contains multiple sentences and paragraphs to ensure
proper extraction testing works correctly.</p>
<p>Second paragraph adds more content for thorough testing of the extraction
pipeline functionality and error handling.</p>
</article>
</body>
</html>
"""

# Minimal HTML that will fail static extraction but has JS-rendered content
MINIMAL_STATIC_HTML = """
<!DOCTYPE html>
<html>
<head><title>SPA Page</title></head>
<body>
<div id="root"></div>
<script>document.getElementById('root').innerHTML = 'Loading...';</script>
</body>
</html>
"""

JS_RENDERED_HTML = """
<!DOCTYPE html>
<html>
<head><title>SPA Page</title></head>
<body>
<div id="root">
<h1>Dynamic Content</h1>
<p>This content was rendered by JavaScript and contains enough text
to pass the minimum content length requirement for extraction testing.
We need multiple paragraphs to ensure proper validation.</p>
<p>Second paragraph with additional content to meet extraction requirements.</p>
</div>
</body>
</html>
"""


class TestExtractionPipeline:
    """Test suite for ExtractionPipeline class."""

    @pytest.mark.asyncio
    async def test_extract_success(self) -> None:
        """Test successful extraction from a mocked URL."""
        pipeline = ExtractionPipeline()

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = SAMPLE_HTML.encode()
        mock_response.text = SAMPLE_HTML
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_response.raise_for_status = lambda: None

        with patch.object(
            httpx.AsyncClient,
            "get",
            return_value=mock_response,
        ):
            result = await pipeline.extract("https://example.com/test")

        assert result.content
        # Title may be from <title> tag or H1 depending on library behavior
        assert result.title in ("Test Page", "Test Article")
        assert result.extraction_method in ("trafilatura", "newspaper4k")

    @pytest.mark.asyncio
    async def test_extract_network_timeout(self) -> None:
        """Test handling of network timeout."""
        pipeline = ExtractionPipeline()

        with patch.object(
            httpx.AsyncClient,
            "get",
            side_effect=httpx.TimeoutException("Connection timed out"),
        ):
            with pytest.raises(NetworkError) as exc_info:
                await pipeline.extract("https://example.com/slow")

        assert "Timeout" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_network_error(self) -> None:
        """Test handling of network errors."""
        pipeline = ExtractionPipeline()

        with patch.object(
            httpx.AsyncClient,
            "get",
            side_effect=httpx.RequestError("Connection refused"),
        ):
            with pytest.raises(NetworkError) as exc_info:
                await pipeline.extract("https://example.com/unreachable")

        assert "Network error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_rate_limit(self) -> None:
        """Test handling of HTTP 429 rate limiting."""
        pipeline = ExtractionPipeline()

        mock_response = AsyncMock()
        mock_response.status_code = 429

        with patch.object(
            httpx.AsyncClient,
            "get",
            return_value=mock_response,
        ):
            with pytest.raises(RateLimitError) as exc_info:
                await pipeline.extract("https://example.com/rate-limited")

        assert "Rate limited" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_content_too_large(self) -> None:
        """Test handling of oversized content."""
        config = ExtractionConfig(max_content_size_mb=1)  # 1 MB limit
        pipeline = ExtractionPipeline(config)

        # Create response larger than 1 MB
        large_content = "x" * (2 * 1024 * 1024)  # 2 MB
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = large_content.encode()
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = lambda: None

        with patch.object(
            httpx.AsyncClient,
            "get",
            return_value=mock_response,
        ):
            with pytest.raises(ContentTooLargeError) as exc_info:
                await pipeline.extract("https://example.com/large")

        assert "exceeds maximum" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_extract_unsupported_content_type(self) -> None:
        """Test handling of unsupported content types."""
        pipeline = ExtractionPipeline()

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = b"PDF content"
        mock_response.text = "PDF content"
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = lambda: None

        with patch.object(
            httpx.AsyncClient,
            "get",
            return_value=mock_response,
        ):
            with pytest.raises(ContentTypeError) as exc_info:
                await pipeline.extract("https://example.com/document.pdf")

        assert "Unsupported content type" in str(exc_info.value)


class TestExtractionPipelineContentTypeDetection:
    """Test suite for content type detection."""

    def test_is_html_text_html(self) -> None:
        """Test detection of text/html content type."""
        pipeline = ExtractionPipeline()
        assert pipeline._is_html("text/html") is True
        assert pipeline._is_html("text/html; charset=utf-8") is True

    def test_is_html_xhtml(self) -> None:
        """Test detection of XHTML content type."""
        pipeline = ExtractionPipeline()
        assert pipeline._is_html("application/xhtml+xml") is True
        assert pipeline._is_html("application/xhtml+xml; charset=utf-8") is True

    def test_is_html_case_insensitive(self) -> None:
        """Test that content type detection is case insensitive."""
        pipeline = ExtractionPipeline()
        assert pipeline._is_html("TEXT/HTML") is True
        assert pipeline._is_html("Text/Html") is True

    def test_is_html_non_html_types(self) -> None:
        """Test rejection of non-HTML content types."""
        pipeline = ExtractionPipeline()
        assert pipeline._is_html("application/pdf") is False
        assert pipeline._is_html("application/json") is False
        assert pipeline._is_html("text/plain") is False
        assert pipeline._is_html("image/png") is False


class TestExtractionPipelineConfig:
    """Test suite for pipeline configuration."""

    def test_default_config(self) -> None:
        """Test that default config is applied."""
        pipeline = ExtractionPipeline()

        assert pipeline.config.timeout_seconds == 30
        assert pipeline.config.min_content_length == 100
        assert pipeline.config.max_content_size_mb == 50

    def test_custom_config(self) -> None:
        """Test that custom config is respected."""
        config = ExtractionConfig(
            timeout_seconds=60,
            min_content_length=200,
            max_content_size_mb=100,
        )
        pipeline = ExtractionPipeline(config)

        assert pipeline.config.timeout_seconds == 60
        assert pipeline.config.min_content_length == 200
        assert pipeline.config.max_content_size_mb == 100

    def test_html_extractor_uses_same_config(self) -> None:
        """Test that HTML extractor receives the same config."""
        config = ExtractionConfig(min_content_length=500)
        pipeline = ExtractionPipeline(config)

        assert pipeline.html_extractor.config.min_content_length == 500


class TestExtractionPipelineJSRetry:
    """Test suite for JavaScript rendering fallback."""

    def test_js_extractor_lazy_loaded(self) -> None:
        """Test that JS extractor is not loaded until accessed."""
        pipeline = ExtractionPipeline()

        # Should not be initialized yet
        assert pipeline._js_extractor is None

    def test_js_extractor_property_creates_instance(self) -> None:
        """Test that js_extractor property creates instance on first access."""
        pipeline = ExtractionPipeline()

        # Access the property
        extractor = pipeline.js_extractor

        # Should now be initialized
        assert extractor is not None
        assert pipeline._js_extractor is extractor

    def test_js_extractor_uses_same_config(self) -> None:
        """Test that JS extractor receives the same config."""
        config = ExtractionConfig(
            timeout_seconds=45,
            playwright_headless=False,
        )
        pipeline = ExtractionPipeline(config)

        assert pipeline.js_extractor.config.timeout_seconds == 45
        assert pipeline.js_extractor.config.playwright_headless is False

    @pytest.mark.asyncio
    async def test_fallback_to_js_when_static_fails(self) -> None:
        """Test that pipeline falls back to JS rendering on EmptyContentError."""
        config = ExtractionConfig(retry_with_js=True)
        pipeline = ExtractionPipeline(config)

        # Mock httpx response with minimal HTML
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = MINIMAL_STATIC_HTML.encode()
        mock_response.text = MINIMAL_STATIC_HTML
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = lambda: None

        # Mock JS extractor to return rendered HTML
        mock_js_extractor = AsyncMock()
        mock_js_extractor.render.return_value = JS_RENDERED_HTML

        with patch.object(
            httpx.AsyncClient,
            "get",
            return_value=mock_response,
        ):
            # Replace JS extractor with mock
            pipeline._js_extractor = mock_js_extractor

            result = await pipeline.extract("https://example.com/spa")

        # Should have used JS rendering
        mock_js_extractor.render.assert_called_once_with("https://example.com/spa")
        assert "playwright+" in result.extraction_method

    @pytest.mark.asyncio
    async def test_no_js_fallback_when_disabled(self) -> None:
        """Test that JS fallback is skipped when retry_with_js=False."""
        config = ExtractionConfig(retry_with_js=False)
        pipeline = ExtractionPipeline(config)

        # Mock httpx response with minimal HTML that will fail extraction
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = MINIMAL_STATIC_HTML.encode()
        mock_response.text = MINIMAL_STATIC_HTML
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = lambda: None

        with patch.object(
            httpx.AsyncClient,
            "get",
            return_value=mock_response,
        ):
            with pytest.raises(EmptyContentError):
                await pipeline.extract("https://example.com/spa")

    @pytest.mark.asyncio
    async def test_extraction_method_prefix_added(self) -> None:
        """Test that 'playwright+' prefix is added to extraction method."""
        config = ExtractionConfig(retry_with_js=True)
        pipeline = ExtractionPipeline(config)

        # Mock httpx response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = MINIMAL_STATIC_HTML.encode()
        mock_response.text = MINIMAL_STATIC_HTML
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = lambda: None

        # Mock JS extractor
        mock_js_extractor = AsyncMock()
        mock_js_extractor.render.return_value = JS_RENDERED_HTML

        with patch.object(
            httpx.AsyncClient,
            "get",
            return_value=mock_response,
        ):
            pipeline._js_extractor = mock_js_extractor
            result = await pipeline.extract("https://example.com/spa")

        # Should have playwright+ prefix
        assert result.extraction_method.startswith("playwright+")
        assert result.extraction_method in (
            "playwright+trafilatura",
            "playwright+newspaper4k",
        )

    @pytest.mark.asyncio
    async def test_static_extraction_used_when_successful(self) -> None:
        """Test that static extraction is used when it succeeds."""
        pipeline = ExtractionPipeline()

        # Mock httpx response with good HTML
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.content = SAMPLE_HTML.encode()
        mock_response.text = SAMPLE_HTML
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = lambda: None

        with patch.object(
            httpx.AsyncClient,
            "get",
            return_value=mock_response,
        ):
            result = await pipeline.extract("https://example.com/article")

        # Should NOT have playwright prefix (static extraction succeeded)
        assert not result.extraction_method.startswith("playwright+")
        assert result.extraction_method in ("trafilatura", "newspaper4k")


class TestExtractionPipelineCleanup:
    """Test suite for pipeline resource cleanup."""

    @pytest.mark.asyncio
    async def test_close_releases_js_extractor(self) -> None:
        """Test that close() releases JS extractor resources."""
        pipeline = ExtractionPipeline()

        # Create mock JS extractor
        mock_js_extractor = AsyncMock()
        pipeline._js_extractor = mock_js_extractor

        await pipeline.close()

        mock_js_extractor.close.assert_called_once()
        assert pipeline._js_extractor is None

    @pytest.mark.asyncio
    async def test_close_safe_when_js_not_initialized(self) -> None:
        """Test that close() is safe when JS extractor was never used."""
        pipeline = ExtractionPipeline()

        # Should not raise
        await pipeline.close()

        assert pipeline._js_extractor is None

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(self) -> None:
        """Test that context manager ensures cleanup."""
        mock_js_extractor = AsyncMock()

        async with ExtractionPipeline() as pipeline:
            pipeline._js_extractor = mock_js_extractor

        mock_js_extractor.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_cleanup_on_exception(self) -> None:
        """Test that context manager ensures cleanup even on exception."""
        mock_js_extractor = AsyncMock()

        with pytest.raises(ValueError):
            async with ExtractionPipeline() as pipeline:
                pipeline._js_extractor = mock_js_extractor
                raise ValueError("Test exception")

        mock_js_extractor.close.assert_called_once()
