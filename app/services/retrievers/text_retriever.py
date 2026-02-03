"""Retriever for raw text content."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.config import settings
from app.services.retrievers.base import RetrievalResult

logger = logging.getLogger(__name__)


class TextRetriever:
    """Accept raw text and save as a file in the sandbox."""

    def retrieve(
        self,
        *,
        source: str,
        target_dir: Path,
        title: str | None = None,
        metadata: dict | None = None,
    ) -> RetrievalResult:
        text = source
        title = title or "Untitled text"

        encoded = text.encode("utf-8")
        if len(encoded) > settings.max_text_bytes:
            return RetrievalResult(
                success=False,
                storage_path=str(target_dir.name),
                size_bytes=0,
                mime_type=None,
                title=title,
                metadata={},
                error_message=f"Text exceeds maximum size: {len(encoded)} bytes",
            )

        # Write text content
        content_file = target_dir / "content.txt"
        content_file.write_text(text, encoding="utf-8")

        # Write metadata
        meta = {"title": title, **(metadata or {})}
        meta_file = target_dir / "metadata.json"
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        return RetrievalResult(
            success=True,
            storage_path=str(target_dir.name),
            size_bytes=len(encoded),
            mime_type="text/plain",
            title=title,
            metadata=meta,
        )
