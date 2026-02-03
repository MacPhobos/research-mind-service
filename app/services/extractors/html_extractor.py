"""HTML content extractor using trafilatura with newspaper4k fallback."""

from __future__ import annotations

import logging
import re
import time

import trafilatura
from newspaper import Article

from app.services.extractors.base import ExtractionConfig, ExtractionResult
from app.services.extractors.exceptions import EmptyContentError

logger = logging.getLogger(__name__)


class HTMLExtractor:
    """Extract readable content from HTML using multi-tier approach."""

    def __init__(self, config: ExtractionConfig | None = None) -> None:
        self.config = config or ExtractionConfig()

    def extract(self, html: str, url: str) -> ExtractionResult:
        """Extract content from HTML, trying trafilatura then newspaper4k.

        Args:
            html: Raw HTML content to extract from
            url: Source URL for context and link resolution

        Returns:
            ExtractionResult with extracted markdown content

        Raises:
            EmptyContentError: If extraction produces insufficient content
        """
        start_time = time.perf_counter()
        warnings: list[str] = []

        # Try trafilatura first (primary)
        content = self._try_trafilatura(html, url)
        method = "trafilatura"

        # Fallback to newspaper4k if trafilatura fails or returns insufficient content
        if not content or len(content) < self.config.min_content_length:
            if content:
                warnings.append(
                    f"trafilatura returned only {len(content)} chars, trying newspaper4k"
                )
            content = self._try_newspaper4k(html, url)
            method = "newspaper4k"

        # Validate minimum content length
        if not content or len(content) < self.config.min_content_length:
            raise EmptyContentError(
                f"Extraction produced insufficient content: {len(content or '')} chars "
                f"(minimum: {self.config.min_content_length})"
            )

        # Extract title
        title = self._extract_title(html, url)

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return ExtractionResult(
            content=content,
            title=title,
            extraction_method=method,
            extraction_time_ms=elapsed_ms,
            warnings=warnings,
        )

    def _try_trafilatura(self, html: str, url: str) -> str | None:
        """Extract using trafilatura with markdown output."""
        try:
            result = trafilatura.extract(
                html,
                url=url,
                output_format="markdown",
                include_links=True,
                include_images=False,
                include_tables=True,
                favor_precision=True,
            )
            return result
        except Exception as e:
            logger.warning("trafilatura extraction failed: %s", e)
            return None

    def _try_newspaper4k(self, html: str, url: str) -> str | None:
        """Extract using newspaper4k as fallback."""
        try:
            article = Article(url)
            article.set_html(html)
            article.parse()
            return article.text
        except Exception as e:
            logger.warning("newspaper4k extraction failed: %s", e)
            return None

    def _extract_title(self, html: str, url: str) -> str:
        """Extract document title from HTML."""
        try:
            # Try trafilatura metadata
            metadata = trafilatura.extract_metadata(html)
            if metadata and metadata.title:
                return metadata.title
        except Exception:
            pass

        # Fallback: parse <title> tag
        match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        return url  # Last resort: use URL as title
