"""Retriever for URL content using extraction pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.services.extractors import ExtractionConfig, ExtractionPipeline
from app.services.extractors.exceptions import (
    ContentTooLargeError,
    ContentTypeError,
    EmptyContentError,
    ExtractionError,
    NetworkError,
    RateLimitError,
)
from app.services.retrievers.base import RetrievalResult

logger = logging.getLogger(__name__)


class UrlRetriever:
    """Fetch URL content, extract markdown, store in sandbox.

    Uses ExtractionPipeline with trafilatura/newspaper4k for static HTML
    extraction, with optional Playwright fallback for JavaScript-rendered pages.
    """

    def __init__(
        self,
        timeout: int | None = None,
        retry_with_js: bool | None = None,
        min_content_length: int | None = None,
    ) -> None:
        """Initialize URL retriever.

        Args:
            timeout: HTTP timeout in seconds (default: from settings)
            retry_with_js: Whether to retry with Playwright if static fails
                          (default: from settings)
            min_content_length: Minimum chars for valid extraction
                               (default: from settings)
        """
        self._timeout = timeout if timeout is not None else settings.url_fetch_timeout
        self._retry_with_js = (
            retry_with_js
            if retry_with_js is not None
            else settings.url_extraction_retry_with_js
        )
        self._min_content_length = (
            min_content_length
            if min_content_length is not None
            else settings.url_extraction_min_content_length
        )

    def retrieve(
        self,
        *,
        source: str,
        target_dir: Path,
        title: str | None = None,
        metadata: dict | None = None,
    ) -> RetrievalResult:
        """Retrieve and extract content from URL.

        Args:
            source: URL to fetch and extract
            target_dir: Directory to store extracted content
            title: Optional title override (uses extracted title if not provided)
            metadata: Additional metadata to include

        Returns:
            RetrievalResult with success status and extraction metadata
        """
        url = source

        # Build extraction config from settings
        config = ExtractionConfig(
            timeout_seconds=self._timeout,
            retry_with_js=self._retry_with_js,
            min_content_length=self._min_content_length,
            max_content_size_mb=settings.max_url_response_bytes // (1024 * 1024),
        )

        # Run async extraction in sync context
        try:
            result = asyncio.run(self._extract_async(url, config))
        except ExtractionError as exc:
            return self._build_error_result(
                url=url,
                target_dir=target_dir,
                title=title,
                metadata=metadata,
                error=exc,
            )

        # Use extracted title if no override provided
        resolved_title = title or result.title or url

        # Write extracted markdown content
        content_file = target_dir / "content.md"
        content_bytes = result.content.encode("utf-8")
        content_file.write_bytes(content_bytes)

        # Build metadata
        retrieved_at = datetime.now(timezone.utc).isoformat()
        meta = {
            "url": url,
            "title": resolved_title,
            "word_count": result.word_count,
            "extraction_method": result.extraction_method,
            "extraction_time_ms": result.extraction_time_ms,
            "retrieved_at": retrieved_at,
            **(metadata or {}),
        }

        # Include warnings if any
        if result.warnings:
            meta["warnings"] = result.warnings

        # Write metadata
        meta_file = target_dir / "metadata.json"
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        return RetrievalResult(
            success=True,
            storage_path=str(target_dir.name),
            size_bytes=len(content_bytes),
            mime_type="text/markdown",
            title=resolved_title,
            metadata=meta,
        )

    async def _extract_async(
        self,
        url: str,
        config: ExtractionConfig,
    ):
        """Run extraction pipeline asynchronously.

        Args:
            url: URL to extract from
            config: Extraction configuration

        Returns:
            ExtractionResult from pipeline

        Raises:
            ExtractionError: If extraction fails
        """
        async with ExtractionPipeline(config) as pipeline:
            return await pipeline.extract(url)

    def _build_error_result(
        self,
        *,
        url: str,
        target_dir: Path,
        title: str | None,
        metadata: dict | None,
        error: ExtractionError,
    ) -> RetrievalResult:
        """Build RetrievalResult for extraction errors.

        Args:
            url: Source URL
            target_dir: Target directory
            title: Optional title
            metadata: Additional metadata
            error: The extraction error

        Returns:
            RetrievalResult with success=False
        """
        # Map exception type to error_type string
        error_type = self._get_error_type(error)
        error_message = str(error)

        logger.warning(
            "URL extraction failed: %s [%s] - %s",
            url,
            error_type,
            error_message,
        )

        return RetrievalResult(
            success=False,
            storage_path=str(target_dir.name),
            size_bytes=0,
            mime_type=None,
            title=title or url,
            metadata={
                "url": url,
                "error_type": error_type,
                **(metadata or {}),
            },
            error_message=error_message,
        )

    def _get_error_type(self, error: ExtractionError) -> str:
        """Map exception to error type string.

        Args:
            error: Extraction error

        Returns:
            String identifier for error type
        """
        if isinstance(error, NetworkError):
            return "network_error"
        if isinstance(error, ContentTypeError):
            return "content_type_error"
        if isinstance(error, EmptyContentError):
            return "empty_content_error"
        if isinstance(error, RateLimitError):
            return "rate_limit_error"
        if isinstance(error, ContentTooLargeError):
            return "content_too_large_error"
        return "extraction_error"
