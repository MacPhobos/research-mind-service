"""Unit tests for LinkExtractor service.

Tests cover:
- Link parsing from HTML
- Source element detection (nav, main, article, aside, footer, header, other)
- Link categorization
- External vs internal link detection
- Deduplication
- Error handling (fetch failures, timeouts)
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.link_extractor import (
    CategorizedLinks,
    ExtractedLink,
    ExtractedLinksResult,
    LinkExtractionError,
    LinkExtractor,
)


# -----------------------------------------------------------------------------
# HTML Fixtures
# -----------------------------------------------------------------------------

SIMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
<main>
    <a href="/internal-page">Internal Link</a>
    <a href="https://external.com/page">External Link</a>
</main>
</body>
</html>
"""

SEMANTIC_HTML = """
<!DOCTYPE html>
<html>
<head><title>Semantic Page</title></head>
<body>
<nav>
    <a href="/home">Home</a>
    <a href="/about">About</a>
</nav>
<header>
    <a href="/logo">Logo Link</a>
</header>
<main>
    <article>
        <a href="/article-link">Article Link</a>
    </article>
    <a href="/main-link">Main Link</a>
</main>
<aside>
    <a href="/sidebar-link">Sidebar Link</a>
</aside>
<footer>
    <a href="/footer-link">Footer Link</a>
</footer>
<div>
    <a href="/other-link">Other Link</a>
</div>
</body>
</html>
"""

HTML_WITH_DUPLICATES = """
<!DOCTYPE html>
<html>
<head><title>Duplicates Page</title></head>
<body>
<main>
    <a href="/page">First occurrence</a>
    <a href="/page">Duplicate link</a>
    <a href="/page">Another duplicate</a>
    <a href="/unique">Unique link</a>
</main>
</body>
</html>
"""

HTML_WITH_SPECIAL_LINKS = """
<!DOCTYPE html>
<html>
<head><title>Special Links</title></head>
<body>
<main>
    <a href="javascript:void(0)">JavaScript link</a>
    <a href="mailto:test@example.com">Email link</a>
    <a href="tel:+1234567890">Phone link</a>
    <a href="#anchor">Anchor link</a>
    <a href="data:text/html,<h1>Data</h1>">Data URI</a>
    <a href="/valid-link">Valid link</a>
    <a href="">Empty href</a>
    <a>No href attribute</a>
</main>
</body>
</html>
"""

HTML_WITH_RELATIVE_URLS = """
<!DOCTYPE html>
<html>
<head><title>Relative URLs</title></head>
<body>
<main>
    <a href="/absolute-path">Absolute path</a>
    <a href="relative-path">Relative path</a>
    <a href="../parent-path">Parent path</a>
    <a href="https://example.com/full-url">Full URL</a>
</main>
</body>
</html>
"""

HTML_WITH_LONG_TEXT = """
<!DOCTYPE html>
<html>
<head><title>Long Text</title></head>
<body>
<main>
    <a href="/link">""" + "A" * 300 + """</a>
</main>
</body>
</html>
"""

HTML_NO_TITLE = """
<!DOCTYPE html>
<html>
<head></head>
<body>
<main>
    <a href="/link">Link</a>
</main>
</body>
</html>
"""


# -----------------------------------------------------------------------------
# Unit Tests for _parse_links
# -----------------------------------------------------------------------------


class TestParseLinksCategorization:
    """Tests for _parse_links method focusing on categorization."""

    def test_parse_links_basic(self):
        """_parse_links extracts anchor tags with href attributes."""
        extractor = LinkExtractor()
        links = extractor._parse_links(SIMPLE_HTML, "https://example.com")

        assert len(links) == 2
        urls = [link.url for link in links]
        assert "https://example.com/internal-page" in urls
        assert "https://external.com/page" in urls

    def test_parse_links_marks_external(self):
        """_parse_links correctly identifies external links."""
        extractor = LinkExtractor()
        links = extractor._parse_links(SIMPLE_HTML, "https://example.com")

        link_map = {link.url: link for link in links}
        internal = link_map["https://example.com/internal-page"]
        external = link_map["https://external.com/page"]

        assert internal.is_external is False
        assert external.is_external is True

    def test_parse_links_extracts_text(self):
        """_parse_links captures link text/anchor text."""
        extractor = LinkExtractor()
        links = extractor._parse_links(SIMPLE_HTML, "https://example.com")

        link_map = {link.url: link for link in links}
        assert link_map["https://example.com/internal-page"].text == "Internal Link"
        assert link_map["https://external.com/page"].text == "External Link"


