"""SQLAlchemy ORM model for research sessions."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Session(Base):
    """Represents a research session with an associated workspace directory."""

    __tablename__ = "sessions"

    session_id: str = Column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    name: str = Column(String(255), nullable=False)
    description: str | None = Column(String(1024), nullable=True)
    workspace_path: str = Column(String(512), nullable=False, unique=True)

    created_at: datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    last_accessed: datetime = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    status: str = Column(String(50), nullable=False, default="active")
    archived: bool = Column(Boolean, nullable=False, default=False)
    ttl_seconds: int | None = Column(Integer, nullable=True)

    # ------------------------------------------------------------------
    # Instance helpers
    # ------------------------------------------------------------------

    def mark_accessed(self) -> None:
        """Update last_accessed to current UTC time."""
        self.last_accessed = _utcnow()

    def is_active(self) -> bool:
        """Return True when status is 'active' and session is not archived."""
        return self.status == "active" and not self.archived

    def is_indexed(self) -> bool:
        """Return True if a .mcp-vector-search/ directory exists in the workspace."""
        if not self.workspace_path:
            return False
        index_dir = os.path.join(self.workspace_path, ".mcp-vector-search")
        return os.path.isdir(index_dir)

    def to_dict(self) -> dict:
        """Serialise the model to a plain dictionary."""
        return {
            "session_id": self.session_id,
            "name": self.name,
            "description": self.description,
            "workspace_path": self.workspace_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "status": self.status,
            "archived": self.archived,
            "ttl_seconds": self.ttl_seconds,
            "is_indexed": self.is_indexed(),
        }

    def __repr__(self) -> str:
        return f"<Session {self.session_id}: {self.name}>"
