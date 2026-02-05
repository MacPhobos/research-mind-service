"""DOCX content extractor using Mammoth and Markdownify."""

from pathlib import Path

import mammoth
from docx import Document  # python-docx for metadata
from markdownify import markdownify as md

from app.services.extractors.document.base import ExtractionResult


class DOCXExtractor:
    """Extract markdown from DOCX using Mammoth.

    Conversion pipeline:
    1. Extract metadata using python-docx
    2. Convert DOCX to HTML using Mammoth (preserves structure)
    3. Convert HTML to Markdown using markdownify

    Preserves:
    - Headings (H1-H6)
    - Bold, italic, underline formatting
    - Ordered and unordered lists
    - Tables
    - Links

    Raises ValueError for:
    - Empty documents
    - Corrupted/malformed DOCX files
    """

    method_name = "mammoth"

    async def extract(self, source: Path) -> ExtractionResult:
        """Extract markdown content from DOCX.

        Args:
            source: Path to the DOCX file.

        Returns:
            ExtractionResult with markdown content and document metadata.

        Raises:
            ValueError: If DOCX is empty or corrupted.
        """
        # Extract metadata using python-docx (best-effort)
        document_metadata = {}
        try:
            doc = Document(str(source))
            core_props = doc.core_properties
            document_metadata = {
                "title": core_props.title or None,
                "author": core_props.author or None,
                "subject": core_props.subject or None,
                "created": (
                    core_props.created.isoformat() if core_props.created else None
                ),
                "modified": (
                    core_props.modified.isoformat() if core_props.modified else None
                ),
            }
            # Remove None values for cleaner metadata
            document_metadata = {
                k: v for k, v in document_metadata.items() if v is not None
            }
        except Exception:
            # Metadata extraction is best-effort; continue with empty metadata
            pass

        # Convert DOCX to HTML using Mammoth
        try:
            with open(source, "rb") as f:
                result = mammoth.convert_to_html(f)
                html_content = result.value
        except Exception as e:
            raise ValueError(
                f"Failed to read DOCX file. The document may be corrupted: {e}"
            ) from e

        if not html_content or not html_content.strip():
            raise ValueError(
                "No content could be extracted from DOCX. "
                "The document may be empty or corrupted."
            )

        # Convert HTML to Markdown
        markdown_content = md(
            html_content,
            heading_style="ATX",  # Use # style headings
            bullets="-",  # Use - for unordered lists
            strip=["script", "style"],  # Remove script/style tags
        )

        if not markdown_content or not markdown_content.strip():
            raise ValueError(
                "No content could be extracted from DOCX. "
                "The document may be empty or corrupted."
            )

        return ExtractionResult(
            content=markdown_content.strip(),
            document_metadata=document_metadata,
        )
