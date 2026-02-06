"""Shared pytest fixtures for integration and unit tests.

Individual test modules (test_sessions.py, test_indexing.py, etc.) define their
own ``client`` fixtures that override get_db. The fixtures below are prefixed
with ``shared_`` so they never collide with per-module fixtures.

Usage in new test files:
    def test_something(shared_client, create_session):
        data = create_session(shared_client, "My Session")
        ...
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  -- ensure models registered with Base.metadata
from app.db.base import Base
from app.db.session import get_db
from app.main import app


# ------------------------------------------------------------------
# Database fixtures (shared_ prefix to avoid collisions)
# ------------------------------------------------------------------


@pytest.fixture()
def shared_db_engine():
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
def shared_tmp_content_sandbox(tmp_path):
    """Provide a temporary content sandbox root directory."""
    return str(tmp_path / "content_sandboxes")


@pytest.fixture()
def shared_client(shared_db_engine, shared_tmp_content_sandbox):
    """TestClient with overridden DB dependency and content_sandbox_root."""
    from app.core.config import settings

    original_content_sandbox_root = settings.content_sandbox_root
    object.__setattr__(settings, "content_sandbox_root", shared_tmp_content_sandbox)

    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=shared_db_engine
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
# Helper fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def create_session() -> Callable[..., dict]:
    """Return a helper that POSTs a session and returns the JSON response."""

    def _create(
        client: TestClient,
        name: str = "Test Session",
        description: str | None = None,
    ) -> dict:
        payload: dict = {"name": name}
        if description is not None:
            payload["description"] = description
        resp = client.post("/api/v1/sessions/", json=payload)
        assert resp.status_code == 201, f"Failed to create session: {resp.text}"
        return resp.json()

    return _create


@pytest.fixture()
def test_workspace(tmp_path: Path) -> Path:
    """Create a temp directory with sample Python files for indexing tests."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "main.py").write_text("def hello():\n    return 'world'\n")
    (ws / "utils.py").write_text("import os\nprint(os.getcwd())\n")
    sub = ws / "sub"
    sub.mkdir()
    (sub / "helper.py").write_text("class Helper:\n    pass\n")
    return ws


@pytest.fixture()
def test_workspace_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Create two temp directories with different content."""
    ws_a = tmp_path / "workspace_a"
    ws_a.mkdir()
    (ws_a / "alpha.py").write_text("x = 1\n")

    ws_b = tmp_path / "workspace_b"
    ws_b.mkdir()
    (ws_b / "beta.py").write_text("y = 2\n")

    return ws_a, ws_b
