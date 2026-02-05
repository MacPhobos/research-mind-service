"""Link extraction and categorization service for web pages."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from bs4.element import Tag

logger = logging.getLogger(__name__)

# Semantic elements for source detection (order matters for priority)
SEMANTIC_ELEMENTS = frozenset({"nav", "main", "article", "aside", "footer", "header"})


@dataclass(frozen=True)
class ExtractedLink:
    """A single extracted link with metadata."""

    url: str
    text: str
    is_external: bool
    source_element: str  # nav, main, aside, footer, header, other


@dataclass
class CategorizedLinks:
    """Links categorized by their source element."""

    main_content: list[ExtractedLink] = field(default_factory=list)
    navigation: list[ExtractedLink] = field(default_factory=list)
    sidebar: list[ExtractedLink] = field(default_factory=list)
    footer: list[ExtractedLink] = field(default_factory=list)
    other: list[ExtractedLink] = field(default_factory=list)


@dataclass
class ExtractedLinksResult:
    """Result of link extraction from a web page."""

    source_url: str
    page_title: str | None
    categories: CategorizedLinks
    link_count: int
    extracted_at: datetime


class LinkExtractionError(Exception):
    """Raised when link extraction fails."""

    def __init__(self, message: str, url: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.url = url
        self.cause = cause


class LinkExtractor:
    """Extract and categorize links from web pages.

    Usage:
        extractor = LinkExtractor()
        result = await extractor.extract("https://example.com")
        for link in result.categories.main_content:
            print(f"{link.text}: {link.url}")
    """

    # HTTP client timeout in seconds
    TIMEOUT_SECONDS = 30.0
    # Maximum redirects to follow
    MAX_REDIRECTS = 5
    # Maximum text length for link text
    MAX_TEXT_LENGTH = 255

    async def extract(
        self, url: str, include_external: bool = True
    ) -> ExtractedLinksResult:
        """Extract and categorize all links from a web page.

        Args:
            url: The URL to extract links from.
            include_external: Whether to include external links (default True).

        Returns:
            ExtractedLinksResult with categorized links.

        Raises:
            LinkExtractionError: If page fetch or parsing fails.
        """
        logger.info("Extracting links from %s", url)

        html = await self._fetch_page(url)
        links = self._parse_links(html, url)

        # Filter external links if requested
        if not include_external:
            links = [link for link in links if not link.is_external]

        categories = self._categorize_links(links)

        # Extract page title
        soup = BeautifulSoup(html, "lxml")
        title_tag = soup.find("title")
        page_title = title_tag.get_text(strip=True) if title_tag else None

        result = ExtractedLinksResult(
            source_url=url,
            page_title=page_title,
            categories=categories,
            link_count=len(links),
            extracted_at=datetime.now(timezone.utc),
        )

        logger.info(
            "Extracted %d links from %s (main=%d, nav=%d, sidebar=%d, footer=%d, other=%d)",
            result.link_count,
            url,
            len(categories.main_content),
            len(categories.navigation),
            len(categories.sidebar),
            len(categories.footer),
            len(categories.other),
        )

        return result

    async def _fetch_page(self, url: str) -> str:
        """Fetch HTML content from a URL.

        Args:
            url: The URL to fetch.

        Returns:
            HTML content as string.

        Raises:
            LinkExtractionError: If the request fails.
        """
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.TIMEOUT_SECONDS),
                follow_redirects=True,
                max_redirects=self.MAX_REDIRECTS,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
        except httpx.TimeoutException as e:
            raise LinkExtractionError(
                f"Request timed out after {self.TIMEOUT_SECONDS}s", url, e
            ) from e
        except httpx.TooManyRedirects as e:
            raise LinkExtractionError(
                f"Too many redirects (max {self.MAX_REDIRECTS})", url, e
            ) from e
        except httpx.HTTPStatusError as e:
            raise LinkExtractionError(
                f"HTTP error {e.response.status_code}: {e.response.reason_phrase}",
                url,
                e,
            ) from e
        except httpx.RequestError as e:
            raise LinkExtractionError(f"Request failed: {e}", url, e) from e

    def _parse_links(self, html: str, base_url: str) -> list[ExtractedLink]:
        """Parse all links from HTML content.

        Args:
            html: HTML content to parse.
            base_url: Base URL for resolving relative links.

        Returns:
            List of extracted links (deduplicated by URL).
        """
        soup = BeautifulSoup(html, "lxml")
        base_domain = urlparse(base_url).netloc

        seen_urls: set[str] = set()
        links: list[ExtractedLink] = []

        for anchor in soup.find_all("a", href=True):
            href_attr = anchor.get("href", "")

            # Handle href attribute (can be str or list in edge cases)
            if isinstance(href_attr, list):
                href = href_attr[0] if href_attr else ""
            else:
                href = href_attr or ""

            # Skip empty hrefs
            if not href or href.isspace():
                continue

            # Skip non-HTTP links (javascript:, mailto:, tel:, etc.)
            if href.startswith(("javascript:", "mailto:", "tel:", "#", "data:")):
                continue

            # Resolve relative URLs
            absolute_url = urljoin(base_url, href)

            # Validate URL scheme
            parsed = urlparse(absolute_url)
            if parsed.scheme not in ("http", "https"):
                continue

            # Skip if already seen (deduplicate)
            if absolute_url in seen_urls:
                continue
            seen_urls.add(absolute_url)

            # Determine if external
            link_domain = parsed.netloc
            is_external = link_domain != base_domain

            # Extract and truncate link text
            text = anchor.get_text(strip=True)
            if len(text) > self.MAX_TEXT_LENGTH:
                text = text[: self.MAX_TEXT_LENGTH - 3] + "..."

            # Determine source element
            source_element = self._get_source_element(anchor)

            links.append(
                ExtractedLink(
                    url=absolute_url,
                    text=text,
                    is_external=is_external,
                    source_element=source_element,
                )
            )

        return links

    def _get_source_element(self, anchor: Tag) -> str:
        """Determine the semantic source element for a link.

        Walks up the DOM tree to find the nearest semantic parent element.

        Args:
            anchor: The anchor tag to find the source for.

        Returns:
            Source element name: nav, main, article, aside, footer, header, or other.
        """
        # Walk up the parent tree
        parent = anchor.parent
        while parent is not None:
            tag_name = getattr(parent, "name", None)
            if tag_name in SEMANTIC_ELEMENTS:
                return tag_name
            parent = getattr(parent, "parent", None)

        return "other"

    def _categorize_links(self, links: list[ExtractedLink]) -> CategorizedLinks:
        """Categorize links by their source element.

        Args:
            links: List of extracted links.

        Returns:
            CategorizedLinks with links sorted into categories.
        """
        categories = CategorizedLinks()

        for link in links:
            match link.source_element:
                case "main" | "article":
                    categories.main_content.append(link)
                case "nav" | "header":
                    categories.navigation.append(link)
                case "aside":
                    categories.sidebar.append(link)
                case "footer":
                    categories.footer.append(link)
                case _:
                    categories.other.append(link)

        return categories
