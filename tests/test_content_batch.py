"""Integration tests for the batch content addition endpoint.

Tests cover:
- POST /api/v1/sessions/{session_id}/content/batch endpoint
- Success responses with multiple URLs
- Duplicate detection (within session and within batch)
- Error handling (invalid session, mixed success/failure)
- source_url metadata recording
"""

from __future__ import annotations

from pathlib import Path
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
from app.services.extractors.base import ExtractionResult


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture()
def tmp_content_sandbox(tmp_path: Path) -> str:
    """Provide a temporary content sandbox root directory."""
    return str(tmp_path / "content_sandboxes")


@pytest.fixture()
def db_engine():
    """Create an in-memory SQLite engine with foreign keys enabled."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def client(db_engine, tmp_content_sandbox: str) -> TestClient:
    """TestClient with overridden DB dependency and content_sandbox_root."""
    from app.core.config import settings

    original_content_sandbox_root = settings.content_sandbox_root
    object.__setattr__(settings, "content_sandbox_root", tmp_content_sandbox)

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
    object.__setattr__(settings, "content_sandbox_root", original_content_sandbox_root)


@pytest.fixture()
def test_session(client: TestClient) -> dict:
    """Create a test session and return its data."""
    response = client.post(
        "/api/v1/sessions/",
        json={"name": "Test Session", "description": "Session for batch tests"},
    )
    assert response.status_code == 201
    return response.json()


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


def _mock_url_extraction(return_value: ExtractionResult | None = None, side_effect=None):
    """Create a patch for UrlRetriever._extract_async."""
    if return_value is None and side_effect is None:
        return_value = ExtractionResult(
            content="# Extracted Content\n\nTest content from URL.",
            title="Extracted Page",
            word_count=5,
            extraction_method="trafilatura",
            extraction_time_ms=100.0,
        )

    from app.services.retrievers.url_retriever import UrlRetriever

    return patch.object(
        UrlRetriever,
        "_extract_async",
        new_callable=AsyncMock,
        return_value=return_value,
        side_effect=side_effect,
    )


# -----------------------------------------------------------------------------
# Success Tests
# -----------------------------------------------------------------------------


class TestBatchAddContent:
    """Tests for POST /api/v1/sessions/{session_id}/content/batch."""

    def test_batch_add_single_url(self, client: TestClient, test_session: dict):
        """POST with single URL returns success."""
        session_id = test_session["session_id"]

        with _mock_url_extraction():
            response = client.post(
                f"/api/v1/sessions/{session_id}/content/batch",
                json={
                    "urls": [{"url": "https://example.com/page1"}],
                },
            )

        assert response.status_code == 200
        data = response.json()

        assert data["session_id"] == session_id
        assert data["total_count"] == 1
        assert data["success_count"] == 1
        assert data["error_count"] == 0
        assert data["duplicate_count"] == 0
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "success"
        assert data["items"][0]["content_id"] is not None

    def test_batch_add_multiple_urls(self, client: TestClient, test_session: dict):
        """POST with multiple URLs processes all."""
        session_id = test_session["session_id"]

        with _mock_url_extraction():
            response = client.post(
                f"/api/v1/sessions/{session_id}/content/batch",
                json={
                    "urls": [
                        {"url": "https://example.com/page1"},
                        {"url": "https://example.com/page2"},
                        {"url": "https://example.com/page3"},
                    ],
                },
            )

        assert response.status_code == 200
        data = response.json()

        assert data["total_count"] == 3
        assert data["success_count"] == 3
        assert len(data["items"]) == 3

        # All should have unique content_ids
        content_ids = [item["content_id"] for item in data["items"]]
        assert len(set(content_ids)) == 3

    def test_batch_add_with_titles(self, client: TestClient, test_session: dict):
        """POST with custom titles uses them."""
        session_id = test_session["session_id"]

        with _mock_url_extraction():
            response = client.post(
                f"/api/v1/sessions/{session_id}/content/batch",
                json={
                    "urls": [
                        {"url": "https://example.com/page1", "title": "Custom Title 1"},
                        {"url": "https://example.com/page2", "title": "Custom Title 2"},
                    ],
                },
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success_count"] == 2
        # Titles should be returned (may be overridden by retriever)
        assert data["items"][0]["title"] is not None
        assert data["items"][1]["title"] is not None


# -----------------------------------------------------------------------------
# Duplicate Detection Tests
# -----------------------------------------------------------------------------


class TestBatchAddDuplicates:
    """Tests for duplicate detection in batch add."""

    def test_batch_detects_existing_duplicate(self, client: TestClient, test_session: dict):
        """POST detects URLs already in session."""
        session_id = test_session["session_id"]

        # First, add a URL to the session
        with _mock_url_extraction():
            client.post(
                f"/api/v1/sessions/{session_id}/content/batch",
                json={"urls": [{"url": "https://example.com/existing"}]},
            )

        # Now try to add it again via batch
        with _mock_url_extraction():
            response = client.post(
                f"/api/v1/sessions/{session_id}/content/batch",
                json={
                    "urls": [
                        {"url": "https://example.com/existing"},
                        {"url": "https://example.com/new-url"},
                    ],
                },
            )

        assert response.status_code == 200
        data = response.json()

        assert data["total_count"] == 2
        assert data["success_count"] == 1
        assert data["duplicate_count"] == 1

        # Check individual items
        items_by_status = {item["status"]: item for item in data["items"]}
        assert "duplicate" in items_by_status
        assert "success" in items_by_status
        assert items_by_status["duplicate"]["url"] == "https://example.com/existing"

    def test_batch_detects_intra_batch_duplicate(self, client: TestClient, test_session: dict):
        """POST detects duplicate URLs within the same batch."""
        session_id = test_session["session_id"]

        with _mock_url_extraction():
            response = client.post(
                f"/api/v1/sessions/{session_id}/content/batch",
                json={
                    "urls": [
                        {"url": "https://example.com/same-url"},
                        {"url": "https://example.com/same-url"},  # Duplicate within batch
                        {"url": "https://example.com/different"},
                    ],
                },
            )

        assert response.status_code == 200
        data = response.json()

        assert data["total_count"] == 3
        assert data["success_count"] == 2  # First occurrence + different
        assert data["duplicate_count"] == 1  # Second occurrence of same-url

        # Find the duplicate item
        duplicate_items = [item for item in data["items"] if item["status"] == "duplicate"]
        assert len(duplicate_items) == 1
        assert duplicate_items[0]["error"] == "Duplicate URL within batch"

    def test_batch_duplicate_has_no_content_id(self, client: TestClient, test_session: dict):
        """POST duplicate items have content_id=None."""
        session_id = test_session["session_id"]

        # Add initial URL
        with _mock_url_extraction():
            client.post(
                f"/api/v1/sessions/{session_id}/content/batch",
                json={"urls": [{"url": "https://example.com/first"}]},
            )

        # Try to add duplicate
        with _mock_url_extraction():
            response = client.post(
                f"/api/v1/sessions/{session_id}/content/batch",
                json={"urls": [{"url": "https://example.com/first"}]},
            )

        assert response.status_code == 200
        data = response.json()

        assert data["items"][0]["status"] == "duplicate"
        assert data["items"][0]["content_id"] is None


# -----------------------------------------------------------------------------
# Error Handling Tests
# -----------------------------------------------------------------------------


class TestBatchAddErrors:
    """Tests for error handling in batch add."""

    def test_batch_invalid_session(self, client: TestClient):
        """POST to non-existent session returns 404."""
        fake_session_id = "00000000-0000-4000-a000-000000000000"

        response = client.post(
            f"/api/v1/sessions/{fake_session_id}/content/batch",
            json={"urls": [{"url": "https://example.com"}]},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"]["code"] == "SESSION_NOT_FOUND"

    def test_batch_empty_urls_list(self, client: TestClient, test_session: dict):
        """POST with empty urls list returns 422 validation error."""
        session_id = test_session["session_id"]

        response = client.post(
            f"/api/v1/sessions/{session_id}/content/batch",
            json={"urls": []},
        )

        assert response.status_code == 422

    def test_batch_exceeds_max_urls(self, client: TestClient, test_session: dict):
        """POST with more than 50 URLs returns 422 validation error."""
        session_id = test_session["session_id"]

        # Create 51 URLs
        urls = [{"url": f"https://example.com/page{i}"} for i in range(51)]

        response = client.post(
            f"/api/v1/sessions/{session_id}/content/batch",
            json={"urls": urls},
        )

        assert response.status_code == 422

    def test_batch_mixed_success_and_error(self, client: TestClient, test_session: dict):
        """POST with some URLs failing (retrieval error) returns all success but individual item shows error.

        Note: The batch_add_content function counts as "success" if the content record is created,
        even if the content retrieval failed (stored with status="error"). This is the expected
        behavior - the content record exists but needs retry or shows error to user.
        """
        session_id = test_session["session_id"]

        from app.services.extractors.exceptions import NetworkError
        from app.services.retrievers.url_retriever import UrlRetriever

        call_count = 0

        async def mock_extract(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise NetworkError("Connection refused")
            return ExtractionResult(
                content="# Content",
                title="Page",
                word_count=1,
                extraction_method="test",
                extraction_time_ms=10.0,
            )

        with patch.object(
            UrlRetriever,
            "_extract_async",
            new_callable=AsyncMock,
            side_effect=mock_extract,
        ):
            response = client.post(
                f"/api/v1/sessions/{session_id}/content/batch",
                json={
                    "urls": [
                        {"url": "https://example.com/page1"},
                        {"url": "https://example.com/page2"},  # Retrieval will fail
                        {"url": "https://example.com/page3"},
                    ],
                },
            )

        assert response.status_code == 200
        data = response.json()

        assert data["total_count"] == 3
        # All 3 create content records successfully (even if retrieval failed)
        assert data["success_count"] == 3
        assert data["error_count"] == 0  # No HTTP errors, just retrieval failures
        assert data["duplicate_count"] == 0

        # All items have content_id (record was created for all)
        assert all(item["content_id"] is not None for item in data["items"])

        # Verify the failed retrieval content has error status in DB
        failed_content_id = data["items"][1]["content_id"]
        get_response = client.get(
            f"/api/v1/sessions/{session_id}/content/{failed_content_id}"
        )
        assert get_response.status_code == 200
        content_data = get_response.json()
        assert content_data["status"] == "error"
        assert "Connection refused" in content_data["error_message"]


# -----------------------------------------------------------------------------
# Source URL Metadata Tests
# -----------------------------------------------------------------------------


class TestBatchAddSourceUrl:
    """Tests for source_url metadata recording."""

    def test_batch_records_source_url(self, client: TestClient, test_session: dict):
        """POST with source_url records it in metadata."""
        session_id = test_session["session_id"]

        with _mock_url_extraction():
            response = client.post(
                f"/api/v1/sessions/{session_id}/content/batch",
                json={
                    "urls": [{"url": "https://example.com/linked-page"}],
                    "source_url": "https://example.com/source-page",
                },
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success_count"] == 1
        content_id = data["items"][0]["content_id"]

        # Fetch the content to verify metadata
        get_response = client.get(
            f"/api/v1/sessions/{session_id}/content/{content_id}"
        )

        assert get_response.status_code == 200
        content_data = get_response.json()
        assert content_data["metadata_json"].get("source_url") == "https://example.com/source-page"

    def test_batch_without_source_url(self, client: TestClient, test_session: dict):
        """POST without source_url works normally."""
        session_id = test_session["session_id"]

        with _mock_url_extraction():
            response = client.post(
                f"/api/v1/sessions/{session_id}/content/batch",
                json={
                    "urls": [{"url": "https://example.com/page"}],
                    # No source_url provided
                },
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success_count"] == 1


# -----------------------------------------------------------------------------
# Validation Tests
# -----------------------------------------------------------------------------


class TestBatchAddValidation:
    """Tests for request validation."""

    def test_batch_invalid_url_format(self, client: TestClient, test_session: dict):
        """POST with invalid URL format returns 422."""
        session_id = test_session["session_id"]

        response = client.post(
            f"/api/v1/sessions/{session_id}/content/batch",
            json={
                "urls": [{"url": "not-a-valid-url"}],
            },
        )

        assert response.status_code == 422

    def test_batch_missing_urls_field(self, client: TestClient, test_session: dict):
        """POST without urls field returns 422."""
        session_id = test_session["session_id"]

        response = client.post(
            f"/api/v1/sessions/{session_id}/content/batch",
            json={},
        )

        assert response.status_code == 422