class TestParseLinksDeduplication:
    """Tests for _parse_links deduplication behavior."""

    def test_parse_links_deduplicates(self):
        """_parse_links returns only unique URLs."""
        extractor = LinkExtractor()
        links = extractor._parse_links(HTML_WITH_DUPLICATES, "https://example.com")

        urls = [link.url for link in links]
        assert len(urls) == 2
        assert urls.count("https://example.com/page") == 1
        assert "https://example.com/unique" in urls


class TestParseLinksFiltersInvalid:
    """Tests for filtering invalid and special links."""

    def test_parse_links_skips_javascript(self):
        """_parse_links skips javascript: protocol links."""
        extractor = LinkExtractor()
        links = extractor._parse_links(HTML_WITH_SPECIAL_LINKS, "https://example.com")

        urls = [link.url for link in links]
        assert not any("javascript:" in url for url in urls)

    def test_parse_links_skips_mailto(self):
        """_parse_links skips mailto: protocol links."""
        extractor = LinkExtractor()
        links = extractor._parse_links(HTML_WITH_SPECIAL_LINKS, "https://example.com")

        urls = [link.url for link in links]
        assert not any("mailto:" in url for url in urls)

    def test_parse_links_skips_tel(self):
        """_parse_links skips tel: protocol links."""
        extractor = LinkExtractor()
        links = extractor._parse_links(HTML_WITH_SPECIAL_LINKS, "https://example.com")

        urls = [link.url for link in links]
        assert not any("tel:" in url for url in urls)

    def test_parse_links_skips_anchors(self):
        """_parse_links skips hash-only anchor links."""
        extractor = LinkExtractor()
        links = extractor._parse_links(HTML_WITH_SPECIAL_LINKS, "https://example.com")

        urls = [link.url for link in links]
        assert not any(url == "#anchor" or url.endswith("#anchor") for url in urls)

    def test_parse_links_skips_data_uri(self):
        """_parse_links skips data: URI links."""
        extractor = LinkExtractor()
        links = extractor._parse_links(HTML_WITH_SPECIAL_LINKS, "https://example.com")

        urls = [link.url for link in links]
        assert not any("data:" in url for url in urls)

    def test_parse_links_skips_empty_href(self):
        """_parse_links skips empty href attributes."""
        extractor = LinkExtractor()
        links = extractor._parse_links(HTML_WITH_SPECIAL_LINKS, "https://example.com")

        # Only valid link should remain
        assert len(links) == 1
        assert links[0].url == "https://example.com/valid-link"


class TestParseLinksResolvesUrls:
    """Tests for relative URL resolution."""

    def test_parse_links_resolves_relative(self):
        """_parse_links converts relative paths to absolute URLs."""
        extractor = LinkExtractor()
        links = extractor._parse_links(HTML_WITH_RELATIVE_URLS, "https://example.com/dir/page")

        urls = [link.url for link in links]
        assert "https://example.com/absolute-path" in urls
        assert "https://example.com/dir/relative-path" in urls
        assert "https://example.com/parent-path" in urls
        assert "https://example.com/full-url" in urls


class TestParseLinksTextTruncation:
    """Tests for long link text truncation."""

    def test_parse_links_truncates_long_text(self):
        """_parse_links truncates text exceeding MAX_TEXT_LENGTH."""
        extractor = LinkExtractor()
        links = extractor._parse_links(HTML_WITH_LONG_TEXT, "https://example.com")

        assert len(links) == 1
        # MAX_TEXT_LENGTH is 255, truncated text ends with "..."
        assert len(links[0].text) == 255
        assert links[0].text.endswith("...")


# -----------------------------------------------------------------------------
# Unit Tests for _get_source_element
# -----------------------------------------------------------------------------


