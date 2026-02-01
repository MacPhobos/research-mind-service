"""End-to-end integration tests (Phase 1.7).

These tests exercise full API flows: create session -> index -> check status.
Subprocess calls are mocked to avoid requiring real CLI tools in CI.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.workspace_indexer import IndexingResult


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _create_session(client: TestClient, name: str = "E2E Session") -> dict:
    """POST a session and return the response JSON."""
    resp = client.post("/api/v1/sessions/", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _mock_indexer(success: bool = True):
    """Return a context-manager that patches WorkspaceIndexer."""
    mock_indexer = MagicMock()
    mock_indexer.initialize.return_value = IndexingResult(
        success=success,
        elapsed_seconds=0.5,
        stdout="init ok" if success else "",
        stderr="" if success else "init failed",
        command=["mcp-vector-search", "init", "--force"],
        return_code=0 if success else 1,
    )
    mock_indexer.index.return_value = IndexingResult(
        success=success,
        elapsed_seconds=1.2,
        stdout="index ok" if success else "",
        stderr="" if success else "index failed",
        command=["mcp-vector-search", "index", "--force"],
        return_code=0 if success else 1,
    )
    return patch(
        "app.services.indexing_service.WorkspaceIndexer",
        return_value=mock_indexer,
    )


# ------------------------------------------------------------------
# E2E flow tests
# ------------------------------------------------------------------


class TestFullFlowCreateSessionAndIndex:
    """POST session -> POST index (mocked) -> GET status -> verify."""

    def test_full_flow_create_session_and_index(self, shared_client: TestClient):
        # Step 1: Create session
        session = _create_session(shared_client)
        session_id = session["session_id"]
        assert session["status"] == "active"

        # Step 2: Index (mocked subprocess success)
        with _mock_indexer(success=True):
            index_resp = shared_client.post(
                f"/api/v1/workspaces/{session_id}/index"
            )
        assert index_resp.status_code == 200
        index_data = index_resp.json()
        assert index_data["workspace_id"] == session_id
        assert index_data["success"] is True
        assert index_data["status"] == "completed"
        assert index_data["elapsed_seconds"] > 0

        # Step 3: Check status -- without real subprocess the .mcp-vector-search
        # dir is NOT created, so status should be "not_initialized".
        status_resp = shared_client.get(
            f"/api/v1/workspaces/{session_id}/index/status"
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["workspace_id"] == session_id
        # The mock doesn't create the directory, so is_indexed stays False
        assert status_data["is_indexed"] is False


class TestFullFlowIndexThenCheckStatus:
    """Create session, simulate indexing artifacts, verify GET status shows indexed."""

    def test_full_flow_index_then_check_status(self, shared_client: TestClient):
        session = _create_session(shared_client, "Indexed Session")
        session_id = session["session_id"]
        workspace_path = session["workspace_path"]

        # Simulate the .mcp-vector-search directory being created
        os.makedirs(os.path.join(workspace_path, ".mcp-vector-search"))

        status_resp = shared_client.get(
            f"/api/v1/workspaces/{session_id}/index/status"
        )
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["is_indexed"] is True
        assert data["status"] == "indexed"


class TestFullFlowSessionLifecycle:
    """Create -> index -> get audit -> delete -> verify cleanup."""

    def test_full_flow_session_lifecycle(self, shared_client: TestClient):
        # Create
        session = _create_session(shared_client, "Lifecycle Session")
        session_id = session["session_id"]
        workspace_path = session["workspace_path"]
        assert os.path.isdir(workspace_path)

        # Index (mocked)
        with _mock_indexer(success=True):
            index_resp = shared_client.post(
                f"/api/v1/workspaces/{session_id}/index"
            )
        assert index_resp.status_code == 200

        # Get audit logs
        audit_resp = shared_client.get(
            f"/api/v1/sessions/{session_id}/audit"
        )
        assert audit_resp.status_code == 200
        assert "logs" in audit_resp.json()

        # Delete
        delete_resp = shared_client.delete(
            f"/api/v1/sessions/{session_id}"
        )
        assert delete_resp.status_code == 204

        # Verify cleanup: workspace dir removed
        assert not os.path.isdir(workspace_path)

        # GET should 404
        get_resp = shared_client.get(f"/api/v1/sessions/{session_id}")
        assert get_resp.status_code == 404


class TestSessionCreateReturnsWorkspacePath:
    def test_session_create_returns_workspace_path(self, shared_client: TestClient):
        session = _create_session(shared_client)
        assert "workspace_path" in session
        assert isinstance(session["workspace_path"], str)
        assert len(session["workspace_path"]) > 0


class TestSessionWorkspaceDirectoryCreated:
    def test_session_workspace_directory_created(self, shared_client: TestClient):
        session = _create_session(shared_client, "Dir Check")
        workspace_path = session["workspace_path"]
        assert os.path.isdir(workspace_path), (
            f"Workspace directory was not created on disk: {workspace_path}"
        )
