"""Base classes for content extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ExtractionConfig:
    """Configuration for extraction pipeline."""

    timeout_seconds: int = 30
    max_retries: int = 3
    max_content_size_mb: int = 50
    min_content_length: int = 100  # Minimum chars for valid extraction
    retry_with_js: bool = True
    playwright_headless: bool = True
    user_agent: str = "research-mind/0.1 (content-extraction)"


@dataclass
class ExtractionResult:
    """Result of content extraction operation."""

    content: str  # Extracted markdown content
    title: str  # Document title
    word_count: int = 0  # Auto-calculated
    extraction_method: str = ""  # Which extractor was used
    extraction_time_ms: float = 0.0  # Processing time
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.word_count == 0:
            self.word_count = len(self.content.split())


class ContentExtractor(Protocol):
    """Protocol defining interface for content extractors."""

    def extract(self, html: str, url: str) -> ExtractionResult:
        """Extract content from HTML string.

        Args:
            html: Raw HTML content
            url: Source URL (for context, relative link resolution)

        Returns:
            ExtractionResult with extracted content

        Raises:
            EmptyContentError: If extraction produces insufficient content
        """
        ...
