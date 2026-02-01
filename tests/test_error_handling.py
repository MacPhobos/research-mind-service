"""Error handling tests (Phase 1.7).

Validates that all endpoints return correct HTTP status codes and error
structures for invalid inputs, missing resources, and subprocess failures.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.workspace_indexer import (
    IndexingCommandError,
    IndexingResult,
    IndexingTimeoutError,
)

FAKE_UUID = "00000000-0000-4000-a000-000000000000"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _create_session(client: TestClient, name: str = "Error Test") -> dict:
    resp = client.post("/api/v1/sessions/", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


# ------------------------------------------------------------------
# 404 tests
# ------------------------------------------------------------------


class TestNotFoundErrors:
    def test_get_nonexistent_session_returns_404(self, shared_client: TestClient):
        resp = shared_client.get(f"/api/v1/sessions/{FAKE_UUID}")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["error"]["code"] == "SESSION_NOT_FOUND"

    def test_index_nonexistent_workspace_returns_404(self, shared_client: TestClient):
        resp = shared_client.post(f"/api/v1/workspaces/{FAKE_UUID}/index")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["error"]["code"] == "SESSION_NOT_FOUND"

    def test_index_status_nonexistent_returns_404(self, shared_client: TestClient):
        resp = shared_client.get(
            f"/api/v1/workspaces/{FAKE_UUID}/index/status"
        )
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["error"]["code"] == "SESSION_NOT_FOUND"

    def test_delete_nonexistent_session_returns_404(self, shared_client: TestClient):
        resp = shared_client.delete(f"/api/v1/sessions/{FAKE_UUID}")
        assert resp.status_code == 404

    def test_audit_nonexistent_session_returns_404(self, shared_client: TestClient):
        resp = shared_client.get(f"/api/v1/sessions/{FAKE_UUID}/audit")
        assert resp.status_code == 404
        data = resp.json()
        assert data["detail"]["error"]["code"] == "SESSION_NOT_FOUND"


# ------------------------------------------------------------------
# 422 Validation errors
# ------------------------------------------------------------------


class TestValidationErrors:
    def test_create_session_no_name_returns_422(self, shared_client: TestClient):
        resp = shared_client.post("/api/v1/sessions/", json={})
        assert resp.status_code == 422

    def test_create_session_empty_name_returns_422(self, shared_client: TestClient):
        resp = shared_client.post("/api/v1/sessions/", json={"name": ""})
        assert resp.status_code == 422


# ------------------------------------------------------------------
# Subprocess failure error handling
# ------------------------------------------------------------------


class TestSubprocessFailureErrors:
    def test_index_subprocess_failure_returns_result(
        self, shared_client: TestClient
    ):
        """When init subprocess fails, POST /index still returns 200 with success=false."""
        session = _create_session(shared_client)
        session_id = session["session_id"]

        # Mock WorkspaceIndexer so init raises IndexingCommandError
        # which IndexingService catches and returns IndexingResult(success=False)
        mock_indexer = MagicMock()
        mock_indexer.initialize.side_effect = IndexingCommandError(
            "Command exited with code 1: mcp-vector-search init --force\n"
            "stderr: init error"
        )

        with patch(
            "app.services.indexing_service.WorkspaceIndexer",
            return_value=mock_indexer,
        ):
            resp = shared_client.post(
                f"/api/v1/workspaces/{session_id}/index"
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["status"] == "failed"

    def test_index_subprocess_timeout_returns_result(
        self, shared_client: TestClient
    ):
        """When subprocess times out, POST /index returns 500 with INDEXING_TIMEOUT."""
        session = _create_session(shared_client)
        session_id = session["session_id"]

        mock_indexer = MagicMock()
        mock_indexer.initialize.side_effect = IndexingTimeoutError(
            "Command timed out after 30s"
        )

        with patch(
            "app.services.indexing_service.WorkspaceIndexer",
            return_value=mock_indexer,
        ):
            resp = shared_client.post(
                f"/api/v1/workspaces/{session_id}/index"
            )

        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"]["error"]["code"] == "INDEXING_TIMEOUT"
