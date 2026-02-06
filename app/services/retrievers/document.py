"""Retriever for document files (PDF, DOCX, Markdown, plain text)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.services.extractors.document import (
    DOCXExtractor,
    ExtractionResult,
    PDFExtractor,
    TextExtractor,
)
from app.services.retrievers.base import RetrievalResult

logger = logging.getLogger(__name__)

# Supported document extensions
SUPPORTED_EXTENSIONS: set[str] = {".pdf", ".docx", ".md", ".txt"}

# Map extensions to extractor classes
EXTRACTOR_MAP: dict[str, type] = {
    ".pdf": PDFExtractor,
    ".docx": DOCXExtractor,
    ".md": TextExtractor,
    ".txt": TextExtractor,
}


class DocumentRetriever:
    """Handle document file extraction and storage.

    Extracts content from PDF, DOCX, Markdown, and plain text files
    using the appropriate extractor. Stores extracted markdown/text
    content and metadata in the target directory.

    Output structure:
        {target_dir}/
            content.md      # Extracted content (markdown)
            content.txt     # Extracted content (for .txt files)
            metadata.json   # Extraction metadata

    Note: Original document files are NOT copied to storage.
    """

    def retrieve(
        self,
        *,
        source: str | bytes,
        target_dir: Path,
        title: str | None = None,
        metadata: dict | None = None,
    ) -> RetrievalResult:
        """Extract content from document and store in target_dir.

        Args:
            source: Path to the source document file.
            target_dir: Pre-created directory to write extracted content.
            title: Optional display title. Defaults to filename.
            metadata: Optional extra metadata from the request.

        Returns:
            RetrievalResult with outcome details.
        """
        # source should be a file path string for documents
        if isinstance(source, bytes):
            return RetrievalResult(
                success=False,
                storage_path=str(target_dir.name),
                size_bytes=0,
                mime_type=None,
                title=title or "Unknown document",
                metadata=metadata or {},
                error_message="Document source must be a file path, not bytes",
            )

        source_path = Path(source)

        # Validate file exists
        if not source_path.exists():
            return RetrievalResult(
                success=False,
                storage_path=str(target_dir.name),
                size_bytes=0,
                mime_type=None,
                title=title or source_path.name,
                metadata={"source_path": source, **(metadata or {})},
                error_message=f"Source file not found: {source}",
            )

        # Validate extension
        file_ext = source_path.suffix.lower()
        if file_ext not in SUPPORTED_EXTENSIONS:
            return RetrievalResult(
                success=False,
                storage_path=str(target_dir.name),
                size_bytes=0,
                mime_type=None,
                title=title or source_path.name,
                metadata={
                    "source_path": source,
                    "file_extension": file_ext,
                    **(metadata or {}),
                },
                error_message=(
                    f"Unsupported file extension: {file_ext}. "
                    f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
                ),
            )

        # Get appropriate extractor
        extractor_cls = EXTRACTOR_MAP.get(file_ext)
        if not extractor_cls:
            return RetrievalResult(
                success=False,
                storage_path=str(target_dir.name),
                size_bytes=0,
                mime_type=None,
                title=title or source_path.name,
                metadata={
                    "source_path": source,
                    "file_extension": file_ext,
                    **(metadata or {}),
                },
                error_message=f"No extractor found for extension: {file_ext}",
            )

        # Run async extraction in sync context
        try:
            extraction_result = self._run_extraction(extractor_cls, source_path)
        except ValueError as e:
            # Extraction validation error (encrypted, empty, corrupted)
            return self._build_error_result(
                source_path=source_path,
                target_dir=target_dir,
                title=title,
                metadata=metadata,
                error_message=str(e),
            )
        except Exception as e:
            logger.exception("Unexpected error extracting document: %s", source_path)
            return self._build_error_result(
                source_path=source_path,
                target_dir=target_dir,
                title=title,
                metadata=metadata,
                error_message=f"Extraction failed: {e}",
            )

        # Determine output filename
        output_filename = "content.txt" if file_ext == ".txt" else "content.md"
        content_file = target_dir / output_filename

        # Write extracted content
        try:
            content_file.write_text(extraction_result.content, encoding="utf-8")
        except Exception as e:
            logger.exception("Failed to write content file: %s", content_file)
            return self._build_error_result(
                source_path=source_path,
                target_dir=target_dir,
                title=title,
                metadata=metadata,
                error_message=f"Failed to write content: {e}",
            )

        # Build comprehensive metadata
        file_size_bytes = source_path.stat().st_size
        content_bytes = len(extraction_result.content.encode("utf-8"))
        word_count = len(extraction_result.content.split())
        char_count = len(extraction_result.content)

        extraction_metadata = {
            "original_filename": source_path.name,
            "file_extension": file_ext,
            "file_size_bytes": file_size_bytes,
            "extraction_method": extractor_cls.__name__,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "document_metadata": extraction_result.document_metadata,
            "content_stats": {
                "word_count": word_count,
                "char_count": char_count,
                "content_bytes": content_bytes,
            },
            **(metadata or {}),
        }

        # Write metadata.json
        metadata_file = target_dir / "metadata.json"
        try:
            metadata_file.write_text(
                json.dumps(extraction_metadata, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Failed to write metadata file: %s", e)
            # Continue anyway, metadata is not critical

        # Determine display title
        display_title = title or source_path.stem

        # Determine MIME type for extracted content
        mime_type = "text/plain" if file_ext == ".txt" else "text/markdown"

        logger.info(
            "Extracted document %s: %d words, %d bytes",
            source_path.name,
            word_count,
            content_bytes,
        )

        return RetrievalResult(
            success=True,
            storage_path=str(target_dir.name),
            size_bytes=content_bytes,
            mime_type=mime_type,
            title=display_title,
            metadata=extraction_metadata,
        )

    def _run_extraction(
        self, extractor_cls: type, source_path: Path
    ) -> ExtractionResult:
        """Run async extraction in sync context.

        Handles async-to-sync conversion with proper exception propagation.

        Args:
            extractor_cls: The extractor class to instantiate.
            source_path: Path to the source document.

        Returns:
            ExtractionResult from the extractor.

        Raises:
            ValueError: If extraction fails.
            Exception: For other extraction errors.
        """
        return asyncio.run(self._extract_content(extractor_cls, source_path))

    async def _extract_content(
        self, extractor_cls: type, source_path: Path
    ) -> ExtractionResult:
        """Run extraction with the given extractor class.

        Args:
            extractor_cls: The extractor class to instantiate.
            source_path: Path to the source document.

        Returns:
            ExtractionResult from the extractor.

        Raises:
            ValueError: If extraction fails.
        """
        extractor = extractor_cls()
        return await extractor.extract(source_path)

    def _build_error_result(
        self,
        source_path: Path,
        target_dir: Path,
        title: str | None,
        metadata: dict | None,
        error_message: str,
    ) -> RetrievalResult:
        """Build a RetrievalResult for error cases.

        Args:
            source_path: Path to the source document.
            target_dir: Target directory (for storage_path).
            title: Optional display title.
            metadata: Optional extra metadata.
            error_message: The error message.

        Returns:
            RetrievalResult with success=False.
        """
        return RetrievalResult(
            success=False,
            storage_path=str(target_dir.name),
            size_bytes=0,
            mime_type=None,
            title=title or source_path.name,
            metadata={
                "source_path": str(source_path),
                "file_extension": source_path.suffix.lower(),
                "error_type": "extraction_error",
                **(metadata or {}),
            },
            error_message=error_message,
        )
