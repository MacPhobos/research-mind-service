"""Retriever for URL content."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from app.core.config import settings
from app.services.retrievers.base import RetrievalResult

logger = logging.getLogger(__name__)


class UrlRetriever:
    """Fetch URL content, store as markdown/text in sandbox."""

    def __init__(self, timeout: int | None = None) -> None:
        self._timeout = timeout if timeout is not None else settings.url_fetch_timeout

    def retrieve(
        self,
        *,
        source: str,
        target_dir: Path,
        title: str | None = None,
        metadata: dict | None = None,
    ) -> RetrievalResult:
        url = source

        try:
            with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
                response = client.get(url, headers={"User-Agent": "research-mind/0.1"})
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            return RetrievalResult(
                success=False,
                storage_path=str(target_dir.name),
                size_bytes=0,
                mime_type=None,
                title=title or url,
                metadata={"url": url},
                error_message=f"HTTP {exc.response.status_code}: {exc.response.reason_phrase}",
            )
        except httpx.RequestError as exc:
            return RetrievalResult(
                success=False,
                storage_path=str(target_dir.name),
                size_bytes=0,
                mime_type=None,
                title=title or url,
                metadata={"url": url},
                error_message=f"Request failed: {exc}",
            )

        content_bytes = response.content
        if len(content_bytes) > settings.max_url_response_bytes:
            return RetrievalResult(
                success=False,
                storage_path=str(target_dir.name),
                size_bytes=0,
                mime_type=None,
                title=title or url,
                metadata={"url": url},
                error_message=f"Response exceeds maximum size: {len(content_bytes)} bytes",
            )

        content_type = response.headers.get("content-type", "")
        resolved_title = title or url

        # Write content
        content_file = target_dir / "content.md"
        content_file.write_bytes(content_bytes)

        # Write metadata
        meta = {
            "url": url,
            "status_code": response.status_code,
            "content_type": content_type,
            "content_length": len(content_bytes),
            **(metadata or {}),
        }
        meta_file = target_dir / "metadata.json"
        meta_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        return RetrievalResult(
            success=True,
            storage_path=str(target_dir.name),
            size_bytes=len(content_bytes),
            mime_type=content_type.split(";")[0].strip() if content_type else None,
            title=resolved_title,
            metadata=meta,
        )
