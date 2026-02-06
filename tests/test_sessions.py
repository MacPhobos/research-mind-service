"""Tests for session management endpoints (Phase 1.2)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  -- ensure models registered with Base.metadata
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def tmp_content_sandbox(tmp_path):
    """Provide a temporary content sandbox root directory."""
    return str(tmp_path / "content_sandboxes")


@pytest.fixture()
def db_engine():
    """Create an in-memory SQLite engine shared across connections."""
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
def db_session(db_engine):
    """Yield a SQLAlchemy session bound to the shared in-memory engine."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client(db_engine, tmp_content_sandbox):
    """TestClient with overridden DB dependency and content_sandbox_root."""
    from app.core.config import settings

    # Override content_sandbox_root (bypass pydantic model immutability)
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


# ------------------------------------------------------------------
# POST /api/v1/sessions
# ------------------------------------------------------------------


class TestCreateSession:
    def test_create_session(self, client: TestClient, tmp_content_sandbox: str):
        response = client.post(
            "/api/v1/sessions/",
            json={"name": "My Session", "description": "Test description"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Session"
        assert data["description"] == "Test description"
        assert data["status"] == "active"
        assert data["archived"] is False
        assert "session_id" in data
        assert "workspace_path" in data
        assert "created_at" in data
        assert "last_accessed" in data
        # Workspace directory should have been created
        assert os.path.isdir(data["workspace_path"])

    def test_create_session_creates_claude_md(
        self, client: TestClient, tmp_content_sandbox: str
    ):
        """Verify that CLAUDE.md is created in the sandbox directory with correct content."""
        response = client.post(
            "/api/v1/sessions/",
            json={"name": "Claude MD Session"},
        )
        assert response.status_code == 201
        data = response.json()
        workspace_path = data["workspace_path"]

        # CLAUDE.md should exist in the workspace directory
        claude_md_path = os.path.join(workspace_path, "CLAUDE.md")
        assert os.path.isfile(claude_md_path), "CLAUDE.md should exist in sandbox"

        # Verify the content matches the expected template
        with open(claude_md_path, "r") as f:
            content = f.read()

        expected_content = """You are a research assistant responsible for answering questions based on the content stored in this sandbox directory.
Use the content to provide accurate and relevant answers.
"""
        assert content == expected_content, "CLAUDE.md content should match template"

    def test_create_session_minimal(self, client: TestClient):
        response = client.post(
            "/api/v1/sessions/",
            json={"name": "Minimal"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal"
        assert data["description"] is None

    def test_create_session_no_name(self, client: TestClient):
        response = client.post("/api/v1/sessions/", json={})
        assert response.status_code == 422

    def test_create_session_empty_name(self, client: TestClient):
        response = client.post("/api/v1/sessions/", json={"name": ""})
        assert response.status_code == 422

    def test_create_session_name_too_long(self, client: TestClient):
        response = client.post("/api/v1/sessions/", json={"name": "x" * 256})
        assert response.status_code == 422


# ------------------------------------------------------------------
# GET /api/v1/sessions/{session_id}
# ------------------------------------------------------------------


class TestGetSession:
    def test_get_session(self, client: TestClient):
        # Create first
        create_resp = client.post("/api/v1/sessions/", json={"name": "Fetched Session"})
        session_id = create_resp.json()["session_id"]

        # Fetch
        response = client.get(f"/api/v1/sessions/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["name"] == "Fetched Session"

    def test_get_session_not_found(self, client: TestClient):
        response = client.get("/api/v1/sessions/00000000-0000-4000-a000-000000000000")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"]["code"] == "SESSION_NOT_FOUND"


# ------------------------------------------------------------------
# GET /api/v1/sessions
# ------------------------------------------------------------------


class TestListSessions:
    def test_list_sessions_empty(self, client: TestClient):
        response = client.get("/api/v1/sessions/")
        assert response.status_code == 200
        data = response.json()
        assert data["sessions"] == []
        assert data["count"] == 0

    def test_list_sessions(self, client: TestClient):
        client.post("/api/v1/sessions/", json={"name": "S1"})
        client.post("/api/v1/sessions/", json={"name": "S2"})
        client.post("/api/v1/sessions/", json={"name": "S3"})

        response = client.get("/api/v1/sessions/")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3
        assert len(data["sessions"]) == 3

    def test_list_sessions_pagination(self, client: TestClient):
        for i in range(5):
            client.post("/api/v1/sessions/", json={"name": f"S{i}"})

        response = client.get("/api/v1/sessions/?limit=2&offset=0")
        data = response.json()
        assert len(data["sessions"]) == 2
        assert data["count"] == 5

        response2 = client.get("/api/v1/sessions/?limit=2&offset=4")
        data2 = response2.json()
        assert len(data2["sessions"]) == 1
        assert data2["count"] == 5


# ------------------------------------------------------------------
# DELETE /api/v1/sessions/{session_id}
# ------------------------------------------------------------------


class TestDeleteSession:
    def test_delete_session(self, client: TestClient):
        create_resp = client.post("/api/v1/sessions/", json={"name": "To Delete"})
        session_id = create_resp.json()["session_id"]
        workspace = create_resp.json()["workspace_path"]

        # Workspace dir should exist
        assert os.path.isdir(workspace)

        # Delete
        response = client.delete(f"/api/v1/sessions/{session_id}")
        assert response.status_code == 204

        # Workspace dir should be removed
        assert not os.path.isdir(workspace)

        # GET should 404
        get_resp = client.get(f"/api/v1/sessions/{session_id}")
        assert get_resp.status_code == 404

    def test_delete_session_not_found(self, client: TestClient):
        response = client.delete(
            "/api/v1/sessions/00000000-0000-4000-a000-000000000000"
        )
        assert response.status_code == 404


# ------------------------------------------------------------------
# Session isolation
# ------------------------------------------------------------------


class TestSessionIsolation:
    def test_multiple_sessions_coexist(self, client: TestClient):
        ids = []
        for i in range(3):
            resp = client.post("/api/v1/sessions/", json={"name": f"Isolated {i}"})
            ids.append(resp.json()["session_id"])

        # All three should be independently accessible
        for sid in ids:
            resp = client.get(f"/api/v1/sessions/{sid}")
            assert resp.status_code == 200

        # Delete one should not affect others
        client.delete(f"/api/v1/sessions/{ids[1]}")

        assert client.get(f"/api/v1/sessions/{ids[0]}").status_code == 200
        assert client.get(f"/api/v1/sessions/{ids[1]}").status_code == 404
        assert client.get(f"/api/v1/sessions/{ids[2]}").status_code == 200


# ------------------------------------------------------------------
# is_indexed reflects filesystem
# ------------------------------------------------------------------


class TestIsIndexed:
    def test_is_indexed_false_by_default(self, client: TestClient):
        resp = client.post("/api/v1/sessions/", json={"name": "Not Indexed"})
        assert resp.status_code == 201
        assert resp.json()["is_indexed"] is False

    def test_is_indexed_true_when_dir_exists(self, client: TestClient):
        resp = client.post("/api/v1/sessions/", json={"name": "Indexed"})
        data = resp.json()
        workspace = data["workspace_path"]
        session_id = data["session_id"]

        # Simulate indexing by creating the directory
        os.makedirs(os.path.join(workspace, ".mcp-vector-search"))

        # Re-fetch the session
        get_resp = client.get(f"/api/v1/sessions/{session_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["is_indexed"] is True
