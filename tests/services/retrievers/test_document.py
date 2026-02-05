"""Tests for DocumentRetriever with document extractor integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.extractors.document.base import ExtractionResult
from app.services.retrievers.document import (
    EXTRACTOR_MAP,
    SUPPORTED_EXTENSIONS,
    DocumentRetriever,
)


class TestDocumentRetrieverSuccess:
    """Test suite for successful document extraction."""

    def test_extract_pdf_success(self, tmp_path: Path) -> None:
        """Successful PDF extraction stores markdown and metadata."""
        # Create a fake source file
        source_file = tmp_path / "source" / "test_document.pdf"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(b"fake pdf content")

        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)

        mock_result = ExtractionResult(
            content="# Document Title\n\nThis is the extracted content from PDF.",
            document_metadata={
                "title": "Test PDF Document",
                "author": "Test Author",
                "page_count": 5,
            },
        )

        with patch.object(
            DocumentRetriever,
            "_run_extraction",
            return_value=mock_result,
        ):
            retriever = DocumentRetriever()
            result = retriever.retrieve(
                source=str(source_file),
                target_dir=target_dir,
                title="Custom Title",
            )

        assert result.success is True
        assert result.title == "Custom Title"
        assert result.mime_type == "text/markdown"
        assert result.size_bytes == len(mock_result.content.encode("utf-8"))

        # Verify content file
        content_file = target_dir / "content.md"
        assert content_file.exists()
        assert content_file.read_text() == mock_result.content

        # Verify metadata
        meta_file = target_dir / "metadata.json"
        assert meta_file.exists()
        meta = json.loads(meta_file.read_text())
        assert meta["original_filename"] == "test_document.pdf"
        assert meta["file_extension"] == ".pdf"
        assert meta["extraction_method"] == "PDFExtractor"
        assert "extracted_at" in meta
        assert meta["document_metadata"]["title"] == "Test PDF Document"
        assert meta["document_metadata"]["author"] == "Test Author"
        assert meta["content_stats"]["word_count"] == 10  # "# Document Title This is the extracted content from PDF."

    def test_extract_docx_success(self, tmp_path: Path) -> None:
        """Successful DOCX extraction stores markdown and metadata."""
        source_file = tmp_path / "source" / "report.docx"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(b"fake docx content")

        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)

        mock_result = ExtractionResult(
            content="# Report\n\n## Section 1\n\nParagraph content here.",
            document_metadata={
                "title": "Quarterly Report",
                "author": "Business Team",
            },
        )

        with patch.object(
            DocumentRetriever,
            "_run_extraction",
            return_value=mock_result,
        ):
            retriever = DocumentRetriever()
            result = retriever.retrieve(
                source=str(source_file),
                target_dir=target_dir,
            )

        assert result.success is True
        assert result.title == "report"  # Uses stem when no title provided
        assert result.mime_type == "text/markdown"

        content_file = target_dir / "content.md"
        assert content_file.exists()
        assert content_file.read_text() == mock_result.content

        meta = json.loads((target_dir / "metadata.json").read_text())
        assert meta["file_extension"] == ".docx"
        assert meta["extraction_method"] == "DOCXExtractor"

    def test_extract_markdown_success(self, tmp_path: Path) -> None:
        """Successful Markdown extraction stores content."""
        source_file = tmp_path / "source" / "readme.md"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("# README\n\nProject documentation.", encoding="utf-8")

        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)

        mock_result = ExtractionResult(
            content="# README\n\nProject documentation.",
            document_metadata={},
        )

        with patch.object(
            DocumentRetriever,
            "_run_extraction",
            return_value=mock_result,
        ):
            retriever = DocumentRetriever()
            result = retriever.retrieve(
                source=str(source_file),
                target_dir=target_dir,
            )

        assert result.success is True
        assert result.title == "readme"
        assert result.mime_type == "text/markdown"

        # MD files should output content.md
        content_file = target_dir / "content.md"
        assert content_file.exists()

        meta = json.loads((target_dir / "metadata.json").read_text())
        assert meta["file_extension"] == ".md"
        assert meta["extraction_method"] == "TextExtractor"

    def test_extract_txt_success(self, tmp_path: Path) -> None:
        """Successful TXT extraction stores content as content.txt."""
        source_file = tmp_path / "source" / "notes.txt"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_text("Plain text content here.", encoding="utf-8")

        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)

        mock_result = ExtractionResult(
            content="Plain text content here.",
            document_metadata={},
        )

        with patch.object(
            DocumentRetriever,
            "_run_extraction",
            return_value=mock_result,
        ):
            retriever = DocumentRetriever()
            result = retriever.retrieve(
                source=str(source_file),
                target_dir=target_dir,
            )

        assert result.success is True
        assert result.mime_type == "text/plain"

        # TXT files should output content.txt
        content_file = target_dir / "content.txt"
        assert content_file.exists()
        assert content_file.read_text() == mock_result.content

        meta = json.loads((target_dir / "metadata.json").read_text())
        assert meta["file_extension"] == ".txt"

    def test_custom_metadata_merged(self, tmp_path: Path) -> None:
        """Custom metadata is merged with extraction metadata."""
        source_file = tmp_path / "source" / "doc.pdf"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(b"fake pdf")

        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)

        mock_result = ExtractionResult(
            content="Content",
            document_metadata={"page_count": 1},
        )

        with patch.object(
            DocumentRetriever,
            "_run_extraction",
            return_value=mock_result,
        ):
            retriever = DocumentRetriever()
            result = retriever.retrieve(
                source=str(source_file),
                target_dir=target_dir,
                metadata={"session_id": "sess_123", "custom_key": "custom_value"},
            )

        assert result.success is True
        meta = json.loads((target_dir / "metadata.json").read_text())
        assert meta["session_id"] == "sess_123"
        assert meta["custom_key"] == "custom_value"
        assert meta["original_filename"] == "doc.pdf"

    def test_content_stats_calculated(self, tmp_path: Path) -> None:
        """Content statistics are calculated and included."""
        source_file = tmp_path / "source" / "article.pdf"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(b"fake pdf")

        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)

        content = "This is a test document with some words."
        mock_result = ExtractionResult(
            content=content,
            document_metadata={},
        )

        with patch.object(
            DocumentRetriever,
            "_run_extraction",
            return_value=mock_result,
        ):
            retriever = DocumentRetriever()
            result = retriever.retrieve(
                source=str(source_file),
                target_dir=target_dir,
            )

        assert result.success is True
        meta = json.loads((target_dir / "metadata.json").read_text())
        assert meta["content_stats"]["word_count"] == 8
        assert meta["content_stats"]["char_count"] == len(content)
        assert meta["content_stats"]["content_bytes"] == len(content.encode("utf-8"))


class TestDocumentRetrieverErrors:
    """Test suite for document extraction error handling."""

    def test_source_not_found(self, tmp_path: Path) -> None:
        """Returns error when source file does not exist."""
        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)

        retriever = DocumentRetriever()
        result = retriever.retrieve(
            source="/nonexistent/path/document.pdf",
            target_dir=target_dir,
        )

        assert result.success is False
        assert "not found" in result.error_message.lower()
        assert result.title == "document.pdf"
        assert result.metadata["source_path"] == "/nonexistent/path/document.pdf"

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        """Returns error for unsupported file extensions."""
        source_file = tmp_path / "source" / "image.png"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(b"fake image")

        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)

        retriever = DocumentRetriever()
        result = retriever.retrieve(
            source=str(source_file),
            target_dir=target_dir,
        )

        assert result.success is False
        assert "unsupported file extension" in result.error_message.lower()
        assert ".png" in result.error_message.lower()
        assert result.metadata["file_extension"] == ".png"

    def test_bytes_source_rejected(self, tmp_path: Path) -> None:
        """Returns error when source is bytes instead of path."""
        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)

        retriever = DocumentRetriever()
        result = retriever.retrieve(
            source=b"raw bytes content",
            target_dir=target_dir,
            title="Test Document",
        )

        assert result.success is False
        assert "must be a file path" in result.error_message.lower()
        assert result.title == "Test Document"

    def test_extraction_error_value_error(self, tmp_path: Path) -> None:
        """Handles ValueError from extractor (encrypted, empty, etc.)."""
        source_file = tmp_path / "source" / "encrypted.pdf"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(b"fake encrypted pdf")

        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)

        with patch.object(
            DocumentRetriever,
            "_run_extraction",
            side_effect=ValueError("PDF is encrypted and requires a password"),
        ):
            retriever = DocumentRetriever()
            result = retriever.retrieve(
                source=str(source_file),
                target_dir=target_dir,
            )

        assert result.success is False
        assert "encrypted" in result.error_message.lower()
        assert result.metadata["error_type"] == "extraction_error"

    def test_extraction_error_generic(self, tmp_path: Path) -> None:
        """Handles generic exceptions from extractor."""
        source_file = tmp_path / "source" / "corrupted.pdf"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(b"corrupted content")

        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)

        with patch.object(
            DocumentRetriever,
            "_run_extraction",
            side_effect=RuntimeError("Unexpected internal error"),
        ):
            retriever = DocumentRetriever()
            result = retriever.retrieve(
                source=str(source_file),
                target_dir=target_dir,
            )

        assert result.success is False
        assert "extraction failed" in result.error_message.lower()

    def test_title_override_used_on_error(self, tmp_path: Path) -> None:
        """Title override is used when extraction fails."""
        source_file = tmp_path / "source" / "bad.pdf"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(b"bad content")

        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)

        with patch.object(
            DocumentRetriever,
            "_run_extraction",
            side_effect=ValueError("Extraction failed"),
        ):
            retriever = DocumentRetriever()
            result = retriever.retrieve(
                source=str(source_file),
                target_dir=target_dir,
                title="My Custom Title",
            )

        assert result.success is False
        assert result.title == "My Custom Title"

    def test_custom_metadata_preserved_on_error(self, tmp_path: Path) -> None:
        """Custom metadata is preserved when extraction fails."""
        source_file = tmp_path / "source" / "error.pdf"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(b"error content")

        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)

        with patch.object(
            DocumentRetriever,
            "_run_extraction",
            side_effect=ValueError("Some error"),
        ):
            retriever = DocumentRetriever()
            result = retriever.retrieve(
                source=str(source_file),
                target_dir=target_dir,
                metadata={"session_id": "sess_456"},
            )

        assert result.success is False
        assert result.metadata["session_id"] == "sess_456"


class TestDocumentRetrieverConfig:
    """Test suite for DocumentRetriever configuration."""

    def test_supported_extensions(self) -> None:
        """Verify supported extensions are correctly defined."""
        assert ".pdf" in SUPPORTED_EXTENSIONS
        assert ".docx" in SUPPORTED_EXTENSIONS
        assert ".md" in SUPPORTED_EXTENSIONS
        assert ".txt" in SUPPORTED_EXTENSIONS
        assert len(SUPPORTED_EXTENSIONS) == 4

    def test_extractor_map_coverage(self) -> None:
        """All supported extensions have corresponding extractors."""
        for ext in SUPPORTED_EXTENSIONS:
            assert ext in EXTRACTOR_MAP, f"Missing extractor for {ext}"
            assert EXTRACTOR_MAP[ext] is not None

    def test_case_insensitive_extension_matching(self, tmp_path: Path) -> None:
        """Extension matching is case-insensitive."""
        source_file = tmp_path / "source" / "DOCUMENT.PDF"
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(b"fake pdf")

        target_dir = tmp_path / "target"
        target_dir.mkdir(parents=True, exist_ok=True)

        mock_result = ExtractionResult(
            content="Content from uppercase PDF",
            document_metadata={},
        )

        with patch.object(
            DocumentRetriever,
            "_run_extraction",
            return_value=mock_result,
        ):
            retriever = DocumentRetriever()
            result = retriever.retrieve(
                source=str(source_file),
                target_dir=target_dir,
            )

        assert result.success is True
        meta = json.loads((target_dir / "metadata.json").read_text())
        assert meta["file_extension"] == ".pdf"


class TestDocumentRetrieverFactoryRegistration:
    """Test that DocumentRetriever is properly registered in factory."""

    def test_factory_returns_document_retriever(self) -> None:
        """Factory returns DocumentRetriever for 'document' content type."""
        from app.services.retrievers.factory import get_retriever

        retriever = get_retriever("document")
        assert isinstance(retriever, DocumentRetriever)

    def test_content_type_enum_has_document(self) -> None:
        """ContentType enum includes DOCUMENT value."""
        from app.models.content_item import ContentType

        assert hasattr(ContentType, "DOCUMENT")
        assert ContentType.DOCUMENT.value == "document"
