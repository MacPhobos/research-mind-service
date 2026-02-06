"""Business logic for workspace indexing operations."""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import settings
from app.core.workspace_indexer import (
    IndexingCommandError,
    IndexingResult,
    WorkspaceIndexer,
)
from app.sandbox.path_validator import PathValidator

logger = logging.getLogger(__name__)


class IndexingService:
    """Static methods for indexing workspace directories."""

    @staticmethod
    def index_workspace(
        workspace_path: str,
        force: bool = True,
        timeout: int | None = None,
    ) -> IndexingResult:
        """Initialize and index a workspace directory.

        Creates a WorkspaceIndexer, runs initialize() then index().
        If init fails, returns the init result immediately (skips index).

        Args:
            workspace_path: Absolute path to the workspace directory.
            force: Whether to force re-index.
            timeout: Custom timeout for the index step (seconds).
                     Uses settings.subprocess_timeout_index if None.

        Returns:
            IndexingResult from the final step executed.

        Raises:
            WorkspaceNotFoundError: If workspace_path does not exist.
            ToolNotFoundError: If mcp-vector-search CLI is not on PATH.
            IndexingTimeoutError: If a subprocess exceeds its timeout.
        """
        path = Path(workspace_path)

        # Security: validate workspace path before subprocess invocation
        if settings.path_validator_enabled:
            sandbox_root = Path(settings.content_sandbox_root).resolve()
            validator = PathValidator(sandbox_root)
            if not validator.validate_workspace_for_subprocess(workspace_path):
                logger.warning(
                    "Path validation failed for workspace: %s", workspace_path
                )
                return IndexingResult(
                    success=False,
                    elapsed_seconds=0.0,
                    stdout="",
                    stderr=f"Path validation failed: {workspace_path}",
                    command=["mcp-vector-search", "init", "--force"],
                    return_code=1,
                )

        indexer = WorkspaceIndexer(path)

        init_timeout = settings.subprocess_timeout_init
        index_timeout = (
            timeout if timeout is not None else settings.subprocess_timeout_index
        )

        # Step 1: Initialize
        try:
            indexer.initialize(timeout=init_timeout)
        except IndexingCommandError as exc:
            logger.warning("Init failed for %s: %s", workspace_path, exc)
            return IndexingResult(
                success=False,
                elapsed_seconds=0.0,
                stdout="",
                stderr=str(exc),
                command=["mcp-vector-search", "init", "--force"],
                return_code=1,
            )

        # Step 2: Index
        try:
            index_result = indexer.index(timeout=index_timeout, force=force)
        except IndexingCommandError as exc:
            logger.warning("Index failed for %s: %s", workspace_path, exc)
            return IndexingResult(
                success=False,
                elapsed_seconds=0.0,
                stdout="",
                stderr=str(exc),
                command=["mcp-vector-search", "index", "--force"],
                return_code=1,
            )

        return index_result

    @staticmethod
    def check_index_status(workspace_path: str) -> dict:
        """Check the indexing status of a workspace directory.

        Args:
            workspace_path: Absolute path to the workspace directory.

        Returns:
            Dict with keys: is_indexed, status, message.
        """
        path = Path(workspace_path)

        if not path.exists() or not path.is_dir():
            return {
                "is_indexed": False,
                "status": "workspace_not_found",
                "message": f"Workspace directory does not exist: {workspace_path}",
            }

        index_dir = path / ".mcp-vector-search"
        if not index_dir.is_dir():
            return {
                "is_indexed": False,
                "status": "not_initialized",
                "message": "Workspace has not been indexed yet.",
            }

        return {
            "is_indexed": True,
            "status": "indexed",
            "message": "Workspace index is available.",
        }
