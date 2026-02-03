"""Content management REST endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.content import AddContentRequest, ContentItemResponse, ContentListResponse
from app.services import content_service

router = APIRouter(prefix="/api/v1/sessions/{session_id}/content", tags=["content"])


@router.post("/", response_model=ContentItemResponse, status_code=201)
def add_content(
    session_id: str,
    content_type: str = Form(..., description="Content type: text, file_upload, url, git_repo"),
    title: str | None = Form(None, max_length=512, description="Content title"),
    source: str | None = Form(None, max_length=2048, description="Source reference (URL, text)"),
    metadata: str | None = Form(None, description="JSON string of additional metadata"),
    file: UploadFile | None = File(None, description="File to upload (for file_upload type)"),
    db: Session = Depends(get_db),
) -> ContentItemResponse:
    """Add content to a session.

    Supports multiple content types:
    - text: Plain text content (source contains the text)
    - file_upload: Upload a file (use the file parameter)
    - url: Fetch content from URL (source contains the URL)
    - git_repo: Clone a git repository (source contains the repo URL)
    """
    import json

    # Parse metadata JSON if provided
    parsed_metadata: dict[str, Any] | None = None
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "code": "INVALID_METADATA",
                        "message": "metadata must be valid JSON",
                    }
                },
            )

    # Handle file upload - store file info in metadata for retriever
    if file and content_type == "file_upload":
        # Read file content and pass to retriever via metadata
        file_content = file.file.read()
        file.file.seek(0)  # Reset for potential re-read

        if parsed_metadata is None:
            parsed_metadata = {}

        parsed_metadata["_upload_filename"] = file.filename
        parsed_metadata["_upload_content_type"] = file.content_type
        parsed_metadata["_upload_size"] = len(file_content)
        parsed_metadata["_upload_content"] = file_content

    # Build request object
    request = AddContentRequest(
        content_type=content_type,
        title=title,
        source=source,
        metadata=parsed_metadata,
    )

    return content_service.add_content(db, session_id, request)


@router.get("/", response_model=ContentListResponse)
def list_content(
    session_id: str,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> ContentListResponse:
    """List all content items for a session with pagination."""
    return content_service.list_content(db, session_id, limit=limit, offset=offset)


@router.get("/{content_id}", response_model=ContentItemResponse)
def get_content(
    session_id: str,
    content_id: str,
    db: Session = Depends(get_db),
) -> ContentItemResponse:
    """Get a single content item by ID."""
    return content_service.get_content(db, session_id, content_id)


@router.delete("/{content_id}", status_code=204, response_model=None)
def delete_content(
    session_id: str,
    content_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a content item and its storage files."""
    deleted = content_service.delete_content(db, session_id, content_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "CONTENT_NOT_FOUND",
                    "message": f"Content '{content_id}' not found in session '{session_id}'",
                }
            },
        )
