"""Business logic for session CRUD operations."""

from __future__ import annotations

import logging
import os
import shutil
from uuid import uuid4

from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.models.content_item import ContentItem
from app.models.session import Session
from app.schemas.session import CreateSessionRequest, SessionResponse, UpdateSessionRequest

logger = logging.getLogger(__name__)


def _build_response(session: Session, db: DbSession | None = None) -> SessionResponse:
    """Convert an ORM Session into a SessionResponse with is_indexed and content_count.

    Args:
        session: The ORM Session object.
        db: Optional database session for querying content count.
            If not provided, content_count defaults to 0.
    """
    content_count = 0
    if db is not None:
        content_count = (
            db.query(ContentItem)
            .filter(ContentItem.session_id == session.session_id)
            .count()
        )

    return SessionResponse(
        session_id=session.session_id,
        name=session.name,
        description=session.description,
        workspace_path=session.workspace_path,
        created_at=session.created_at,
        last_accessed=session.last_accessed,
        status=session.status,
        archived=session.archived,
        ttl_seconds=session.ttl_seconds,
        is_indexed=session.is_indexed(),
        content_count=content_count,
    )


def create_session(db: DbSession, request: CreateSessionRequest) -> SessionResponse:
    """Create a new session, persist it, and create the workspace directory."""
    # Generate session_id eagerly so we can derive workspace_path
    session_id = str(uuid4())
    workspace_path = os.path.join(settings.workspace_root, session_id)

    session = Session(
        session_id=session_id,
        name=request.name,
        description=request.description,
        workspace_path=workspace_path,
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    # Create workspace directory on disk
    os.makedirs(session.workspace_path, exist_ok=True)
    logger.info("Created session %s at %s", session.session_id, session.workspace_path)

    return _build_response(session, db)


def get_session(db: DbSession, session_id: str) -> SessionResponse | None:
    """Fetch a session by ID and update last_accessed. Returns None if not found."""
    session = db.query(Session).filter(Session.session_id == session_id).first()
    if session is None:
        return None

    session.mark_accessed()
    db.commit()
    db.refresh(session)

    return _build_response(session, db)


def list_sessions(
    db: DbSession, limit: int = 20, offset: int = 0
) -> tuple[list[SessionResponse], int]:
    """Return a paginated list of sessions and total count."""
    total = db.query(Session).count()
    rows = (
        db.query(Session)
        .order_by(Session.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    sessions = [_build_response(s, db) for s in rows]
    return sessions, total


def update_session(
    db: DbSession, session_id: str, request: UpdateSessionRequest
) -> SessionResponse | None:
    """Update a session's mutable fields (name, description, status).

    Returns the updated SessionResponse, or None if session not found.
    """
    session = db.query(Session).filter(Session.session_id == session_id).first()
    if session is None:
        return None

    # Update only fields that are provided (not None)
    if request.name is not None:
        session.name = request.name
    if request.description is not None:
        session.description = request.description
    if request.status is not None:
        session.status = request.status

    session.mark_accessed()
    db.commit()
    db.refresh(session)

    logger.info("Updated session %s", session_id)
    return _build_response(session, db)


def delete_session(db: DbSession, session_id: str) -> bool:
    """Delete a session record and remove its workspace and content sandbox.

    Returns True if the session was found and deleted, False otherwise.
    """
    session = db.query(Session).filter(Session.session_id == session_id).first()
    if session is None:
        return False

    workspace = session.workspace_path

    db.delete(session)
    db.commit()

    # Clean up workspace directory
    if workspace and os.path.isdir(workspace):
        shutil.rmtree(workspace, ignore_errors=True)
        logger.info("Removed workspace directory %s", workspace)

    # Clean up content sandbox directory
    content_sandbox = os.path.join(settings.content_sandbox_root, session_id)
    if os.path.isdir(content_sandbox):
        shutil.rmtree(content_sandbox, ignore_errors=True)
        logger.info("Removed content sandbox directory %s", content_sandbox)

    logger.info("Deleted session %s", session_id)
    return True
