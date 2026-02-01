"""
Session model for research-mind.

Persists session metadata, workspace configuration, and indexing state.
Completed during Phase 1.2, stub created in Phase 1.0.
"""

from datetime import datetime
from uuid import uuid4
from sqlalchemy import Column, String, DateTime, Integer, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Session(Base):
    """
    Session record persisting research context.

    Fields:
    - session_id: UUID v4 identifier (immutable)
    - name: Human-readable session name
    - description: Optional session description
    - workspace_path: Root directory for session content (/var/lib/research-mind/sessions/{id})
    - created_at: Session creation timestamp (UTC)
    - last_accessed: Last activity timestamp (UTC)
    - status: Session lifecycle status (active, archived, deleted)
    - index_stats: JSON blob tracking index metadata
      - file_count: Number of indexed files
      - chunk_count: Number of indexed chunks
      - total_size_bytes: Total indexed content size
      - last_indexed_at: Timestamp of last indexing job
    """

    __tablename__ = "sessions"

    # Primary key
    session_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))

    # Metadata
    name = Column(String(255), nullable=False)
    description = Column(String(1024), nullable=True)
    workspace_path = Column(String(512), nullable=False, unique=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_accessed = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Status and configuration
    status = Column(String(50), nullable=False, default="active")

    # Index metadata (JSON)
    index_stats = Column(
        JSON,
        nullable=True,
        default={
            "file_count": 0,
            "chunk_count": 0,
            "total_size_bytes": 0,
            "last_indexed_at": None,
        },
    )

    def __repr__(self):
        return f"<Session {self.session_id}: {self.name}>"
