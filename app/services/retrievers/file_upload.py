"""Retriever for multipart file uploads."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from app.core.config import settings
from app.services.retrievers.base import RetrievalResult

logger = logging.getLogger(__name__)


class FileUploadRetriever:
    """Handle multipart file uploads by saving to sandbox."""

    def retrieve(
        self,
        *,
        source: bytes,
        target_dir: Path,
        title: str | None = None,
        metadata: dict | None = None,
    ) -> RetrievalResult:
        filename = (metadata or {}).get("original_filename", "upload")
        title = title or filename

        # Validate size
        if len(source) > settings.max_upload_bytes:
            return RetrievalResult(
                success=False,
                storage_path=str(target_dir.name),
                size_bytes=0,
                mime_type=None,
                title=title,
                metadata={},
                error_message=(
                    f"File exceeds maximum size: "
                    f"{len(source)} bytes > {settings.max_upload_bytes} bytes"
                ),
            )

        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(filename)

        # Write file
        dest = target_dir / filename
        dest.write_bytes(source)

        return RetrievalResult(
            success=True,
            storage_path=str(target_dir.name),
            size_bytes=len(source),
            mime_type=mime_type,
            title=title,
            metadata={
                "original_filename": filename,
            },
        )
