"""Audit log REST endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.session import Session as SessionModel
from app.schemas.audit import AuditLogListResponse
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/v1/sessions", tags=["audit"])


@router.get("/{session_id}/audit", response_model=AuditLogListResponse)
def get_audit_logs(
    session_id: str,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> AuditLogListResponse:
    """Retrieve audit logs for a session."""
    # Verify session exists
    session = db.query(SessionModel).filter_by(session_id=session_id).first()
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

    logs, total = AuditService.get_audit_logs(db, session_id, limit=limit, offset=offset)
    return AuditLogListResponse(logs=logs, count=total)
