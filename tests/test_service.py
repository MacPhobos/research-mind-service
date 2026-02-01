"""Phase 1.1 tests: health endpoints, config loading, and WorkspaceIndexer."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.workspace_indexer import (
    IndexingCommandError,
    IndexingTimeoutError,
    ToolNotFoundError,
    WorkspaceIndexer,
    WorkspaceNotFoundError,
)
from app.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a temporary directory to act as a workspace."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


# ---------------------------------------------------------------------------
# Health endpoint tests
# ---------------------------------------------------------------------------


class TestHealthEndpoints:
    def test_root_health(self, client: TestClient) -> None:
        """GET /health returns 200 with status ok."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "git_sha" in data

    def test_api_v1_health(self, client: TestClient) -> None:
        """GET /api/v1/health returns 200 with status ok."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["name"] == "research-mind-service"

    def test_api_v1_version(self, client: TestClient) -> None:
        """GET /api/v1/version returns version info."""
        response = client.get("/api/v1/version")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert data["name"] == "research-mind-service"


# ---------------------------------------------------------------------------
# Configuration tests
# ---------------------------------------------------------------------------


class TestConfiguration:
    def test_default_port(self) -> None:
        s = Settings(
            _env_file=None,  # type: ignore[call-arg]
        )
        assert s.port == 15010

    def test_default_host(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.host == "0.0.0.0"

    def test_default_debug_false(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.debug is False

    def test_default_feature_flags_off(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.enable_agent_integration is False
        assert s.enable_caching is False
        assert s.enable_warm_pools is False

    def test_default_timeouts(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.subprocess_timeout_init == 30
        assert s.subprocess_timeout_index == 60
        assert s.subprocess_timeout_large == 600

    def test_cors_origins_default(self) -> None:
        s = Settings(_env_file=None)  # type: ignore[call-arg]
        origins = s.get_cors_origins()
        assert "http://localhost:15000" in origins


# ---------------------------------------------------------------------------
# WorkspaceIndexer tests
# ---------------------------------------------------------------------------


class TestWorkspaceIndexerInit:
    def test_valid_directory(self, tmp_workspace: Path) -> None:
        indexer = WorkspaceIndexer(tmp_workspace)
        assert indexer.workspace_dir == tmp_workspace

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        with pytest.raises(WorkspaceNotFoundError, match="does not exist"):
            WorkspaceIndexer(tmp_path / "nope")

    def test_file_instead_of_directory(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hi")
        with pytest.raises(WorkspaceNotFoundError, match="not a directory"):
            WorkspaceIndexer(f)


class TestWorkspaceIndexerIsIndexed:
    def test_not_indexed(self, tmp_workspace: Path) -> None:
        indexer = WorkspaceIndexer(tmp_workspace)
        assert indexer.is_indexed() is False

    def test_indexed(self, tmp_workspace: Path) -> None:
        (tmp_workspace / ".mcp-vector-search").mkdir()
        indexer = WorkspaceIndexer(tmp_workspace)
        assert indexer.is_indexed() is True


class TestWorkspaceIndexerSubprocess:
    """Tests that mock subprocess.run to verify command construction."""

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_initialize_calls_init_force(
        self, mock_run: MagicMock, tmp_workspace: Path
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["mcp-vector-search", "init", "--force"],
            returncode=0,
            stdout="Initialized.",
            stderr="",
        )
        indexer = WorkspaceIndexer(tmp_workspace)
        result = indexer.initialize(timeout=10)

        assert result.success is True
        assert result.command == ["mcp-vector-search", "init", "--force"]
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs["cwd"] == tmp_workspace
        assert call_kwargs.kwargs["timeout"] == 10

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_index_calls_index_force(
        self, mock_run: MagicMock, tmp_workspace: Path
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["mcp-vector-search", "index", "--force"],
            returncode=0,
            stdout="Indexed 42 files.",
            stderr="",
        )
        indexer = WorkspaceIndexer(tmp_workspace)
        result = indexer.index(timeout=20, force=True)

        assert result.success is True
        assert "--force" in result.command

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_index_without_force(
        self, mock_run: MagicMock, tmp_workspace: Path
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["mcp-vector-search", "index"],
            returncode=0,
            stdout="Indexed.",
            stderr="",
        )
        indexer = WorkspaceIndexer(tmp_workspace)
        result = indexer.index(timeout=20, force=False)

        assert result.success is True
        assert "--force" not in result.command

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_timeout_raises(
        self, mock_run: MagicMock, tmp_workspace: Path
    ) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["mcp-vector-search", "index", "--force"], timeout=5
        )
        indexer = WorkspaceIndexer(tmp_workspace)
        with pytest.raises(IndexingTimeoutError, match="timed out"):
            indexer.index(timeout=5)

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_tool_not_found_raises(
        self, mock_run: MagicMock, tmp_workspace: Path
    ) -> None:
        mock_run.side_effect = FileNotFoundError("No such file")
        indexer = WorkspaceIndexer(tmp_workspace)
        with pytest.raises(ToolNotFoundError, match="not found"):
            indexer.initialize()

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_nonzero_exit_raises(
        self, mock_run: MagicMock, tmp_workspace: Path
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["mcp-vector-search", "init", "--force"],
            returncode=1,
            stdout="",
            stderr="Error: something went wrong",
        )
        indexer = WorkspaceIndexer(tmp_workspace)
        with pytest.raises(IndexingCommandError, match="code 1"):
            indexer.initialize()

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_initialize_and_index_both_succeed(
        self, mock_run: MagicMock, tmp_workspace: Path
    ) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ok", stderr=""
        )
        indexer = WorkspaceIndexer(tmp_workspace)
        init_r, index_r = indexer.initialize_and_index()

        assert init_r.success is True
        assert index_r.success is True
        assert mock_run.call_count == 2
