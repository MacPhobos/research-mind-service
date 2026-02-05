"""Text and Markdown content extractor with encoding detection."""

from pathlib import Path

from app.services.extractors.document.base import ExtractionResult


class TextExtractor:
    """Direct extraction for TXT and MD files.

    Handles multiple text encodings:
    - UTF-8 (with and without BOM)
    - Latin-1 (ISO-8859-1)
    - Windows-1252 (CP1252)

    For .md files: Content is stored as-is (no transformation).
    For .txt files: Content is stored as plain text.

    Raises ValueError for:
    - Empty files
    - Files with unrecognized encoding (binary files)
    """

    method_name = "direct"

    async def extract(self, source: Path) -> ExtractionResult:
        """Read text content directly with encoding detection.

        Args:
            source: Path to the text or markdown file.

        Returns:
            ExtractionResult with content and encoding metadata.

        Raises:
            ValueError: If file is empty or has unrecognized encoding.
        """
        # Try multiple encodings in order of likelihood
        encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
        content = None
        detected_encoding = None

        for encoding in encodings:
            try:
                content = source.read_text(encoding=encoding)
                detected_encoding = encoding
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            raise ValueError(
                "Unable to decode text file. "
                "Please ensure the file uses UTF-8 or Latin-1 encoding."
            )

        if not content.strip():
            raise ValueError("Text file is empty.")

        # Minimal metadata for text files
        document_metadata = {
            "encoding_detected": detected_encoding,
        }

        return ExtractionResult(
            content=content,
            document_metadata=document_metadata,
        )
