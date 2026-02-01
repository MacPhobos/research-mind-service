"""Tests for workspace indexing operations (Phase 1.3)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  -- ensure models registered with Base.metadata
from app.core.workspace_indexer import (
    IndexingResult,
    WorkspaceIndexer,
    WorkspaceNotFoundError,
)
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.indexing_service import IndexingService


# ====================================================================
# Unit tests for IndexingService.check_index_status
# ====================================================================


class TestCheckIndexStatus:
    def test_index_status_not_initialized(self, tmp_path: Path):
        """Workspace exists but .mcp-vector-search/ does not."""
        result = IndexingService.check_index_status(str(tmp_path))
        assert result["is_indexed"] is False
        assert result["status"] == "not_initialized"
        assert "not been indexed" in result["message"]

    def test_index_status_initialized(self, tmp_path: Path):
        """Workspace exists and .mcp-vector-search/ is present."""
        (tmp_path / ".mcp-vector-search").mkdir()
        result = IndexingService.check_index_status(str(tmp_path))
        assert result["is_indexed"] is True
        assert result["status"] == "indexed"
        assert "available" in result["message"]

    def test_index_status_workspace_not_found(self, tmp_path: Path):
        """Workspace directory does not exist."""
        fake_path = str(tmp_path / "nonexistent")
        result = IndexingService.check_index_status(fake_path)
        assert result["is_indexed"] is False
        assert result["status"] == "workspace_not_found"
        assert "does not exist" in result["message"]


# ====================================================================
# Unit tests for IndexingService.index_workspace (mocked subprocess)
# ====================================================================


def _make_completed_process(returncode: int = 0, stdout: str = "", stderr: str = ""):
    """Helper to build a CompletedProcess mock."""
    proc = MagicMock(spec=subprocess.CompletedProcess)
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class TestIndexWorkspace:
    """Unit tests for IndexingService with path validation disabled.

    These tests use tmp_path which is outside the configured workspace_root,
    so we disable path_validator_enabled for the duration of each test.
    """

    @pytest.fixture(autouse=True)
    def _disable_path_validator(self):
        """Disable path validation so tmp_path workspaces are accepted."""
        from app.core.config import settings

        original = settings.path_validator_enabled
        object.__setattr__(settings, "path_validator_enabled", False)
        yield
        object.__setattr__(settings, "path_validator_enabled", original)

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_index_workspace_success(self, mock_run, tmp_path: Path):
        """Both init and index succeed."""
        mock_run.return_value = _make_completed_process(
            returncode=0, stdout="OK", stderr=""
        )
        result = IndexingService.index_workspace(str(tmp_path), force=True)
        assert result.success is True
        assert mock_run.call_count == 2  # init + index

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_index_workspace_init_failure(self, mock_run, tmp_path: Path):
        """Init step returns non-zero exit code."""
        mock_run.return_value = _make_completed_process(
            returncode=1, stdout="", stderr="init failed"
        )
        result = IndexingService.index_workspace(str(tmp_path))
        assert result.success is False
        assert mock_run.call_count == 1  # only init was called

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_index_workspace_timeout(self, mock_run, tmp_path: Path):
        """Subprocess raises TimeoutExpired."""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="mcp-vector-search init --force", timeout=30
        )
        with pytest.raises(Exception):  # IndexingTimeoutError wraps TimeoutExpired
            IndexingService.index_workspace(str(tmp_path))

    def test_index_workspace_not_found(self, tmp_path: Path):
        """Workspace directory does not exist."""
        fake = str(tmp_path / "nonexistent")
        with pytest.raises(WorkspaceNotFoundError):
            IndexingService.index_workspace(fake)

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_multi_workspace_isolation(self, mock_run, tmp_path: Path):
        """Two workspaces use different cwd values."""
        mock_run.return_value = _make_completed_process(returncode=0, stdout="OK")

        ws1 = tmp_path / "workspace_a"
        ws2 = tmp_path / "workspace_b"
        ws1.mkdir()
        ws2.mkdir()

        IndexingService.index_workspace(str(ws1))
        IndexingService.index_workspace(str(ws2))

        # Collect all cwd arguments passed to subprocess.run
        cwd_values = [call.kwargs.get("cwd") for call in mock_run.call_args_list]

        assert ws1 in cwd_values
        assert ws2 in cwd_values
        # Each workspace should have its own init + index calls
        assert mock_run.call_count == 4


# ====================================================================
# Endpoint tests (TestClient with DB override)
# ====================================================================


@pytest.fixture()
def tmp_workspace(tmp_path):
    """Provide a temporary workspace root directory."""
    return str(tmp_path / "workspaces")


@pytest.fixture()
def db_engine():
    """In-memory SQLite engine shared across connections."""
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
def client(db_engine, tmp_workspace):
    """TestClient with overridden DB dependency and workspace root."""
    from app.core.config import settings

    original_workspace_root = settings.workspace_root
    object.__setattr__(settings, "workspace_root", tmp_workspace)

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
    object.__setattr__(settings, "workspace_root", original_workspace_root)


def _create_session(client: TestClient, name: str = "Test Session") -> dict:
    """Helper to create a session and return JSON response."""
    resp = client.post("/api/v1/sessions/", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


class TestIndexEndpoints:
    def test_index_endpoint_session_not_found(self, client: TestClient):
        """POST /api/v1/workspaces/{id}/index returns 404 for unknown session."""
        response = client.post("/api/v1/workspaces/00000000-0000-4000-a000-000000000000/index")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"]["code"] == "SESSION_NOT_FOUND"

    def test_index_status_endpoint_session_not_found(self, client: TestClient):
        """GET /api/v1/workspaces/{id}/index/status returns 404 for unknown session."""
        response = client.get("/api/v1/workspaces/00000000-0000-4000-a000-000000000000/index/status")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"]["code"] == "SESSION_NOT_FOUND"

    @patch("app.services.indexing_service.WorkspaceIndexer")
    def test_index_endpoint_success(self, mock_indexer_cls, client: TestClient):
        """POST returns 200 with success=true when indexing succeeds."""
        session_data = _create_session(client)
        session_id = session_data["session_id"]

        # Mock the indexer instance
        mock_indexer = MagicMock()
        mock_indexer.initialize.return_value = IndexingResult(
            success=True,
            elapsed_seconds=1.0,
            stdout="init ok",
            stderr="",
            command=["mcp-vector-search", "init", "--force"],
            return_code=0,
        )
        mock_indexer.index.return_value = IndexingResult(
            success=True,
            elapsed_seconds=2.5,
            stdout="index ok",
            stderr="",
            command=["mcp-vector-search", "index", "--force"],
            return_code=0,
        )
        mock_indexer_cls.return_value = mock_indexer

        response = client.post(f"/api/v1/workspaces/{session_id}/index")
        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == session_id
        assert data["success"] is True
        assert data["status"] == "completed"
        assert data["elapsed_seconds"] > 0

    def test_index_status_endpoint(self, client: TestClient):
        """GET returns 200 with status info for an existing session."""
        session_data = _create_session(client)
        session_id = session_data["session_id"]

        # Before indexing
        response = client.get(f"/api/v1/workspaces/{session_id}/index/status")
        assert response.status_code == 200
        data = response.json()
        assert data["workspace_id"] == session_id
        assert data["is_indexed"] is False
        assert data["status"] == "not_initialized"

        # Simulate indexing by creating the directory
        workspace = session_data["workspace_path"]
        os.makedirs(os.path.join(workspace, ".mcp-vector-search"))

        # After indexing
        response2 = client.get(f"/api/v1/workspaces/{session_id}/index/status")
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["is_indexed"] is True
        assert data2["status"] == "indexed"
