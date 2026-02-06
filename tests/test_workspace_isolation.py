"""Multi-workspace isolation tests (Phase 1.7).

Verifies that sessions have independent workspace paths, independent index
status, and that operations on one workspace do not affect another.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.workspace_indexer import WorkspaceIndexer
from app.services.indexing_service import IndexingService


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _create_session(client: TestClient, name: str) -> dict:
    resp = client.post("/api/v1/sessions/", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _make_completed_process(returncode: int = 0, stdout: str = "", stderr: str = ""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


# ------------------------------------------------------------------
# Isolation tests
# ------------------------------------------------------------------


class TestTwoSessionsHaveDifferentWorkspacePaths:
    def test_two_sessions_have_different_workspace_paths(
        self, shared_client: TestClient
    ):
        s1 = _create_session(shared_client, "Session A")
        s2 = _create_session(shared_client, "Session B")

        assert s1["workspace_path"] != s2["workspace_path"]
        assert s1["session_id"] != s2["session_id"]
        # Both directories should exist
        assert os.path.isdir(s1["workspace_path"])
        assert os.path.isdir(s2["workspace_path"])


class TestWorkspaceIndexStatusIndependent:
    """Mock: two sessions, one indexed, one not -- statuses are independent."""

    def test_workspace_index_status_independent(self, shared_client: TestClient):
        s1 = _create_session(shared_client, "Indexed One")
        s2 = _create_session(shared_client, "Not Indexed")

        # Simulate indexing for s1 only
        os.makedirs(os.path.join(s1["workspace_path"], ".mcp-vector-search"))

        status1 = shared_client.get(
            f"/api/v1/workspaces/{s1['session_id']}/index/status"
        )
        status2 = shared_client.get(
            f"/api/v1/workspaces/{s2['session_id']}/index/status"
        )

        assert status1.status_code == 200
        assert status2.status_code == 200
        assert status1.json()["is_indexed"] is True
        assert status2.json()["is_indexed"] is False


class TestDeletingOneSessionDoesntAffectOther:
    def test_deleting_one_session_doesnt_affect_other(self, shared_client: TestClient):
        s1 = _create_session(shared_client, "Keep Me")
        s2 = _create_session(shared_client, "Delete Me")

        # Delete s2
        del_resp = shared_client.delete(f"/api/v1/sessions/{s2['session_id']}")
        assert del_resp.status_code == 204

        # s1 should still be accessible
        get_resp = shared_client.get(f"/api/v1/sessions/{s1['session_id']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "Keep Me"

        # s1 workspace should still exist
        assert os.path.isdir(s1["workspace_path"])

        # s2 workspace should be gone
        assert not os.path.isdir(s2["workspace_path"])


class TestConcurrentIndexingMocked:
    """Mock: verify different cwd values for parallel indexing calls."""

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_concurrent_indexing_mocked(
        self, mock_run, test_workspace_pair: tuple[Path, Path]
    ):
        mock_run.return_value = _make_completed_process(returncode=0, stdout="OK")

        ws_a, ws_b = test_workspace_pair

        # Disable path validation for tmp_path workspaces
        from app.core.config import settings

        original = settings.path_validator_enabled
        object.__setattr__(settings, "path_validator_enabled", False)

        try:
            IndexingService.index_workspace(str(ws_a))
            IndexingService.index_workspace(str(ws_b))
        finally:
            object.__setattr__(settings, "path_validator_enabled", original)

        # Collect all cwd values passed to subprocess.run
        cwd_values = [call.kwargs.get("cwd") for call in mock_run.call_args_list]
        assert ws_a in cwd_values
        assert ws_b in cwd_values
        # Each workspace has init + index = 4 total calls
        assert mock_run.call_count == 4


# ------------------------------------------------------------------
# Real integration test
# ------------------------------------------------------------------


@pytest.mark.integration
class TestParallelRealIndexing:
    """Real subprocess, two workspaces indexed in ThreadPoolExecutor."""

    def test_parallel_real_indexing(self, test_workspace_pair: tuple[Path, Path]):
        ws_a, ws_b = test_workspace_pair

        def index_workspace(ws: Path) -> bool:
            indexer = WorkspaceIndexer(ws)
            init_result = indexer.initialize()
            if not init_result.success:
                return False
            index_result = indexer.index()
            return index_result.success

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(index_workspace, ws_a)
            future_b = executor.submit(index_workspace, ws_b)

            result_a = future_a.result(timeout=60)
            result_b = future_b.result(timeout=60)

        assert result_a is True, "Workspace A indexing failed"
        assert result_b is True, "Workspace B indexing failed"

        # Both should have .mcp-vector-search directories
        assert (ws_a / ".mcp-vector-search").is_dir()
        assert (ws_b / ".mcp-vector-search").is_dir()
