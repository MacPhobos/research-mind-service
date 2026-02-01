"""Service layer for audit logging operations."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Static methods to create and query audit log entries.

    All write methods swallow exceptions so that audit logging never
    crashes the calling code path.
    """

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create_entry(
        db: Session,
        session_id: str,
        action: str,
        *,
        status: str = "success",
        query: str | None = None,
        result_count: int | None = None,
        duration_ms: int | None = None,
        error: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> None:
        """Persist a single audit entry, swallowing exceptions."""
        try:
            entry = AuditLog(
                session_id=session_id,
                action=action,
                status=status,
                query=query,
                result_count=result_count,
                duration_ms=duration_ms,
                error=error,
                metadata_json=metadata_json,
            )
            db.add(entry)
            db.commit()
        except Exception:
            logger.warning(
                "Failed to write audit log (action=%s, session=%s)",
                action,
                session_id,
                exc_info=True,
            )
            try:
                db.rollback()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public logging methods
    # ------------------------------------------------------------------

    @staticmethod
    def log_session_create(db: Session, session_id: str, name: str) -> None:
        AuditService._create_entry(
            db,
            session_id,
            "session_create",
            metadata_json={"name": name},
        )

    @staticmethod
    def log_session_delete(db: Session, session_id: str) -> None:
        AuditService._create_entry(db, session_id, "session_delete")

    @staticmethod
    def log_index_start(db: Session, session_id: str, workspace_path: str) -> None:
        AuditService._create_entry(
            db,
            session_id,
            "index_start",
            metadata_json={"workspace_path": workspace_path},
        )

    @staticmethod
    def log_index_complete(
        db: Session,
        session_id: str,
        elapsed_ms: int,
        stdout_summary: str = "",
    ) -> None:
        AuditService._create_entry(
            db,
            session_id,
            "index_complete",
            duration_ms=elapsed_ms,
            metadata_json={"stdout_summary": stdout_summary} if stdout_summary else None,
        )

    @staticmethod
    def log_subprocess_spawn(
        db: Session, session_id: str, command: str, workspace_path: str
    ) -> None:
        AuditService._create_entry(
            db,
            session_id,
            "subprocess_spawn",
            metadata_json={"command": command, "workspace_path": workspace_path},
        )

    @staticmethod
    def log_subprocess_complete(
        db: Session,
        session_id: str,
        command: str,
        exit_code: int,
        elapsed_ms: int,
        stdout_summary: str = "",
    ) -> None:
        AuditService._create_entry(
            db,
            session_id,
            "subprocess_complete",
            duration_ms=elapsed_ms,
            metadata_json={
                "command": command,
                "exit_code": exit_code,
                "stdout_summary": stdout_summary,
            },
        )

    @staticmethod
    def log_subprocess_error(
        db: Session,
        session_id: str,
        command: str,
        exit_code: int,
        elapsed_ms: int,
        stderr_summary: str = "",
    ) -> None:
        AuditService._create_entry(
            db,
            session_id,
            "subprocess_error",
            status="failed",
            duration_ms=elapsed_ms,
            error=stderr_summary or None,
            metadata_json={"command": command, "exit_code": exit_code},
        )

    @staticmethod
    def log_subprocess_timeout(
        db: Session,
        session_id: str,
        command: str,
        timeout_seconds: int,
        workspace_path: str,
    ) -> None:
        AuditService._create_entry(
            db,
            session_id,
            "subprocess_timeout",
            status="failed",
            error=f"Subprocess timed out after {timeout_seconds}s",
            metadata_json={
                "command": command,
                "timeout_seconds": timeout_seconds,
                "workspace_path": workspace_path,
            },
        )

    @staticmethod
    def log_failed_request(
        db: Session, session_id: str, action: str, error: str
    ) -> None:
        AuditService._create_entry(
            db,
            session_id,
            "failed_request",
            status="failed",
            error=error,
            metadata_json={"original_action": action},
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    @staticmethod
    def get_audit_logs(
        db: Session,
        session_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        """Return audit logs for a session with pagination.

        Returns:
            Tuple of (list_of_logs, total_count).
        """
        query = (
            db.query(AuditLog)
            .filter(AuditLog.session_id == session_id)
            .order_by(AuditLog.timestamp.desc())
        )
        total = query.count()
        logs = query.offset(offset).limit(limit).all()
        return logs, total
