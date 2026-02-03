"""Base protocol for content retrievers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RetrievalResult:
    """Result returned by a content retriever after fetching content."""

    success: bool
    storage_path: str  # Relative path within session workspace
    size_bytes: int  # Total bytes written to disk
    mime_type: str | None  # Primary content MIME type
    title: str  # Display title (may be refined by retriever)
    metadata: dict  # Retriever-specific metadata
    error_message: str | None = None  # Set when success=False


class ContentRetriever(Protocol):
    """Protocol that all content retrievers must implement.

    Each retriever handles one content type. The retriever is responsible
    for:
    1. Accepting a source reference (URL, text, file bytes, etc.)
    2. Fetching/processing the content
    3. Writing files to the provided target directory
    4. Returning a RetrievalResult with metadata

    The target_dir is pre-created by ContentService and lives within
    the content sandbox: {content_sandbox_root}/{session_id}/{content_id}/
    """

    def retrieve(
        self,
        *,
        source: str | bytes,
        target_dir: Path,
        title: str | None = None,
        metadata: dict | None = None,
    ) -> RetrievalResult:
        """Fetch content and store it in target_dir.

        Args:
            source: The source reference. Semantics depend on content type:
                - file_upload: raw file bytes
                - text: raw text string
                - url: URL string to fetch
                - git_repo: git clone URL
                - mcp_source: MCP resource URI
            target_dir: Pre-created directory to write content into.
            title: Optional display title hint. Retriever may override.
            metadata: Optional extra metadata from the request.

        Returns:
            RetrievalResult with outcome details.
        """
        ...
