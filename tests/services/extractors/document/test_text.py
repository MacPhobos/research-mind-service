"""Tests for Text/Markdown content extractor."""

from pathlib import Path

import pytest

from app.services.extractors.document.text import TextExtractor


# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent.parent.parent.parent / "fixtures" / "documents"


@pytest.fixture
def text_extractor():
    """Create a TextExtractor instance."""
    return TextExtractor()


@pytest.fixture
def utf8_text_file(tmp_path):
    """Create a UTF-8 encoded text file."""
    file_path = tmp_path / "utf8.txt"
    file_path.write_text("Hello, World!\nThis is UTF-8 encoded text.", encoding="utf-8")
    return file_path


@pytest.fixture
def utf8_bom_text_file(tmp_path):
    """Create a UTF-8 with BOM text file."""
    file_path = tmp_path / "utf8_bom.txt"
    content = "Hello with BOM!\nThis is UTF-8 BOM encoded."
    file_path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
    return file_path


@pytest.fixture
def latin1_text_file(tmp_path):
    """Create a Latin-1 encoded text file with special characters."""
    file_path = tmp_path / "latin1.txt"
    # Use Latin-1 specific characters
    content = "Caf\xe9 au lait\n\xa9 2024 Test"
    file_path.write_bytes(content.encode("latin-1"))
    return file_path


@pytest.fixture
def cp1252_text_file(tmp_path):
    """Create a CP1252 (Windows-1252) encoded text file."""
    file_path = tmp_path / "cp1252.txt"
    # Use CP1252 specific byte sequences (smart quotes and em dash)
    # These are the raw byte values for CP1252 characters
    # 0x93 = left double quote, 0x94 = right double quote, 0x96 = en dash
    raw_bytes = b"\x93Smart quotes\x94 and \x96 en dash"
    file_path.write_bytes(raw_bytes)
    return file_path


@pytest.fixture
def empty_text_file(tmp_path):
    """Create an empty text file."""
    file_path = tmp_path / "empty.txt"
    file_path.write_text("", encoding="utf-8")
    return file_path


@pytest.fixture
def whitespace_only_file(tmp_path):
    """Create a file with only whitespace."""
    file_path = tmp_path / "whitespace.txt"
    file_path.write_text("   \n\t\n   ", encoding="utf-8")
    return file_path


@pytest.fixture
def binary_file(tmp_path):
    """Create a binary file (not valid text)."""
    file_path = tmp_path / "binary.bin"
    # Write invalid UTF-8 sequences that also aren't valid Latin-1
    file_path.write_bytes(bytes([0x80, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87]))
    return file_path


@pytest.fixture
def multiline_text_file(tmp_path):
    """Create a text file with multiple lines and paragraphs."""
    file_path = tmp_path / "multiline.txt"
    content = """First paragraph of text.
It spans multiple lines.

Second paragraph here.
Also spans multiple lines.

Third and final paragraph."""
    file_path.write_text(content, encoding="utf-8")
    return file_path


