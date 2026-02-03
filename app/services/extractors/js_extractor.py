"""JavaScript rendering extractor using Playwright.

This module provides JSExtractor for rendering JavaScript-heavy pages
(SPAs, React sites, lazy-loaded content) using Playwright's async API.

Usage:
    extractor = JSExtractor(config)
    html = await extractor.render("https://example.com")
    await extractor.close()  # Clean up resources

Note: Playwright browsers must be installed separately:
    uv run playwright install chromium
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.services.extractors.base import ExtractionConfig
from app.services.extractors.exceptions import NetworkError

if TYPE_CHECKING:
    from playwright.async_api import Browser, Playwright

logger = logging.getLogger(__name__)


class JSExtractor:
    """Extract content by rendering JavaScript with Playwright.

    Uses lazy browser initialization to avoid overhead when JS rendering
    is not needed. The browser is only started on first render() call.

    Attributes:
        config: Extraction configuration (timeout, headless mode, etc.)
    """

    def __init__(self, config: ExtractionConfig | None = None) -> None:
        """Initialize JSExtractor with configuration.

        Args:
            config: Extraction configuration. If None, defaults are used.
        """
        self.config = config or ExtractionConfig()
        self._browser: Browser | None = None
        self._playwright: Playwright | None = None

    async def _ensure_browser(self) -> Browser:
        """Ensure browser is initialized (lazy initialization).

        Returns:
            Initialized Playwright Browser instance.

        Raises:
            NetworkError: If browser fails to launch.
        """
        if self._browser is None:
            try:
                # Import here to avoid loading Playwright until needed
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=self.config.playwright_headless,
                )
                logger.debug(
                    "Playwright browser launched (headless=%s)",
                    self.config.playwright_headless,
                )
            except Exception as e:
                logger.error("Failed to launch Playwright browser: %s", e)
                raise NetworkError(f"Failed to launch browser: {e}") from e

        return self._browser

    async def render(self, url: str, wait_time_ms: int = 2000) -> str:
        """Render URL with JavaScript and return HTML.

        Navigates to the URL, waits for network idle, then waits additional
        time for JavaScript execution before returning the rendered HTML.

        Args:
            url: URL to render.
            wait_time_ms: Additional time to wait for JS execution after
                network idle (default: 2000ms).

        Returns:
            Rendered HTML content as string.

        Raises:
            NetworkError: If page fails to load or rendering fails.
        """
        browser = await self._ensure_browser()
        page = None

        try:
            page = await browser.new_page()

            # Set reasonable timeout based on config
            page.set_default_timeout(self.config.timeout_seconds * 1000)

            # Navigate and wait for network idle
            logger.debug("Rendering URL with Playwright: %s", url)
            response = await page.goto(url, wait_until="networkidle")

            if response is None or response.status >= 400:
                status = response.status if response else "unknown"
                raise NetworkError(f"Failed to load {url}: HTTP {status}")

            # Wait for additional JS execution
            await asyncio.sleep(wait_time_ms / 1000)

            # Get rendered HTML
            html = await page.content()
            logger.debug(
                "Playwright rendered %d chars from %s",
                len(html),
                url,
            )
            return html

        except NetworkError:
            # Re-raise our own exceptions as-is
            raise
        except Exception as e:
            logger.warning("Playwright rendering failed for %s: %s", url, e)
            raise NetworkError(f"Playwright rendering failed for {url}: {e}") from e

        finally:
            if page:
                await page.close()

    async def close(self) -> None:
        """Close browser and cleanup resources.

        Should be called when the extractor is no longer needed to
        release browser resources. Safe to call multiple times.
        """
        if self._browser:
            try:
                await self._browser.close()
                logger.debug("Playwright browser closed")
            except Exception as e:
                logger.warning("Error closing browser: %s", e)
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
                logger.debug("Playwright stopped")
            except Exception as e:
                logger.warning("Error stopping Playwright: %s", e)
            self._playwright = None

    async def __aenter__(self) -> JSExtractor:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - ensures cleanup."""
        await self.close()