class TestGetSourceElement:
    """Tests for _get_source_element method."""

    def test_get_source_element_nav(self):
        """_get_source_element returns 'nav' for links in nav element."""
        extractor = LinkExtractor()
        links = extractor._parse_links(SEMANTIC_HTML, "https://example.com")

        home_link = next(link for link in links if "home" in link.url)
        assert home_link.source_element == "nav"

    def test_get_source_element_main(self):
        """_get_source_element returns 'main' for links in main element."""
        extractor = LinkExtractor()
        links = extractor._parse_links(SEMANTIC_HTML, "https://example.com")

        main_link = next(link for link in links if "main-link" in link.url)
        assert main_link.source_element == "main"

    def test_get_source_element_article(self):
        """_get_source_element returns 'article' for links in article element."""
        extractor = LinkExtractor()
        links = extractor._parse_links(SEMANTIC_HTML, "https://example.com")

        article_link = next(link for link in links if "article-link" in link.url)
        assert article_link.source_element == "article"

    def test_get_source_element_aside(self):
        """_get_source_element returns 'aside' for links in aside element."""
        extractor = LinkExtractor()
        links = extractor._parse_links(SEMANTIC_HTML, "https://example.com")

        sidebar_link = next(link for link in links if "sidebar-link" in link.url)
        assert sidebar_link.source_element == "aside"

    def test_get_source_element_footer(self):
        """_get_source_element returns 'footer' for links in footer element."""
        extractor = LinkExtractor()
        links = extractor._parse_links(SEMANTIC_HTML, "https://example.com")

        footer_link = next(link for link in links if "footer-link" in link.url)
        assert footer_link.source_element == "footer"

    def test_get_source_element_header(self):
        """_get_source_element returns 'header' for links in header element."""
        extractor = LinkExtractor()
        links = extractor._parse_links(SEMANTIC_HTML, "https://example.com")

        logo_link = next(link for link in links if "logo" in link.url)
        assert logo_link.source_element == "header"

    def test_get_source_element_other(self):
        """_get_source_element returns 'other' for links outside semantic elements."""
        extractor = LinkExtractor()
        links = extractor._parse_links(SEMANTIC_HTML, "https://example.com")

        other_link = next(link for link in links if "other-link" in link.url)
        assert other_link.source_element == "other"


# -----------------------------------------------------------------------------
# Unit Tests for _categorize_links
# -----------------------------------------------------------------------------


class TestCategorizeLinks:
    """Tests for _categorize_links method."""

    def test_categorize_main_content(self):
        """_categorize_links puts main/article links in main_content."""
        extractor = LinkExtractor()
        links = [
            ExtractedLink(url="https://example.com/1", text="", is_external=False, source_element="main"),
            ExtractedLink(url="https://example.com/2", text="", is_external=False, source_element="article"),
        ]

        categories = extractor._categorize_links(links)

        assert len(categories.main_content) == 2
        assert len(categories.navigation) == 0
        assert len(categories.sidebar) == 0
        assert len(categories.footer) == 0
        assert len(categories.other) == 0

    def test_categorize_navigation(self):
        """_categorize_links puts nav/header links in navigation."""
        extractor = LinkExtractor()
        links = [
            ExtractedLink(url="https://example.com/1", text="", is_external=False, source_element="nav"),
            ExtractedLink(url="https://example.com/2", text="", is_external=False, source_element="header"),
        ]

        categories = extractor._categorize_links(links)

        assert len(categories.navigation) == 2
        assert len(categories.main_content) == 0

    def test_categorize_sidebar(self):
        """_categorize_links puts aside links in sidebar."""
        extractor = LinkExtractor()
        links = [
            ExtractedLink(url="https://example.com/1", text="", is_external=False, source_element="aside"),
        ]

        categories = extractor._categorize_links(links)

        assert len(categories.sidebar) == 1

    def test_categorize_footer(self):
        """_categorize_links puts footer links in footer."""
        extractor = LinkExtractor()
        links = [
            ExtractedLink(url="https://example.com/1", text="", is_external=False, source_element="footer"),
        ]

        categories = extractor._categorize_links(links)

        assert len(categories.footer) == 1

    def test_categorize_other(self):
        """_categorize_links puts unknown source elements in other."""
        extractor = LinkExtractor()
        links = [
            ExtractedLink(url="https://example.com/1", text="", is_external=False, source_element="other"),
            ExtractedLink(url="https://example.com/2", text="", is_external=False, source_element="div"),
        ]

        categories = extractor._categorize_links(links)

        assert len(categories.other) == 2

    def test_categorize_empty_list(self):
        """_categorize_links handles empty list."""
        extractor = LinkExtractor()
        categories = extractor._categorize_links([])

        assert categories.main_content == []
        assert categories.navigation == []
        assert categories.sidebar == []
        assert categories.footer == []
        assert categories.other == []


# -----------------------------------------------------------------------------
# Integration Tests for extract method
# -----------------------------------------------------------------------------


