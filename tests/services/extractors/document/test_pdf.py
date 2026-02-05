"""Tests for PDF content extractor."""

import pytest
import fitz  # PyMuPDF

from app.services.extractors.document.pdf import PDFExtractor


@pytest.fixture
def pdf_extractor():
    """Create a PDFExtractor instance."""
    return PDFExtractor()


@pytest.fixture
def simple_pdf(tmp_path):
    """Create a simple PDF with text content."""
    pdf_path = tmp_path / "simple.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello, World!")
    page.insert_text((72, 100), "This is a simple PDF document.")
    page.insert_text((72, 128), "It contains multiple lines of text.")
    doc.set_metadata({
        "title": "Test Document",
        "author": "Test Author",
        "subject": "Test Subject",
    })
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def multi_page_pdf(tmp_path):
    """Create a multi-page PDF."""
    pdf_path = tmp_path / "multi_page.pdf"
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1} content")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


@pytest.fixture
def encrypted_pdf(tmp_path):
    """Create an encrypted (password-protected) PDF."""
    pdf_path = tmp_path / "encrypted.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Secret content")
    doc.save(str(pdf_path), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="password")
    doc.close()
    return pdf_path


@pytest.fixture
def empty_pdf(tmp_path):
    """Create an empty PDF (pages but no text)."""
    pdf_path = tmp_path / "empty.pdf"
    doc = fitz.open()
    doc.new_page()  # Empty page
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


class TestPDFExtractor:
    """Test suite for PDFExtractor."""

    @pytest.mark.asyncio
    async def test_extract_simple_pdf(self, pdf_extractor, simple_pdf):
        """Test extracting content from a simple PDF."""
        result = await pdf_extractor.extract(simple_pdf)

        assert result.content is not None
        assert "Hello, World!" in result.content
        assert "simple PDF document" in result.content
        assert "multiple lines" in result.content

    @pytest.mark.asyncio
    async def test_extract_pdf_metadata(self, pdf_extractor, simple_pdf):
        """Test extracting metadata from PDF."""
        result = await pdf_extractor.extract(simple_pdf)

        assert result.document_metadata is not None
        assert result.document_metadata.get("title") == "Test Document"
        assert result.document_metadata.get("author") == "Test Author"
        assert result.document_metadata.get("subject") == "Test Subject"

    @pytest.mark.asyncio
    async def test_extract_pdf_page_count(self, pdf_extractor, multi_page_pdf):
        """Test that page count is extracted."""
        result = await pdf_extractor.extract(multi_page_pdf)

        assert result.document_metadata.get("page_count") == 3
        assert "Page 1 content" in result.content
        assert "Page 2 content" in result.content
        assert "Page 3 content" in result.content

    @pytest.mark.asyncio
    async def test_encrypted_pdf_raises_error(self, pdf_extractor, encrypted_pdf):
        """Test that encrypted PDF raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await pdf_extractor.extract(encrypted_pdf)

        assert "encrypted" in str(exc_info.value).lower()
        assert "password" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_empty_pdf_raises_error(self, pdf_extractor, empty_pdf):
        """Test that PDF with no text content raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await pdf_extractor.extract(empty_pdf)

        assert "no text content" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_nonexistent_pdf_raises_error(self, pdf_extractor, tmp_path):
        """Test that non-existent file raises ValueError."""
        nonexistent = tmp_path / "nonexistent.pdf"

        with pytest.raises(ValueError) as exc_info:
            await pdf_extractor.extract(nonexistent)

        assert "corrupted" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_corrupted_pdf_raises_error(self, pdf_extractor, tmp_path):
        """Test that corrupted PDF raises ValueError."""
        corrupted_path = tmp_path / "corrupted.pdf"
        corrupted_path.write_bytes(b"not a valid pdf content")

        with pytest.raises(ValueError) as exc_info:
            await pdf_extractor.extract(corrupted_path)

        assert "corrupted" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_method_name(self, pdf_extractor):
        """Test that method_name is set correctly."""
        assert pdf_extractor.method_name == "pymupdf4llm"

    @pytest.mark.asyncio
    async def test_content_is_stripped(self, pdf_extractor, simple_pdf):
        """Test that extracted content is stripped of leading/trailing whitespace."""
        result = await pdf_extractor.extract(simple_pdf)

        assert result.content == result.content.strip()

    @pytest.mark.asyncio
    async def test_metadata_removes_none_values(self, pdf_extractor, tmp_path):
        """Test that None metadata values are removed."""
        # Create PDF without metadata
        pdf_path = tmp_path / "no_metadata.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Content without metadata")
        doc.save(str(pdf_path))
        doc.close()

        result = await pdf_extractor.extract(pdf_path)

        # Should have page_count but not None values like title, author
        assert "page_count" in result.document_metadata
        assert result.document_metadata["page_count"] == 1
        # None values should not be present
        for value in result.document_metadata.values():
            assert value is not None
