"""Base protocol and types for document content extractors."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class ExtractionResult:
    """Result of document content extraction."""

    content: str
    document_metadata: dict


class DocumentExtractor(Protocol):
    """Protocol for document content extractors.

    Extractors implement this protocol to handle specific document formats.
    Each extractor must provide:
    - method_name: Identifies the extraction method used (e.g., "pymupdf4llm")
    - extract(): Async method that extracts content from the source file
    """

    method_name: str

    async def extract(self, source: Path) -> ExtractionResult:
        """Extract content from a document file.

        Args:
            source: Path to the source document file.

        Returns:
            ExtractionResult with content and document metadata.

        Raises:
            ValueError: If extraction fails (encrypted, empty, corrupted, etc.)
        """
        ...