class TestExtractMethod:
    """Integration tests for the main extract method."""

    @pytest.mark.asyncio
    async def test_extract_success(self):
        """extract() returns ExtractedLinksResult on success."""
        extractor = LinkExtractor()

        # Mock _fetch_page using patch
        with patch.object(extractor, "_fetch_page", new_callable=AsyncMock, return_value=SEMANTIC_HTML):
            result = await extractor.extract("https://example.com")

        assert isinstance(result, ExtractedLinksResult)
        assert result.source_url == "https://example.com"
        assert result.page_title == "Semantic Page"
        assert result.link_count > 0
        assert isinstance(result.extracted_at, datetime)

    @pytest.mark.asyncio
    async def test_extract_filters_external(self):
        """extract(include_external=False) excludes external links."""
        extractor = LinkExtractor()

        with patch.object(extractor, "_fetch_page", new_callable=AsyncMock, return_value=SIMPLE_HTML):
            result = await extractor.extract("https://example.com", include_external=False)

        # Only internal link should remain
        all_links = (
            result.categories.main_content +
            result.categories.navigation +
            result.categories.sidebar +
            result.categories.footer +
            result.categories.other
        )
        assert all(not link.is_external for link in all_links)

    @pytest.mark.asyncio
    async def test_extract_page_without_title(self):
        """extract() handles pages without title tag."""
        extractor = LinkExtractor()

        with patch.object(extractor, "_fetch_page", new_callable=AsyncMock, return_value=HTML_NO_TITLE):
            result = await extractor.extract("https://example.com")

        assert result.page_title is None

    @pytest.mark.asyncio
    async def test_extract_categorizes_correctly(self):
        """extract() correctly categorizes links by source element."""
        extractor = LinkExtractor()

        with patch.object(extractor, "_fetch_page", new_callable=AsyncMock, return_value=SEMANTIC_HTML):
            result = await extractor.extract("https://example.com")

        # Check categories are populated
        assert len(result.categories.navigation) >= 2  # nav and header links
        assert len(result.categories.main_content) >= 1  # main/article links
        assert len(result.categories.sidebar) >= 1  # aside links
        assert len(result.categories.footer) >= 1  # footer links
        assert len(result.categories.other) >= 1  # div links


# -----------------------------------------------------------------------------
# Error Handling Tests
# -----------------------------------------------------------------------------


class TestLinkExtractionError:
    """Tests for LinkExtractionError exception."""

    def test_error_has_url(self):
        """LinkExtractionError stores the URL."""
        error = LinkExtractionError("Test error", "https://example.com")
        assert error.url == "https://example.com"
        assert str(error) == "Test error"

    def test_error_has_cause(self):
        """LinkExtractionError stores the cause exception."""
        cause = ValueError("Original error")
        error = LinkExtractionError("Wrapped error", "https://example.com", cause)
        assert error.cause is cause


class TestFetchPageErrors:
    """Tests for error handling in _fetch_page."""

    @pytest.mark.asyncio
    async def test_fetch_timeout_raises_error(self):
        """_fetch_page raises LinkExtractionError on timeout."""
        extractor = LinkExtractor()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(LinkExtractionError) as exc_info:
                await extractor._fetch_page("https://example.com")

        assert "timed out" in str(exc_info.value).lower()
        assert exc_info.value.url == "https://example.com"
        assert isinstance(exc_info.value.cause, httpx.TimeoutException)

    @pytest.mark.asyncio
    async def test_fetch_too_many_redirects_raises_error(self):
        """_fetch_page raises LinkExtractionError on too many redirects."""
        extractor = LinkExtractor()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get = AsyncMock(side_effect=httpx.TooManyRedirects("Too many redirects"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(LinkExtractionError) as exc_info:
                await extractor._fetch_page("https://example.com")

        assert "redirects" in str(exc_info.value).lower()
        assert exc_info.value.url == "https://example.com"

    @pytest.mark.asyncio
    async def test_fetch_http_error_raises_error(self):
        """_fetch_page raises LinkExtractionError on HTTP error status."""
        extractor = LinkExtractor()

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.reason_phrase = "Not Found"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "HTTP 404", request=MagicMock(), response=mock_response
            )
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(LinkExtractionError) as exc_info:
                await extractor._fetch_page("https://example.com")

        assert "404" in str(exc_info.value)
        assert exc_info.value.url == "https://example.com"

    @pytest.mark.asyncio
    async def test_fetch_connection_error_raises_error(self):
        """_fetch_page raises LinkExtractionError on connection error."""
        extractor = LinkExtractor()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.get = AsyncMock(
            side_effect=httpx.RequestError("Connection refused")
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(LinkExtractionError) as exc_info:
                await extractor._fetch_page("https://example.com")

        assert "Request failed" in str(exc_info.value)
        assert exc_info.value.url == "https://example.com"


class TestExtractErrorPropagation:
    """Tests for error propagation in extract method."""

    @pytest.mark.asyncio
    async def test_extract_propagates_fetch_error(self):
        """extract() propagates LinkExtractionError from _fetch_page."""
        extractor = LinkExtractor()

        with patch.object(
            extractor,
            "_fetch_page",
            new_callable=AsyncMock,
            side_effect=LinkExtractionError("Fetch failed", "https://example.com"),
        ):
            with pytest.raises(LinkExtractionError):
                await extractor.extract("https://example.com")
