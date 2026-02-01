"""Subprocess invocation tests (Phase 1.7).

Verifies that WorkspaceIndexer and IndexingService correctly invoke
mcp-vector-search as a subprocess, handle exit codes, timeouts, and
output capture.

Tests marked @pytest.mark.integration require the real mcp-vector-search CLI.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.workspace_indexer import (
    IndexingCommandError,
    IndexingTimeoutError,
    ToolNotFoundError,
    WorkspaceIndexer,
)
from app.services.indexing_service import IndexingService


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_completed_process(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> MagicMock:
    proc = MagicMock(spec=subprocess.CompletedProcess)
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


# ------------------------------------------------------------------
# Mocked subprocess tests
# ------------------------------------------------------------------


class TestInitSubprocessCall:
    """Verify mcp-vector-search init is called with correct command and cwd."""

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_init_subprocess_call(self, mock_run, tmp_path: Path):
        mock_run.return_value = _make_completed_process(
            returncode=0, stdout="Initialized"
        )
        indexer = WorkspaceIndexer(tmp_path)
        indexer.initialize()

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd == ["mcp-vector-search", "init", "--force"]
        assert call_args.kwargs["cwd"] == tmp_path


class TestIndexSubprocessCall:
    """Verify mcp-vector-search index is called with correct command and cwd."""

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_index_subprocess_call(self, mock_run, tmp_path: Path):
        mock_run.return_value = _make_completed_process(
            returncode=0, stdout="Indexed 42 files"
        )
        indexer = WorkspaceIndexer(tmp_path)
        indexer.index(force=True)

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd == ["mcp-vector-search", "index", "--force"]
        assert call_args.kwargs["cwd"] == tmp_path


class TestSubprocessExitCodes:
    @patch("app.core.workspace_indexer.subprocess.run")
    def test_subprocess_exit_code_zero_is_success(self, mock_run, tmp_path: Path):
        mock_run.return_value = _make_completed_process(returncode=0, stdout="OK")
        indexer = WorkspaceIndexer(tmp_path)
        result = indexer.initialize()
        assert result.success is True
        assert result.return_code == 0

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_subprocess_exit_code_one_is_failure(self, mock_run, tmp_path: Path):
        mock_run.return_value = _make_completed_process(
            returncode=1, stdout="", stderr="error occurred"
        )
        indexer = WorkspaceIndexer(tmp_path)
        with pytest.raises(IndexingCommandError):
            indexer.initialize()


class TestSubprocessTimeoutHandling:
    @patch("app.core.workspace_indexer.subprocess.run")
    def test_subprocess_timeout_handling(self, mock_run, tmp_path: Path):
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd="mcp-vector-search init --force", timeout=30
        )
        indexer = WorkspaceIndexer(tmp_path)
        with pytest.raises(IndexingTimeoutError):
            indexer.initialize(timeout=30)


class TestSubprocessOutputCapture:
    @patch("app.core.workspace_indexer.subprocess.run")
    def test_subprocess_output_capture(self, mock_run, tmp_path: Path):
        mock_run.return_value = _make_completed_process(
            returncode=0,
            stdout="indexed 10 files\n3 chunks created",
            stderr="warn: something minor",
        )
        indexer = WorkspaceIndexer(tmp_path)
        result = indexer.initialize()

        assert "indexed 10 files" in result.stdout
        assert "warn: something minor" in result.stderr
        assert result.success is True
        # Verify capture_output=True was passed
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["capture_output"] is True
        assert call_kwargs["text"] is True


class TestPathValidationBeforeSubprocess:
    """Verify that path validation occurs before subprocess invocation."""

    @patch("app.core.workspace_indexer.subprocess.run")
    def test_path_validation_before_subprocess(self, mock_run, tmp_path: Path):
        """IndexingService should validate path before spawning subprocess."""
        from app.core.config import settings

        # Enable path validation
        original = settings.path_validator_enabled
        object.__setattr__(settings, "path_validator_enabled", True)

        try:
            # Use a path OUTSIDE workspace_root -- should fail validation
            result = IndexingService.index_workspace(str(tmp_path))
            assert result.success is False
            assert "Path validation failed" in result.stderr
            # subprocess.run should NOT have been called
            mock_run.assert_not_called()
        finally:
            object.__setattr__(settings, "path_validator_enabled", original)


# ------------------------------------------------------------------
# Real integration tests (require mcp-vector-search CLI)
# ------------------------------------------------------------------


@pytest.mark.integration
class TestRealInitSubprocess:
    """Run real mcp-vector-search init on a temp directory."""

    def test_real_init_subprocess(self, test_workspace: Path):
        """Real init should succeed if CLI is installed."""
        indexer = WorkspaceIndexer(test_workspace)
        result = indexer.initialize()
        assert result.success is True
        assert result.return_code == 0
        # The .mcp-vector-search directory should exist after init
        assert (test_workspace / ".mcp-vector-search").is_dir()


@pytest.mark.integration
class TestRealIndexArtifactsCreated:
    """Run real init + index and verify artifacts."""

    def test_real_index_artifacts_created(self, test_workspace: Path):
        """After init + index, .mcp-vector-search/ should contain index data."""
        indexer = WorkspaceIndexer(test_workspace)

        init_result = indexer.initialize()
        assert init_result.success is True

        index_result = indexer.index()
        assert index_result.success is True

        index_dir = test_workspace / ".mcp-vector-search"
        assert index_dir.is_dir()
        # The directory should have some content after indexing
        contents = list(index_dir.iterdir())
        assert len(contents) > 0, ".mcp-vector-search/ should not be empty after indexing"
