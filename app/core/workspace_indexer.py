"""Workspace indexer that drives mcp-vector-search as a subprocess.

mcp-vector-search is a CLI tool, NOT a Python library. All interactions
happen through subprocess.run() with cwd set to the workspace directory.

Two-step indexing flow:
    1. ``mcp-vector-search init --force``   (creates .mcp-vector-search/)
    2. ``mcp-vector-search index --force``   (builds the vector index)
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexingResult:
    """Outcome of a single subprocess invocation."""

    success: bool
    elapsed_seconds: float
    stdout: str
    stderr: str
    command: list[str]
    return_code: int = 0


class WorkspaceIndexerError(Exception):
    """Base exception for workspace indexer failures."""


class WorkspaceNotFoundError(WorkspaceIndexerError):
    """Raised when the workspace directory does not exist."""


class IndexingTimeoutError(WorkspaceIndexerError):
    """Raised when a subprocess exceeds its timeout."""


class IndexingCommandError(WorkspaceIndexerError):
    """Raised when the subprocess exits with a non-zero code."""


class ToolNotFoundError(WorkspaceIndexerError):
    """Raised when mcp-vector-search CLI is not found on PATH."""


class WorkspaceIndexer:
    """Manages mcp-vector-search subprocess invocations for a workspace.

    Args:
        workspace_dir: Absolute path to the workspace directory.
                       Must exist at construction time.

    Raises:
        WorkspaceNotFoundError: If *workspace_dir* does not exist or
                                is not a directory.
    """

    MCP_CLI = "mcp-vector-search"
    INDEX_DIR_NAME = ".mcp-vector-search"

    def __init__(self, workspace_dir: Path) -> None:
        if not workspace_dir.exists():
            raise WorkspaceNotFoundError(
                f"Workspace directory does not exist: {workspace_dir}"
            )
        if not workspace_dir.is_dir():
            raise WorkspaceNotFoundError(
                f"Workspace path is not a directory: {workspace_dir}"
            )
        self._workspace_dir = workspace_dir

    @property
    def workspace_dir(self) -> Path:
        return self._workspace_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialize(self, timeout: int = 30) -> IndexingResult:
        """Run ``mcp-vector-search init --force`` in the workspace.

        Args:
            timeout: Maximum seconds to wait for the process.

        Returns:
            IndexingResult with subprocess output.
        """
        cmd = [self.MCP_CLI, "init", "--force"]
        return self._run_command(cmd, timeout=timeout)

    def index(self, timeout: int = 60, force: bool = True) -> IndexingResult:
        """Run ``mcp-vector-search index`` in the workspace.

        Args:
            timeout: Maximum seconds to wait for the process.
            force: If True, passes ``--force`` to re-index from scratch.

        Returns:
            IndexingResult with subprocess output.
        """
        cmd = [self.MCP_CLI, "index"]
        if force:
            cmd.append("--force")
        return self._run_command(cmd, timeout=timeout)

    def initialize_and_index(
        self,
        init_timeout: int = 30,
        index_timeout: int = 60,
    ) -> tuple[IndexingResult, IndexingResult]:
        """Run the full two-step flow: init then index.

        Args:
            init_timeout: Timeout for the init step.
            index_timeout: Timeout for the index step.

        Returns:
            Tuple of (init_result, index_result).
        """
        init_result = self.initialize(timeout=init_timeout)
        if not init_result.success:
            return init_result, IndexingResult(
                success=False,
                elapsed_seconds=0.0,
                stdout="",
                stderr="Skipped: init step failed.",
                command=[self.MCP_CLI, "index", "--force"],
                return_code=-1,
            )
        index_result = self.index(timeout=index_timeout)
        return init_result, index_result

    def is_indexed(self) -> bool:
        """Check whether the workspace has been indexed.

        Returns:
            True if the ``.mcp-vector-search/`` directory exists inside
            the workspace.
        """
        return (self._workspace_dir / self.INDEX_DIR_NAME).is_dir()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_command(
        self,
        cmd: list[str],
        timeout: int,
    ) -> IndexingResult:
        """Execute a subprocess and return an IndexingResult.

        Args:
            cmd: Command and arguments to execute.
            timeout: Maximum seconds before TimeoutExpired.

        Returns:
            IndexingResult capturing stdout, stderr, elapsed time, and
            success/failure.

        Raises:
            ToolNotFoundError: mcp-vector-search is not installed.
            IndexingTimeoutError: Process exceeded *timeout*.
            IndexingCommandError: Process exited with non-zero code.
        """
        logger.info(
            "Running command: %s (cwd=%s, timeout=%ds)",
            " ".join(cmd),
            self._workspace_dir,
            timeout,
        )
        start = time.monotonic()

        try:
            result = subprocess.run(
                cmd,
                cwd=self._workspace_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            elapsed = time.monotonic() - start
            logger.error("CLI tool not found: %s", cmd[0])
            raise ToolNotFoundError(
                f"'{cmd[0]}' not found. Is mcp-vector-search installed and on PATH?"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - start
            logger.error("Command timed out after %ds: %s", timeout, " ".join(cmd))
            raise IndexingTimeoutError(
                f"Command timed out after {timeout}s: {' '.join(cmd)}"
            ) from exc

        elapsed = time.monotonic() - start

        if result.returncode != 0:
            logger.warning(
                "Command exited with code %d: %s\nstderr: %s",
                result.returncode,
                " ".join(cmd),
                result.stderr.strip(),
            )
            raise IndexingCommandError(
                f"Command exited with code {result.returncode}: {' '.join(cmd)}\n"
                f"stderr: {result.stderr.strip()}"
            )

        logger.info(
            "Command succeeded in %.2fs: %s",
            elapsed,
            " ".join(cmd),
        )
        return IndexingResult(
            success=True,
            elapsed_seconds=round(elapsed, 3),
            stdout=result.stdout,
            stderr=result.stderr,
            command=cmd,
            return_code=result.returncode,
        )
