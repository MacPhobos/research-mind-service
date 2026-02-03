"""Tests for JavaScript rendering extractor using Playwright.

These tests mock Playwright to avoid requiring actual browser binaries in CI.
For integration tests with real browsers, see test_js_extractor_integration.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.extractors.base import ExtractionConfig
from app.services.extractors.exceptions import NetworkError
from app.services.extractors.js_extractor import JSExtractor


SAMPLE_RENDERED_HTML = """
<!DOCTYPE html>
<html>
<head><title>JS Rendered Page</title></head>
<body>
<div id="app">
<h1>Dynamic Content</h1>
<p>This content was rendered by JavaScript and contains enough text
to pass the minimum content length requirement for extraction testing.
We need multiple paragraphs to ensure proper validation.</p>
<p>Second paragraph with additional content to meet extraction requirements
and test the JavaScript rendering pipeline functionality.</p>
</div>
</body>
</html>
"""


class TestJSExtractorInstantiation:
    """Test suite for JSExtractor instantiation."""

    def test_instantiate_with_default_config(self) -> None:
        """Test that JSExtractor can be instantiated with default config."""
        extractor = JSExtractor()

        assert extractor.config is not None
        assert extractor.config.timeout_seconds == 30
        assert extractor.config.playwright_headless is True
        assert extractor._browser is None
        assert extractor._playwright is None

    def test_instantiate_with_custom_config(self) -> None:
        """Test that JSExtractor respects custom configuration."""
        config = ExtractionConfig(
            timeout_seconds=60,
            playwright_headless=False,
        )
        extractor = JSExtractor(config)

        assert extractor.config.timeout_seconds == 60
        assert extractor.config.playwright_headless is False

    def test_browser_not_started_on_init(self) -> None:
        """Test that browser is not started during initialization (lazy loading)."""
        extractor = JSExtractor()

        assert extractor._browser is None
        assert extractor._playwright is None


class TestJSExtractorLazyInitialization:
    """Test suite for lazy browser initialization."""

    @pytest.mark.asyncio
    async def test_browser_initialized_on_first_render(self) -> None:
        """Test that browser is lazily initialized on first render call."""
        extractor = JSExtractor()

        # Create mock browser and page
        mock_page = AsyncMock()
        mock_page.content.return_value = SAMPLE_RENDERED_HTML
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        # async_playwright() returns a context manager with async start()
        mock_context_manager = AsyncMock()
        mock_context_manager.start.return_value = mock_playwright

        with patch(
            "playwright.async_api.async_playwright",
            return_value=mock_context_manager,
        ):
            html = await extractor.render("https://example.com")

        assert html == SAMPLE_RENDERED_HTML
        mock_playwright.chromium.launch.assert_called_once()

    @pytest.mark.asyncio
    async def test_browser_reused_on_subsequent_renders(self) -> None:
        """Test that browser is reused for multiple render calls."""
        extractor = JSExtractor()

        # Create mock browser and page
        mock_page = AsyncMock()
        mock_page.content.return_value = SAMPLE_RENDERED_HTML
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        # async_playwright() returns a context manager with async start()
        mock_context_manager = AsyncMock()
        mock_context_manager.start.return_value = mock_playwright

        with patch(
            "playwright.async_api.async_playwright",
            return_value=mock_context_manager,
        ):
            # Render twice
            await extractor.render("https://example.com/page1")
            await extractor.render("https://example.com/page2")

        # Browser should only be launched once
        mock_playwright.chromium.launch.assert_called_once()
        # But two pages should be created
        assert mock_browser.new_page.call_count == 2


class TestJSExtractorRender:
    """Test suite for render functionality."""

    @pytest.mark.asyncio
    async def test_render_returns_html(self) -> None:
        """Test that render returns HTML content from the page."""
        extractor = JSExtractor()

        mock_page = AsyncMock()
        mock_page.content.return_value = SAMPLE_RENDERED_HTML
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        # async_playwright() returns a context manager with async start()
        mock_context_manager = AsyncMock()
        mock_context_manager.start.return_value = mock_playwright

        with patch(
            "playwright.async_api.async_playwright",
            return_value=mock_context_manager,
        ):
            html = await extractor.render("https://example.com/spa")

        assert "Dynamic Content" in html
        assert "<title>JS Rendered Page</title>" in html

    @pytest.mark.asyncio
    async def test_render_raises_on_http_error(self) -> None:
        """Test that render raises NetworkError on HTTP 4xx/5xx."""
        extractor = JSExtractor()

        mock_page = AsyncMock()
        mock_response = MagicMock()
        mock_response.status = 404
        mock_page.goto.return_value = mock_response

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        # async_playwright() returns a context manager with async start()
        mock_context_manager = AsyncMock()
        mock_context_manager.start.return_value = mock_playwright

        with patch(
            "playwright.async_api.async_playwright",
            return_value=mock_context_manager,
        ):
            with pytest.raises(NetworkError) as exc_info:
                await extractor.render("https://example.com/not-found")

        assert "HTTP 404" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_render_raises_on_navigation_failure(self) -> None:
        """Test that render raises NetworkError when page fails to load."""
        extractor = JSExtractor()

        mock_page = AsyncMock()
        mock_page.goto.return_value = None  # Indicates navigation failure

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        # async_playwright() returns a context manager with async start()
        mock_context_manager = AsyncMock()
        mock_context_manager.start.return_value = mock_playwright

        with patch(
            "playwright.async_api.async_playwright",
            return_value=mock_context_manager,
        ):
            with pytest.raises(NetworkError) as exc_info:
                await extractor.render("https://example.com/failing")

        assert "Failed to load" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_render_closes_page_after_success(self) -> None:
        """Test that page is closed after successful render."""
        extractor = JSExtractor()

        mock_page = AsyncMock()
        mock_page.content.return_value = SAMPLE_RENDERED_HTML
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        # async_playwright() returns a context manager with async start()
        mock_context_manager = AsyncMock()
        mock_context_manager.start.return_value = mock_playwright

        with patch(
            "playwright.async_api.async_playwright",
            return_value=mock_context_manager,
        ):
            await extractor.render("https://example.com")

        mock_page.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_render_closes_page_on_error(self) -> None:
        """Test that page is closed even when rendering fails."""
        extractor = JSExtractor()

        mock_page = AsyncMock()
        mock_page.goto.side_effect = Exception("Navigation error")

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        # async_playwright() returns a context manager with async start()
        mock_context_manager = AsyncMock()
        mock_context_manager.start.return_value = mock_playwright

        with patch(
            "playwright.async_api.async_playwright",
            return_value=mock_context_manager,
        ):
            with pytest.raises(NetworkError):
                await extractor.render("https://example.com/error")

        mock_page.close.assert_called_once()


class TestJSExtractorCleanup:
    """Test suite for resource cleanup."""

    @pytest.mark.asyncio
    async def test_close_releases_resources(self) -> None:
        """Test that close() releases browser resources."""
        extractor = JSExtractor()

        # Set up mocked browser state
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()

        extractor._browser = mock_browser
        extractor._playwright = mock_playwright

        await extractor.close()

        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()
        assert extractor._browser is None
        assert extractor._playwright is None

    @pytest.mark.asyncio
    async def test_close_safe_when_not_initialized(self) -> None:
        """Test that close() is safe to call when browser was never started."""
        extractor = JSExtractor()

        # Should not raise
        await extractor.close()

        assert extractor._browser is None
        assert extractor._playwright is None

    @pytest.mark.asyncio
    async def test_close_safe_to_call_multiple_times(self) -> None:
        """Test that close() can be called multiple times safely."""
        extractor = JSExtractor()

        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()

        extractor._browser = mock_browser
        extractor._playwright = mock_playwright

        # Call close multiple times
        await extractor.close()
        await extractor.close()
        await extractor.close()

        # Should only call close once
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()


class TestJSExtractorContextManager:
    """Test suite for async context manager support."""

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(self) -> None:
        """Test that context manager ensures cleanup on exit."""
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()

        async with JSExtractor() as extractor:
            # Simulate browser initialization
            extractor._browser = mock_browser
            extractor._playwright = mock_playwright

        # Should be cleaned up after context exit
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_cleanup_on_exception(self) -> None:
        """Test that context manager ensures cleanup even on exception."""
        mock_browser = AsyncMock()
        mock_playwright = AsyncMock()

        with pytest.raises(ValueError):
            async with JSExtractor() as extractor:
                extractor._browser = mock_browser
                extractor._playwright = mock_playwright
                raise ValueError("Test exception")

        # Should still be cleaned up
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()


class TestJSExtractorConfig:
    """Test suite for configuration handling."""

    @pytest.mark.asyncio
    async def test_headless_config_passed_to_browser(self) -> None:
        """Test that headless config is passed to browser launch."""
        config = ExtractionConfig(playwright_headless=False)
        extractor = JSExtractor(config)

        mock_page = AsyncMock()
        mock_page.content.return_value = SAMPLE_RENDERED_HTML
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        # async_playwright() returns a context manager with async start()
        mock_context_manager = AsyncMock()
        mock_context_manager.start.return_value = mock_playwright

        with patch(
            "playwright.async_api.async_playwright",
            return_value=mock_context_manager,
        ):
            await extractor.render("https://example.com")

        mock_playwright.chromium.launch.assert_called_once_with(headless=False)

    @pytest.mark.asyncio
    async def test_timeout_config_applied_to_page(self) -> None:
        """Test that timeout config is applied to page."""
        config = ExtractionConfig(timeout_seconds=45)
        extractor = JSExtractor(config)

        mock_page = AsyncMock()
        mock_page.content.return_value = SAMPLE_RENDERED_HTML
        mock_response = MagicMock()
        mock_response.status = 200
        mock_page.goto.return_value = mock_response

        mock_browser = AsyncMock()
        mock_browser.new_page.return_value = mock_page

        mock_playwright = AsyncMock()
        mock_playwright.chromium.launch.return_value = mock_browser

        # async_playwright() returns a context manager with async start()
        mock_context_manager = AsyncMock()
        mock_context_manager.start.return_value = mock_playwright

        with patch(
            "playwright.async_api.async_playwright",
            return_value=mock_context_manager,
        ):
            await extractor.render("https://example.com")

        # 45 seconds * 1000 = 45000ms
        mock_page.set_default_timeout.assert_called_once_with(45000)
