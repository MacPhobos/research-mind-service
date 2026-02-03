"""Placeholder retriever for MCP-based content sources (MVP stub)."""

from __future__ import annotations

from pathlib import Path

from app.services.retrievers.base import RetrievalResult


class McpSourceRetriever:
    """Placeholder. MCP source retrieval is not implemented in MVP."""

    def retrieve(
        self,
        *,
        source: str,
        target_dir: Path,
        title: str | None = None,
        metadata: dict | None = None,
    ) -> RetrievalResult:
        return RetrievalResult(
            success=False,
            storage_path=str(target_dir.name),
            size_bytes=0,
            mime_type=None,
            title=title or source,
            metadata={"source_uri": source},
            error_message="MCP source retrieval is not yet implemented.",
        )
