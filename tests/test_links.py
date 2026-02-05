"""Integration tests for the extract-links endpoint.

Tests cover:
- POST /api/v1/content/extract-links endpoint
- Success responses with categorized links
- Error handling (invalid URLs, extraction failures)
- include_external parameter
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - ensure models registered with Base.metadata
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.link_extractor import (
    CategorizedLinks,
    ExtractedLink,
    ExtractedLinksResult,
    LinkExtractionError,
    LinkExtractor,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture()
def db_engine():
    """Create an in-memory SQLite engine."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def client(db_engine) -> TestClient:
    """TestClient with overridden DB dependency."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )

    def _override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


# -----------------------------------------------------------------------------
# Mock Result Fixtures
# -----------------------------------------------------------------------------


def _create_mock_result(
    source_url: str = "https://example.com",
    page_title: str = "Test Page",
    main_content: list[ExtractedLink] | None = None,
    navigation: list[ExtractedLink] | None = None,
    sidebar: list[ExtractedLink] | None = None,
    footer: list[ExtractedLink] | None = None,
    other: list[ExtractedLink] | None = None,
) -> ExtractedLinksResult:
    """Create a mock ExtractedLinksResult for testing."""
    categories = CategorizedLinks(
        main_content=main_content or [],
        navigation=navigation or [],
        sidebar=sidebar or [],
        footer=footer or [],
        other=other or [],
    )

    total_links = (
        len(categories.main_content) +
        len(categories.navigation) +
        len(categories.sidebar) +
        len(categories.footer) +
        len(categories.other)
    )

    return ExtractedLinksResult(
        source_url=source_url,
        page_title=page_title,
        categories=categories,
        link_count=total_links,
        extracted_at=datetime.now(timezone.utc),
    )


# -----------------------------------------------------------------------------
# Success Tests
# -----------------------------------------------------------------------------


class TestExtractLinksEndpoint:
    """Tests for POST /api/v1/content/extract-links."""

    def test_extract_links_success(self, client: TestClient):
        """POST with valid URL returns 200 with categorized links."""
        mock_result = _create_mock_result(
            source_url="https://example.com",
            page_title="Example Page",
            main_content=[
                ExtractedLink(
                    url="https://example.com/article",
                    text="Article Link",
                    is_external=False,
                    source_element="main",
                ),
            ],
            navigation=[
                ExtractedLink(
                    url="https://example.com/home",
                    text="Home",
                    is_external=False,
                    source_element="nav",
                ),
            ],
        )

        with patch.object(
            LinkExtractor,
            "extract",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client.post(
                "/api/v1/content/extract-links",
                json={"url": "https://example.com"},
            )

        assert response.status_code == 200
        data = response.json()

        assert data["source_url"] == "https://example.com"
        assert data["page_title"] == "Example Page"
        assert data["link_count"] == 2
        assert "extracted_at" in data
        assert "categories" in data

        # Check categories structure
        categories = data["categories"]
        assert len(categories["main_content"]) == 1
        assert len(categories["navigation"]) == 1
        assert categories["main_content"][0]["url"] == "https://example.com/article"
        assert categories["navigation"][0]["url"] == "https://example.com/home"

    def test_extract_links_returns_all_categories(self, client: TestClient):
        """POST returns all five link categories."""
        mock_result = _create_mock_result(
            main_content=[ExtractedLink(url="https://example.com/main", text="", is_external=False, source_element="main")],
            navigation=[ExtractedLink(url="https://example.com/nav", text="", is_external=False, source_element="nav")],
            sidebar=[ExtractedLink(url="https://example.com/side", text="", is_external=False, source_element="aside")],
            footer=[ExtractedLink(url="https://example.com/foot", text="", is_external=False, source_element="footer")],
            other=[ExtractedLink(url="https://example.com/other", text="", is_external=False, source_element="other")],
        )

        with patch.object(
            LinkExtractor,
            "extract",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client.post(
                "/api/v1/content/extract-links",
                json={"url": "https://example.com"},
            )

        assert response.status_code == 200
        categories = response.json()["categories"]

        assert "main_content" in categories
        assert "navigation" in categories
        assert "sidebar" in categories
        assert "footer" in categories
        assert "other" in categories

    def test_extract_links_with_include_external_false(self, client: TestClient):
        """POST with include_external=false passes parameter to extractor."""
        mock_result = _create_mock_result()

        with patch.object(
            LinkExtractor,
            "extract",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_extract:
            response = client.post(
                "/api/v1/content/extract-links",
                json={"url": "https://example.com", "include_external": False},
            )

        assert response.status_code == 200
        mock_extract.assert_called_once_with("https://example.com/", include_external=False)

    def test_extract_links_include_external_default_true(self, client: TestClient):
        """POST without include_external defaults to true."""
        mock_result = _create_mock_result()

        with patch.object(
            LinkExtractor,
            "extract",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_extract:
            response = client.post(
                "/api/v1/content/extract-links",
                json={"url": "https://example.com"},
            )

        assert response.status_code == 200
        mock_extract.assert_called_once_with("https://example.com/", include_external=True)


# -----------------------------------------------------------------------------
# Error Handling Tests
# -----------------------------------------------------------------------------


class TestExtractLinksErrors:
    """Tests for error handling in extract-links endpoint."""

    def test_extract_links_invalid_url_format(self, client: TestClient):
        """POST with invalid URL format returns 422 validation error."""
        response = client.post(
            "/api/v1/content/extract-links",
            json={"url": "not-a-valid-url"},
        )

        assert response.status_code == 422

    def test_extract_links_extraction_error(self, client: TestClient):
        """POST returns 400 when extraction fails."""
        with patch.object(
            LinkExtractor,
            "extract",
            new_callable=AsyncMock,
            side_effect=LinkExtractionError(
                "Failed to fetch page",
                "https://example.com",
            ),
        ):
            response = client.post(
                "/api/v1/content/extract-links",
                json={"url": "https://example.com"},
            )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error"]["code"] == "EXTRACTION_FAILED"

    def test_extract_links_timeout_error(self, client: TestClient):
        """POST returns 400 with TIMEOUT code on timeout."""
        import httpx

        timeout_cause = httpx.TimeoutException("Request timed out")
        error = LinkExtractionError(
            "Request timed out after 30s",
            "https://example.com",
            timeout_cause,
        )

        with patch.object(
            LinkExtractor,
            "extract",
            new_callable=AsyncMock,
            side_effect=error,
        ):
            response = client.post(
                "/api/v1/content/extract-links",
                json={"url": "https://example.com"},
            )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"]["code"] == "TIMEOUT"

    def test_extract_links_missing_url(self, client: TestClient):
        """POST without URL returns 422 validation error."""
        response = client.post(
            "/api/v1/content/extract-links",
            json={},
        )

        assert response.status_code == 422
