"""Content extraction module for URL content retrieval.

This module provides a multi-tier content extraction pipeline:
1. trafilatura (primary) - Fast, accurate article extraction
2. newspaper4k (fallback) - Alternative extraction for complex pages
3. Playwright (JS rendering) - For SPAs and JavaScript-heavy sites

The ExtractionPipeline orchestrates these extractors with automatic
fallback when static extraction fails.

Usage:
    from app.services.extractors import ExtractionPipeline

    async with ExtractionPipeline() as pipeline:
        result = await pipeline.extract("https://example.com")
        print(result.content)

Note: Playwright browsers must be installed separately:
    uv run playwright install chromium
"""

from app.services.extractors.base import (
    ContentExtractor,
    ExtractionConfig,
    ExtractionResult,
)
from app.services.extractors.exceptions import (
    ContentTooLargeError,
    ContentTypeError,
    EmptyContentError,
    ExtractionError,
    NetworkError,
    RateLimitError,
)
from app.services.extractors.html_extractor import HTMLExtractor
from app.services.extractors.js_extractor import JSExtractor
from app.services.extractors.pipeline import ExtractionPipeline

__all__ = [
    # Base classes
    "ContentExtractor",
    "ExtractionConfig",
    "ExtractionResult",
    # Extractors
    "HTMLExtractor",
    "JSExtractor",
    "ExtractionPipeline",
    # Exceptions
    "ExtractionError",
    "NetworkError",
    "ContentTypeError",
    "EmptyContentError",
    "RateLimitError",
    "ContentTooLargeError",
]