class TestTextExtractor:
    """Test suite for TextExtractor."""

    @pytest.mark.asyncio
    async def test_extract_utf8_text(self, text_extractor, utf8_text_file):
        """Test extracting UTF-8 encoded text."""
        result = await text_extractor.extract(utf8_text_file)

        assert result.content is not None
        assert "Hello, World!" in result.content
        assert "UTF-8 encoded text" in result.content
        assert result.document_metadata.get("encoding_detected") == "utf-8"

    @pytest.mark.asyncio
    async def test_extract_utf8_bom_text(self, text_extractor, utf8_bom_text_file):
        """Test extracting UTF-8 with BOM text."""
        result = await text_extractor.extract(utf8_bom_text_file)

        assert result.content is not None
        assert "Hello with BOM!" in result.content
        # Should detect utf-8-sig for BOM files
        assert result.document_metadata.get("encoding_detected") in [
            "utf-8",
            "utf-8-sig",
        ]

    @pytest.mark.asyncio
    async def test_extract_latin1_text(self, text_extractor, latin1_text_file):
        """Test extracting Latin-1 encoded text."""
        result = await text_extractor.extract(latin1_text_file)

        assert result.content is not None
        # The content should be readable
        assert "Caf" in result.content
        assert "lait" in result.content

    @pytest.mark.asyncio
    async def test_extract_cp1252_text(self, text_extractor, cp1252_text_file):
        """Test extracting CP1252 (Windows-1252) encoded text."""
        result = await text_extractor.extract(cp1252_text_file)

        assert result.content is not None
        assert "quotes" in result.content
        assert "dash" in result.content

    @pytest.mark.asyncio
    async def test_extract_multiline_text(self, text_extractor, multiline_text_file):
        """Test extracting text with multiple paragraphs."""
        result = await text_extractor.extract(multiline_text_file)

        assert "First paragraph" in result.content
        assert "Second paragraph" in result.content
        assert "Third and final paragraph" in result.content

    @pytest.mark.asyncio
    async def test_extract_markdown_file(self, text_extractor):
        """Test extracting a markdown file from fixtures."""
        md_path = FIXTURES_DIR / "sample.md"
        result = await text_extractor.extract(md_path)

        assert "# Sample Markdown Document" in result.content
        assert "## Features" in result.content
        assert "Bullet point" in result.content
        assert "```python" in result.content

    @pytest.mark.asyncio
    async def test_extract_simple_text_fixture(self, text_extractor):
        """Test extracting the simple.txt fixture file."""
        txt_path = FIXTURES_DIR / "simple.txt"
        result = await text_extractor.extract(txt_path)

        assert "simple text file" in result.content
        assert "multiple lines" in result.content

    @pytest.mark.asyncio
    async def test_empty_text_raises_error(self, text_extractor, empty_text_file):
        """Test that empty file raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await text_extractor.extract(empty_text_file)

        assert "empty" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_whitespace_only_raises_error(
        self, text_extractor, whitespace_only_file
    ):
        """Test that whitespace-only file raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            await text_extractor.extract(whitespace_only_file)

        assert "empty" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_nonexistent_file_raises_error(self, text_extractor, tmp_path):
        """Test that non-existent file raises an error."""
        nonexistent = tmp_path / "nonexistent.txt"

        with pytest.raises(FileNotFoundError):
            await text_extractor.extract(nonexistent)

    @pytest.mark.asyncio
    async def test_method_name(self, text_extractor):
        """Test that method_name is set correctly."""
        assert text_extractor.method_name == "direct"

    @pytest.mark.asyncio
    async def test_encoding_metadata_included(self, text_extractor, utf8_text_file):
        """Test that encoding is included in metadata."""
        result = await text_extractor.extract(utf8_text_file)

        assert "encoding_detected" in result.document_metadata
        assert result.document_metadata["encoding_detected"] is not None

    @pytest.mark.asyncio
    async def test_preserves_line_breaks(self, text_extractor, multiline_text_file):
        """Test that line breaks are preserved in content."""
        result = await text_extractor.extract(multiline_text_file)

        # Check that newlines are present
        assert "\n" in result.content

    @pytest.mark.asyncio
    async def test_unicode_content(self, text_extractor, tmp_path):
        """Test extracting text with unicode characters."""
        file_path = tmp_path / "unicode.txt"
        content = "Unicode test: \u4e2d\u6587 \u65e5\u672c\u8a9e \ud55c\uad6d\uc5b4 \u0420\u0443\u0441\u0441\u043a\u0438\u0439"
        file_path.write_text(content, encoding="utf-8")

        result = await text_extractor.extract(file_path)

        assert "\u4e2d\u6587" in result.content  # Chinese
        assert "\u65e5\u672c\u8a9e" in result.content  # Japanese
        assert "\ud55c\uad6d\uc5b4" in result.content  # Korean
        assert "\u0420\u0443\u0441\u0441\u043a\u0438\u0439" in result.content  # Russian

    @pytest.mark.asyncio
    async def test_large_text_file(self, text_extractor, tmp_path):
        """Test extracting a larger text file."""
        file_path = tmp_path / "large.txt"
        # Create a file with 1000 lines
        lines = [f"Line {i}: This is some content for testing." for i in range(1000)]
        file_path.write_text("\n".join(lines), encoding="utf-8")

        result = await text_extractor.extract(file_path)

        assert "Line 0:" in result.content
        assert "Line 999:" in result.content
        assert result.document_metadata.get("encoding_detected") == "utf-8"
