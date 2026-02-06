"""SQLAlchemy ORM model for content items within sessions."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.types import JSON

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ContentType(str, enum.Enum):
    """Supported content source types."""

    FILE_UPLOAD = "file_upload"
    TEXT = "text"
    URL = "url"
    GIT_REPO = "git_repo"
    MCP_SOURCE = "mcp_source"
    DOCUMENT = "document"


class ContentStatus(str, enum.Enum):
    """Lifecycle status of a content item."""

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class ContentItem(Base):
    """A piece of content added to a research session."""

    __tablename__ = "content_items"

    content_id: str = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id: str = Column(
        String(36),
        ForeignKey("sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )

    # What kind of content this is
    content_type: str = Column(String(20), nullable=False)

    # Human-readable label (filename, URL, repo name, etc.)
    title: str = Column(String(512), nullable=False)

    # Original source reference (file path, URL, git URL, etc.)
    source_ref: str | None = Column(String(2048), nullable=True)

    # Path within the session workspace where content is stored
    # Relative to session workspace: {content_id}/
    storage_path: str | None = Column(String(512), nullable=True)

    # Lifecycle status
    status: str = Column(
        String(20), nullable=False, default=ContentStatus.PENDING.value
    )

    # Error message when status=error
    error_message: str | None = Column(Text, nullable=True)

    # Size in bytes of stored content
    size_bytes: int | None = Column(Integer, nullable=True)

    # MIME type of the primary content file
    mime_type: str | None = Column(String(128), nullable=True)

    # Flexible metadata (original filename, headers, git commit, etc.)
    metadata_json = Column(JSON, nullable=True, default=dict)

    # Timestamps
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: datetime = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        Index("idx_content_session_id", "session_id"),
        Index("idx_content_status", "status"),
        Index("idx_content_type", "content_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<ContentItem {self.content_id}: "
            f"type={self.content_type} status={self.status}>"
        )
