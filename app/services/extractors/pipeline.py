"""Extraction pipeline orchestrating content extraction from URLs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from app.services.extractors.base import ExtractionConfig, ExtractionResult
from app.services.extractors.exceptions import (
    ContentTooLargeError,
    ContentTypeError,
    EmptyContentError,
    NetworkError,
    RateLimitError,
)
from app.services.extractors.html_extractor import HTMLExtractor

if TYPE_CHECKING:
    from app.services.extractors.js_extractor import JSExtractor

logger = logging.getLogger(__name__)


class ExtractionPipeline:
    """Orchestrates content extraction from URLs.

    Uses a multi-tier approach:
    1. Static HTML extraction (trafilatura + newspaper4k)
    2. JavaScript rendering via Playwright (if static fails and retry_with_js enabled)

    The JSExtractor is lazy-loaded to avoid Playwright import overhead
    when JS rendering is not needed.
    """

    def __init__(self, config: ExtractionConfig | None = None) -> None:
        self.config = config or ExtractionConfig()
        self.html_extractor = HTMLExtractor(self.config)
        self._js_extractor: JSExtractor | None = None

    @property
    def js_extractor(self) -> JSExtractor:
        """Lazy-load JS extractor to avoid Playwright import overhead.

        Returns:
            JSExtractor instance (created on first access).
        """
        if self._js_extractor is None:
            from app.services.extractors.js_extractor import JSExtractor

            self._js_extractor = JSExtractor(self.config)
        return self._js_extractor

    async def extract(self, url: str) -> ExtractionResult:
        """Extract content from URL with automatic fallback strategies.

        First attempts static HTML extraction. If that fails with
        EmptyContentError and retry_with_js is enabled, falls back to
        JavaScript rendering via Playwright.

        Args:
            url: URL to fetch and extract content from

        Returns:
            ExtractionResult with extracted markdown content

        Raises:
            NetworkError: If URL fetch fails
            ContentTypeError: If content type is not HTML
            ContentTooLargeError: If content exceeds size limits
            RateLimitError: If HTTP 429 is received
            EmptyContentError: If extraction produces insufficient content
        """
        # Fetch content
        html, content_type = await self._fetch_url(url)

        # Validate content type
        if not self._is_html(content_type):
            raise ContentTypeError(f"Unsupported content type: {content_type}")

        # Try static extraction first
        try:
            return self.html_extractor.extract(html, url)
        except EmptyContentError as e:
            if not self.config.retry_with_js:
                raise
            logger.info("Static extraction failed, trying JS rendering: %s", e)

        # Fallback to JavaScript rendering
        return await self._extract_with_js(url)

    async def _fetch_url(self, url: str) -> tuple[str, str]:
        """Fetch URL content with error handling.

        Args:
            url: URL to fetch

        Returns:
            Tuple of (html_content, content_type)

        Raises:
            NetworkError: If request fails
            RateLimitError: If HTTP 429 is received
            ContentTooLargeError: If content exceeds size limits
        """
        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": self.config.user_agent},
                )

                # Handle rate limiting
                if response.status_code == 429:
                    raise RateLimitError(f"Rate limited by {url}")

                response.raise_for_status()

                # Check content size
                content_length = len(response.content)
                max_bytes = self.config.max_content_size_mb * 1024 * 1024
                if content_length > max_bytes:
                    raise ContentTooLargeError(
                        f"Content size {content_length} exceeds maximum {max_bytes}"
                    )

                content_type = response.headers.get("content-type", "")
                return response.text, content_type

        except httpx.TimeoutException as e:
            raise NetworkError(f"Timeout fetching {url}: {e}") from e
        except httpx.RequestError as e:
            raise NetworkError(f"Network error fetching {url}: {e}") from e
        except httpx.HTTPStatusError as e:
            raise NetworkError(
                f"HTTP {e.response.status_code} from {url}: {e.response.reason_phrase}"
            ) from e

    def _is_html(self, content_type: str) -> bool:
        """Check if content type is HTML.

        Args:
            content_type: Content-Type header value

        Returns:
            True if content type indicates HTML
        """
        ct_lower = content_type.lower()
        return "text/html" in ct_lower or "application/xhtml" in ct_lower

    async def _extract_with_js(self, url: str) -> ExtractionResult:
        """Extract content using JavaScript rendering.

        Renders the page with Playwright, then extracts content from
        the rendered HTML using the standard HTML extractor.

        Args:
            url: URL to render and extract content from

        Returns:
            ExtractionResult with "playwright+" prefix on extraction_method

        Raises:
            NetworkError: If page fails to load
            EmptyContentError: If extraction produces insufficient content
        """
        logger.info("Attempting JS rendering for %s", url)
        html = await self.js_extractor.render(url)
        result = self.html_extractor.extract(html, url)

        # Update extraction method to indicate Playwright was used
        result.extraction_method = f"playwright+{result.extraction_method}"
        return result

    async def close(self) -> None:
        """Close resources and cleanup.

        Should be called when the pipeline is no longer needed to
        release Playwright browser resources (if any were created).
        """
        if self._js_extractor is not None:
            await self._js_extractor.close()
            self._js_extractor = None

    async def __aenter__(self) -> ExtractionPipeline:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - ensures cleanup."""
        await self.close()
