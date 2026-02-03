"""Business logic for content management operations."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.models.content_item import ContentItem, ContentStatus
from app.models.session import Session
from app.schemas.content import AddContentRequest, ContentItemResponse, ContentListResponse
from app.services.retrievers.factory import get_retriever

logger = logging.getLogger(__name__)


def _get_session_or_raise(db: DbSession, session_id: str) -> Session:
    """Fetch session by ID or raise 404."""
    session = db.query(Session).filter(Session.session_id == session_id).first()
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Session '{session_id}' not found",
                }
            },
        )
    return session


def _build_response(item: ContentItem) -> ContentItemResponse:
    """Convert ORM ContentItem into ContentItemResponse."""
    return ContentItemResponse(
        content_id=item.content_id,
        session_id=item.session_id,
        content_type=item.content_type,
        title=item.title,
        source_ref=item.source_ref,
        storage_path=item.storage_path,
        status=item.status,
        error_message=item.error_message,
        size_bytes=item.size_bytes,
        mime_type=item.mime_type,
        metadata_json=item.metadata_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def add_content(
    db: DbSession, session_id: str, request: AddContentRequest
) -> ContentItemResponse:
    """Add content to a session using the appropriate retriever.

    1. Validate session exists
    2. Create ContentItem record (status=processing)
    3. Get retriever for content_type
    4. Create target directory in content sandbox
    5. Call retriever.retrieve()
    6. Update ContentItem with result
    7. Return response
    """
    # Validate session exists
    session = _get_session_or_raise(db, session_id)

    # Generate content_id
    content_id = str(uuid4())

    # Create content item record with processing status
    item = ContentItem(
        content_id=content_id,
        session_id=session_id,
        content_type=request.content_type,
        title=request.title or f"Content {content_id[:8]}",
        source_ref=request.source,
        status=ContentStatus.PROCESSING.value,
        metadata_json=request.metadata or {},
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    # Create target directory in content sandbox
    # Structure: {content_sandbox_root}/{session_id}/{content_id}/
    target_dir = Path(settings.content_sandbox_root) / session_id / content_id
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Get the appropriate retriever
        retriever = get_retriever(request.content_type)

        # Determine source value
        source = request.source or ""

        # Call retriever
        result = retriever.retrieve(
            source=source,
            target_dir=target_dir,
            title=request.title,
            metadata=request.metadata,
        )

        if result.success:
            item.status = ContentStatus.READY.value
            item.storage_path = result.storage_path
            item.size_bytes = result.size_bytes
            item.mime_type = result.mime_type
            item.title = result.title  # Retriever may refine title
            # Merge retriever metadata with request metadata
            merged_meta = dict(item.metadata_json or {})
            merged_meta.update(result.metadata or {})
            item.metadata_json = merged_meta
        else:
            item.status = ContentStatus.ERROR.value
            item.error_message = result.error_message

    except ValueError as e:
        # Unknown content type or validation error
        item.status = ContentStatus.ERROR.value
        item.error_message = str(e)
        logger.warning("Content retrieval failed for %s: %s", content_id, e)
    except Exception as e:
        item.status = ContentStatus.ERROR.value
        item.error_message = f"Unexpected error: {e}"
        logger.exception("Unexpected error retrieving content %s", content_id)

    db.commit()
    db.refresh(item)

    # Touch session last_accessed
    session.mark_accessed()
    db.commit()

    logger.info(
        "Added content %s to session %s (type=%s, status=%s)",
        content_id,
        session_id,
        request.content_type,
        item.status,
    )

    return _build_response(item)


def list_content(
    db: DbSession, session_id: str, limit: int = 50, offset: int = 0
) -> ContentListResponse:
    """List all content items for a session with pagination."""
    # Validate session exists
    _get_session_or_raise(db, session_id)

    query = (
        db.query(ContentItem)
        .filter(ContentItem.session_id == session_id)
        .order_by(ContentItem.created_at.desc())
    )
    total = query.count()
    items = query.offset(offset).limit(limit).all()

    return ContentListResponse(
        items=[_build_response(item) for item in items],
        count=total,
    )


def get_content(db: DbSession, session_id: str, content_id: str) -> ContentItemResponse:
    """Get a single content item by ID."""
    # Validate session exists
    _get_session_or_raise(db, session_id)

    item = (
        db.query(ContentItem)
        .filter(
            ContentItem.session_id == session_id,
            ContentItem.content_id == content_id,
        )
        .first()
    )

    if item is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "CONTENT_NOT_FOUND",
                    "message": f"Content '{content_id}' not found in session '{session_id}'",
                }
            },
        )

    return _build_response(item)


def delete_content(db: DbSession, session_id: str, content_id: str) -> bool:
    """Delete a content item and its storage files.

    Returns True if found and deleted, False if not found.
    """
    # Validate session exists
    _get_session_or_raise(db, session_id)

    item = (
        db.query(ContentItem)
        .filter(
            ContentItem.session_id == session_id,
            ContentItem.content_id == content_id,
        )
        .first()
    )

    if item is None:
        return False

    # Get storage path before deleting record
    content_dir = Path(settings.content_sandbox_root) / session_id / content_id

    # Delete database record
    db.delete(item)
    db.commit()

    # Clean up storage directory
    if content_dir.exists():
        shutil.rmtree(content_dir, ignore_errors=True)
        logger.info("Removed content directory %s", content_dir)

    logger.info("Deleted content %s from session %s", content_id, session_id)
    return True
