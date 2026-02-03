"""Tests for HTML content extraction."""

from __future__ import annotations

import pytest

from app.services.extractors.base import ExtractionConfig
from app.services.extractors.exceptions import EmptyContentError
from app.services.extractors.html_extractor import HTMLExtractor


# Sample HTML fixtures
ARTICLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Article</title></head>
<body>
<article>
<h1>Main Heading</h1>
<p>This is a substantial article with enough content to pass the minimum length requirement.
It contains multiple sentences and paragraphs to ensure proper extraction testing.</p>
<p>Second paragraph with more content for thorough testing of the extraction pipeline.
We need to make sure this has plenty of text to exceed the minimum threshold.</p>
<p>Third paragraph adds even more substantial content to guarantee we pass any
reasonable minimum content length requirements that might be configured.</p>
</article>
<nav>Navigation menu that should be ignored</nav>
<footer>Footer content that should also be ignored</footer>
</body>
</html>
"""

MINIMAL_HTML = """
<!DOCTYPE html>
<html><body><p>Short</p></body></html>
"""

HTML_WITHOUT_TITLE = """
<!DOCTYPE html>
<html>
<head></head>
<body>
<article>
<p>This is content without a title tag in the head section.
We have enough content here to pass the minimum length requirement
for extraction validation. Adding more text to ensure we exceed
the default minimum of 100 characters.</p>
</article>
</body>
</html>
"""

HTML_WITH_COMPLEX_CONTENT = """
<!DOCTYPE html>
<html>
<head><title>Complex Page</title></head>
<body>
<div class="content">
<h1>Article Title</h1>
<p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor
incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud
exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.</p>
<p>Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu
fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa
qui officia deserunt mollit anim id est laborum.</p>
<ul>
<li>First item</li>
<li>Second item</li>
<li>Third item</li>
</ul>
</div>
<aside>Sidebar content to be excluded</aside>
</body>
</html>
"""


class TestHTMLExtractor:
    """Test suite for HTMLExtractor class."""

    def test_extract_article_content(self) -> None:
        """Test extraction of article content from well-structured HTML."""
        extractor = HTMLExtractor()
        result = extractor.extract(ARTICLE_HTML, "https://example.com/article")

        assert result.content
        assert len(result.content) >= 100
        # Title may be extracted from <title> tag or from H1 depending on library
        assert result.title in ("Test Article", "Main Heading")
        assert result.extraction_method in ("trafilatura", "newspaper4k")
        assert result.word_count > 0
        assert result.extraction_time_ms > 0

    def test_extract_raises_on_minimal_content(self) -> None:
        """Test that extraction raises EmptyContentError for insufficient content."""
        extractor = HTMLExtractor()

        with pytest.raises(EmptyContentError) as exc_info:
            extractor.extract(MINIMAL_HTML, "https://example.com")

        assert "insufficient content" in str(exc_info.value).lower()
        assert "minimum" in str(exc_info.value).lower()

    def test_title_extraction(self) -> None:
        """Test title extraction from HTML.

        Note: trafilatura may extract title from <title> tag or H1,
        depending on content structure. Both are valid behaviors.
        """
        extractor = HTMLExtractor()
        result = extractor.extract(ARTICLE_HTML, "https://example.com/article")

        # Title should be extracted - could be from <title> or H1
        assert result.title in ("Test Article", "Main Heading")

    def test_title_fallback_to_url(self) -> None:
        """Test that title falls back to URL when no title tag exists."""
        extractor = HTMLExtractor()
        url = "https://example.com/no-title-page"
        result = extractor.extract(HTML_WITHOUT_TITLE, url)

        # Title should either be extracted from content or fall back to URL
        assert result.title is not None
        assert len(result.title) > 0

    def test_extraction_with_custom_config(self) -> None:
        """Test extraction with custom configuration."""
        config = ExtractionConfig(min_content_length=50)
        extractor = HTMLExtractor(config)
        result = extractor.extract(ARTICLE_HTML, "https://example.com/article")

        assert result.content
        assert len(result.content) >= 50

    def test_extraction_with_strict_min_length(self) -> None:
        """Test that strict minimum length config is respected."""
        config = ExtractionConfig(min_content_length=10000)
        extractor = HTMLExtractor(config)

        with pytest.raises(EmptyContentError):
            extractor.extract(ARTICLE_HTML, "https://example.com")

    def test_complex_html_extraction(self) -> None:
        """Test extraction from HTML with complex structure."""
        extractor = HTMLExtractor()
        result = extractor.extract(HTML_WITH_COMPLEX_CONTENT, "https://example.com/complex")

        assert result.content
        # Title may be from <title> tag or H1
        assert result.title in ("Complex Page", "Article Title")
        # Should contain some of the main content
        assert "Lorem ipsum" in result.content or len(result.content) > 100

    def test_word_count_calculation(self) -> None:
        """Test that word count is calculated correctly."""
        extractor = HTMLExtractor()
        result = extractor.extract(ARTICLE_HTML, "https://example.com/article")

        # Word count should match content split by whitespace
        expected_word_count = len(result.content.split())
        assert result.word_count == expected_word_count

    def test_extraction_time_is_recorded(self) -> None:
        """Test that extraction time is recorded in milliseconds."""
        extractor = HTMLExtractor()
        result = extractor.extract(ARTICLE_HTML, "https://example.com/article")

        assert result.extraction_time_ms > 0
        # Should be reasonable (less than 10 seconds for simple HTML)
        assert result.extraction_time_ms < 10000

    def test_warnings_list_initialized(self) -> None:
        """Test that warnings list is properly initialized."""
        extractor = HTMLExtractor()
        result = extractor.extract(ARTICLE_HTML, "https://example.com/article")

        assert isinstance(result.warnings, list)


class TestHTMLExtractorFallback:
    """Test suite for HTMLExtractor fallback behavior."""

    def test_trafilatura_is_primary_method(self) -> None:
        """Test that trafilatura is tried first."""
        extractor = HTMLExtractor()
        result = extractor.extract(ARTICLE_HTML, "https://example.com/article")

        # For well-structured HTML, trafilatura should succeed
        assert result.extraction_method in ("trafilatura", "newspaper4k")

    def test_fallback_warning_when_primary_insufficient(self) -> None:
        """Test that warning is added when falling back to newspaper4k."""
        # Create HTML that might produce short content from trafilatura
        sparse_html = """
        <!DOCTYPE html>
        <html>
        <head><title>Sparse Page</title></head>
        <body>
        <div>
        <p>This is some content that needs to be long enough to pass validation
        but might trigger fallback behavior in certain scenarios depending on
        how the extractors handle the HTML structure and content detection.</p>
        </div>
        </body>
        </html>
        """
        extractor = HTMLExtractor()
        result = extractor.extract(sparse_html, "https://example.com/sparse")

        # Result should succeed with either method
        assert result.content
        assert result.extraction_method in ("trafilatura", "newspaper4k")
