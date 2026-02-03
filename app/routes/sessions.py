"""Session management REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.session import (
    CreateSessionRequest,
    SessionListResponse,
    SessionResponse,
    UpdateSessionRequest,
)
from app.services import session_service

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.post("/", response_model=SessionResponse, status_code=201)
def create_session(
    request: CreateSessionRequest,
    db: Session = Depends(get_db),
) -> SessionResponse:
    """Create a new research session."""
    return session_service.create_session(db, request)


@router.get("/", response_model=SessionListResponse)
def list_sessions(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> SessionListResponse:
    """List sessions with pagination."""
    sessions, total = session_service.list_sessions(db, limit=limit, offset=offset)
    return SessionListResponse(sessions=sessions, count=total)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> SessionResponse:
    """Retrieve a single session by ID."""
    result = session_service.get_session(db, session_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Session '{session_id}' not found",
                }
            },
        )
    return result


@router.patch("/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    db: Session = Depends(get_db),
) -> SessionResponse:
    """Update a session's mutable fields (name, description, status)."""
    result = session_service.update_session(db, session_id, request)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Session '{session_id}' not found",
                }
            },
        )
    return result


@router.delete("/{session_id}", status_code=204, response_model=None)
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a session and its workspace directory."""
    deleted = session_service.delete_session(db, session_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Session '{session_id}' not found",
                }
            },
        )
