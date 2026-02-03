"""Retriever for git repository cloning."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from app.core.config import settings
from app.services.retrievers.base import RetrievalResult

logger = logging.getLogger(__name__)


class GitRepoRetriever:
    """Clone a git repo (shallow) into the sandbox."""

    def __init__(
        self,
        timeout: int | None = None,
        depth: int | None = None,
    ) -> None:
        self._timeout = timeout if timeout is not None else settings.git_clone_timeout
        self._depth = depth if depth is not None else settings.git_clone_depth

    def retrieve(
        self,
        *,
        source: str,
        target_dir: Path,
        title: str | None = None,
        metadata: dict | None = None,
    ) -> RetrievalResult:
        clone_url = source
        repo_dir = target_dir / "repo"
        resolved_title = (
            title or clone_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        )

        cmd = [
            "git",
            "clone",
            "--depth",
            str(self._depth),
            "--single-branch",
            clone_url,
            str(repo_dir),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            return RetrievalResult(
                success=False,
                storage_path=str(target_dir.name),
                size_bytes=0,
                mime_type=None,
                title=resolved_title,
                metadata={"clone_url": clone_url},
                error_message=f"Git clone timed out after {self._timeout}s",
            )
        except FileNotFoundError:
            return RetrievalResult(
                success=False,
                storage_path=str(target_dir.name),
                size_bytes=0,
                mime_type=None,
                title=resolved_title,
                metadata={"clone_url": clone_url},
                error_message="git CLI not found on PATH",
            )

        if result.returncode != 0:
            return RetrievalResult(
                success=False,
                storage_path=str(target_dir.name),
                size_bytes=0,
                mime_type=None,
                title=resolved_title,
                metadata={"clone_url": clone_url},
                error_message=f"git clone failed (exit {result.returncode}): {result.stderr.strip()}",
            )

        # Calculate total size
        total_bytes = sum(
            f.stat().st_size for f in repo_dir.rglob("*") if f.is_file()
        )

        # Write metadata
        meta = {
            "clone_url": clone_url,
            "depth": self._depth,
            "total_bytes": total_bytes,
            **(metadata or {}),
        }
        meta_file = target_dir / "metadata.json"
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        return RetrievalResult(
            success=True,
            storage_path=str(target_dir.name),
            size_bytes=total_bytes,
            mime_type=None,
            title=resolved_title,
            metadata=meta,
        )
