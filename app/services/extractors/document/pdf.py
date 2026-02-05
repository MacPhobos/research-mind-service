"""PDF content extractor using PyMuPDF4LLM for structure detection."""

from pathlib import Path

import fitz  # PyMuPDF
import pymupdf4llm

from app.services.extractors.document.base import ExtractionResult


class PDFExtractor:
    """Extract text from PDF with structure detection.

    Uses pymupdf4llm to convert PDF to markdown, preserving:
    - Headers (H1, H2, H3, etc.)
    - Paragraphs
    - Lists (ordered and unordered)
    - Tables

    Raises ValueError for:
    - Encrypted/password-protected PDFs
    - Image-only PDFs (no extractable text)
    - Corrupted/malformed PDFs
    """

    method_name = "pymupdf4llm"

    async def extract(self, source: Path) -> ExtractionResult:
        """Extract markdown content from PDF.

        Args:
            source: Path to the PDF file.

        Returns:
            ExtractionResult with markdown content and document metadata.

        Raises:
            ValueError: If PDF is encrypted, empty, or corrupted.
        """
        # Open PDF to check for encryption and get metadata
        try:
            doc = fitz.open(str(source))
        except Exception as e:
            raise ValueError(
                f"Failed to open PDF file. The document may be corrupted: {e}"
            ) from e

        try:
            # Check for encryption
            if doc.is_encrypted:
                raise ValueError(
                    "PDF is encrypted and requires a password. "
                    "Please provide an unencrypted document."
                )

            # Extract document metadata
            pdf_metadata = doc.metadata or {}
            document_metadata = {
                "title": pdf_metadata.get("title") or None,
                "author": pdf_metadata.get("author") or None,
                "subject": pdf_metadata.get("subject") or None,
                "page_count": len(doc),
                "creation_date": pdf_metadata.get("creationDate") or None,
                "modification_date": pdf_metadata.get("modDate") or None,
            }
            # Remove None values for cleaner metadata
            document_metadata = {
                k: v for k, v in document_metadata.items() if v is not None
            }

        finally:
            doc.close()

        # Extract content with structure detection
        # pymupdf4llm handles headers, lists, tables automatically
        try:
            markdown_content = pymupdf4llm.to_markdown(
                str(source),
                page_chunks=False,  # Return single string, not list
            )
        except Exception as e:
            raise ValueError(
                f"Failed to extract content from PDF. "
                f"The document may be corrupted: {e}"
            ) from e

        if not markdown_content or not markdown_content.strip():
            raise ValueError(
                "No text content could be extracted from PDF. "
                "The document may be image-only or corrupted."
            )

        return ExtractionResult(
            content=markdown_content.strip(),
            document_metadata=document_metadata,
        )
