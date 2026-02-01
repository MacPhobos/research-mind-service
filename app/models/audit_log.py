"""SQLAlchemy ORM model for audit log entries."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, Integer, String
from sqlalchemy.types import JSON

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuditLog(Base):
    """Records auditable actions within research sessions."""

    __tablename__ = "audit_logs"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    timestamp: datetime = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    session_id: str = Column(String(36), nullable=False)
    action: str = Column(String(50), nullable=False)
    query: str | None = Column(String(2048), nullable=True)
    result_count: int | None = Column(Integer, nullable=True)
    duration_ms: int | None = Column(Integer, nullable=True)
    status: str = Column(String(50), nullable=False, default="success")
    error: str | None = Column(String(2048), nullable=True)
    metadata_json = Column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_audit_session_id", "session_id"),
        Index("idx_audit_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.id}: {self.action} session={self.session_id}>"
