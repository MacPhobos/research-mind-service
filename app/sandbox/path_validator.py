"""Path validation for preventing directory traversal and unauthorized access.

Validates all file paths before allowing read, list, or subprocess operations.
Critical security layer for WorkspaceIndexer which uses subprocess.run(cwd=...).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import unquote

logger = logging.getLogger(__name__)

# System paths that must never be accessed
BLOCKED_SYSTEM_PATHS: frozenset[str] = frozenset({
    "/etc",
    "/root",
    "/home",
    "/var",
    "/sys",
    "/proc",
    "/dev",
    "/bin",
    "/sbin",
    "/usr/bin",
    "/usr/sbin",
})

# File patterns that indicate hidden or sensitive files
HIDDEN_FILE_PREFIX = "."


class PathValidationError(Exception):
    """Raised when a path fails security validation."""


class PathValidator:
    """Validates file paths to prevent directory traversal and unauthorized access.

    All paths are checked against a session workspace root. Any attempt to
    escape the workspace or access sensitive files is blocked and logged.

    Args:
        session_workspace: Absolute path to the session workspace root.
                          Must exist and be a directory.
    """

    def __init__(self, session_workspace: Path) -> None:
        self._workspace_root = session_workspace.resolve()

    @property
    def workspace_root(self) -> Path:
        """Return the resolved workspace root path."""
        return self._workspace_root

    def validate_path(self, requested_path: str) -> bool:
        """Validate that a requested path is safe to access.

        Checks performed:
            1. URL-decode the path (block encoded traversal attempts)
            2. Resolve the path to an absolute path
            3. Verify the path is within the workspace root
            4. Block hidden files (components starting with '.')
            5. Block system paths (/etc, /root, /proc, etc.)
            6. Block symlinks (prevent escape via symlink)

        Args:
            requested_path: The path to validate (relative or absolute).

        Returns:
            True if the path is safe, False otherwise.
        """
        # Step 1: URL-decode to catch encoded traversal attacks
        decoded_path = unquote(unquote(requested_path))

        # Step 2: Resolve to absolute path
        if os.path.isabs(decoded_path):
            resolved = Path(decoded_path).resolve()
        else:
            resolved = (self._workspace_root / decoded_path).resolve()

        # Step 3: Check path is within workspace root
        try:
            resolved.relative_to(self._workspace_root)
        except ValueError:
            logger.warning(
                "PATH_BLOCKED: Traversal attempt — '%s' resolves outside workspace '%s'",
                requested_path,
                self._workspace_root,
            )
            return False

        # Step 4: Block hidden files (any component starting with '.')
        for part in resolved.relative_to(self._workspace_root).parts:
            if part.startswith(HIDDEN_FILE_PREFIX):
                logger.warning(
                    "PATH_BLOCKED: Hidden file access — '%s' (component: '%s')",
                    requested_path,
                    part,
                )
                return False

        # Step 5: Block system paths
        resolved_str = str(resolved)
        for blocked in BLOCKED_SYSTEM_PATHS:
            if resolved_str == blocked or resolved_str.startswith(blocked + "/"):
                logger.warning(
                    "PATH_BLOCKED: System path access — '%s' (matched: '%s')",
                    requested_path,
                    blocked,
                )
                return False

        # Step 6: Block symlinks anywhere in the path chain
        if self._has_symlink_in_chain(resolved):
            logger.warning(
                "PATH_BLOCKED: Symlink detected in path — '%s'",
                requested_path,
            )
            return False

        return True

    def safe_read(self, path: str) -> str:
        """Validate a path then read its contents.

        Args:
            path: Relative or absolute path to read.

        Returns:
            File contents as a string.

        Raises:
            PathValidationError: If the path fails validation.
            FileNotFoundError: If the validated path does not exist.
        """
        if not self.validate_path(path):
            raise PathValidationError(f"Access denied: {path}")

        decoded = unquote(unquote(path))
        if os.path.isabs(decoded):
            resolved = Path(decoded).resolve()
        else:
            resolved = (self._workspace_root / decoded).resolve()

        return resolved.read_text(encoding="utf-8")

    def safe_list_dir(self, path: str) -> list[str]:
        """Validate a path then list its directory contents (excluding hidden files).

        Args:
            path: Relative or absolute path to list.

        Returns:
            Sorted list of non-hidden file/directory names.

        Raises:
            PathValidationError: If the path fails validation.
            NotADirectoryError: If the validated path is not a directory.
        """
        if not self.validate_path(path):
            raise PathValidationError(f"Access denied: {path}")

        decoded = unquote(unquote(path))
        if os.path.isabs(decoded):
            resolved = Path(decoded).resolve()
        else:
            resolved = (self._workspace_root / decoded).resolve()

        if not resolved.is_dir():
            raise NotADirectoryError(f"Not a directory: {resolved}")

        return sorted(
            entry.name
            for entry in resolved.iterdir()
            if not entry.name.startswith(HIDDEN_FILE_PREFIX)
        )

    def validate_workspace_for_subprocess(self, workspace_path: str) -> bool:
        """Validate a workspace path is safe for use as subprocess cwd.

        Performs strict checks suitable for passing as cwd= to subprocess.run():
            - Path exists and is a directory
            - Path is within the allowed workspace root
            - No symlinks anywhere in the path chain

        Args:
            workspace_path: Absolute path to validate as subprocess cwd.

        Returns:
            True if safe for subprocess use, False otherwise.
        """
        try:
            resolved = Path(workspace_path).resolve()
        except (OSError, ValueError):
            logger.warning(
                "SUBPROCESS_BLOCKED: Invalid path — '%s'", workspace_path
            )
            return False

        # Must exist and be a directory
        if not resolved.exists():
            logger.warning(
                "SUBPROCESS_BLOCKED: Path does not exist — '%s'", workspace_path
            )
            return False

        if not resolved.is_dir():
            logger.warning(
                "SUBPROCESS_BLOCKED: Path is not a directory — '%s'", workspace_path
            )
            return False

        # Must be within workspace root
        try:
            resolved.relative_to(self._workspace_root)
        except ValueError:
            logger.warning(
                "SUBPROCESS_BLOCKED: Path outside workspace root — '%s' (root: '%s')",
                workspace_path,
                self._workspace_root,
            )
            return False

        # No symlinks in path chain
        if self._has_symlink_in_chain(resolved):
            logger.warning(
                "SUBPROCESS_BLOCKED: Symlink in path chain — '%s'", workspace_path
            )
            return False

        return True

    def _has_symlink_in_chain(self, resolved_path: Path) -> bool:
        """Check if any component in the path chain is a symlink.

        Walks from the workspace root down to the target, checking each
        intermediate path for symlinks.

        Args:
            resolved_path: The fully resolved path to check.

        Returns:
            True if any component is a symlink, False otherwise.
        """
        try:
            relative = resolved_path.relative_to(self._workspace_root)
        except ValueError:
            return True  # Outside workspace = treat as blocked

        current = self._workspace_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                return True
        return False
