"""Workspace indexing REST endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.workspace_indexer import (
    IndexingTimeoutError,
    ToolNotFoundError,
    WorkspaceNotFoundError,
)
from app.db.session import get_db
from app.schemas.indexing import (
    IndexResultResponse,
    IndexStatusResponse,
    IndexWorkspaceRequest,
)
from app.services import session_service
from app.services.indexing_service import IndexingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workspaces", tags=["indexing"])


def _get_session_or_404(db: Session, workspace_id: str):
    """Fetch session by workspace_id or raise 404."""
    result = session_service.get_session(db, workspace_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"Session '{workspace_id}' not found",
                }
            },
        )
    return result


@router.post(
    "/{workspace_id}/index",
    response_model=IndexResultResponse,
)
def index_workspace(
    workspace_id: str,
    request: IndexWorkspaceRequest | None = None,
    db: Session = Depends(get_db),
) -> IndexResultResponse:
    """Trigger indexing for a workspace."""
    session = _get_session_or_404(db, workspace_id)

    force = True
    timeout = None
    if request is not None:
        force = request.force
        timeout = request.timeout

    try:
        result = IndexingService.index_workspace(
            workspace_path=session.workspace_path,
            force=force,
            timeout=timeout,
        )
    except WorkspaceNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "WORKSPACE_NOT_FOUND",
                    "message": f"Workspace directory not found for session '{workspace_id}'",
                }
            },
        )
    except ToolNotFoundError:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "TOOL_NOT_FOUND",
                    "message": "mcp-vector-search CLI is not available on PATH",
                }
            },
        )
    except IndexingTimeoutError:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "INDEXING_TIMEOUT",
                    "message": "Indexing operation timed out",
                }
            },
        )

    return IndexResultResponse(
        workspace_id=workspace_id,
        success=result.success,
        status="completed" if result.success else "failed",
        elapsed_seconds=result.elapsed_seconds,
        stdout=result.stdout or None,
        stderr=result.stderr or None,
    )


@router.get(
    "/{workspace_id}/index/status",
    response_model=IndexStatusResponse,
)
def get_index_status(
    workspace_id: str,
    db: Session = Depends(get_db),
) -> IndexStatusResponse:
    """Check the indexing status of a workspace."""
    session = _get_session_or_404(db, workspace_id)

    status_info = IndexingService.check_index_status(session.workspace_path)

    return IndexStatusResponse(
        workspace_id=workspace_id,
        is_indexed=status_info["is_indexed"],
        status=status_info["status"],
        message=status_info["message"],
    )
