"""SQLAlchemy ORM model for chat messages within sessions."""

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


class ChatRole(str, enum.Enum):
    """Message author role."""

    USER = "user"
    ASSISTANT = "assistant"


class ChatStatus(str, enum.Enum):
    """Message lifecycle status."""

    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETED = "completed"
    ERROR = "error"


class ChatMessage(Base):
    """A chat message within a research session."""

    __tablename__ = "chat_messages"

    message_id: str = Column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    session_id: str = Column(
        String(36),
        ForeignKey("sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )

    role: str = Column(String(20), nullable=False)
    content: str = Column(Text, nullable=False)
    status: str = Column(
        String(20), nullable=False, default=ChatStatus.PENDING.value
    )
    error_message: str | None = Column(Text, nullable=True)

    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    completed_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

    token_count: int | None = Column(Integer, nullable=True)
    duration_ms: int | None = Column(Integer, nullable=True)
    metadata_json = Column(JSON, nullable=True, default=dict)

    __table_args__ = (
        Index("idx_chat_messages_session_id", "session_id"),
        Index("idx_chat_messages_created_at", "created_at"),
        Index("idx_chat_messages_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<ChatMessage {self.message_id}: role={self.role} status={self.status}>"
