"""Database engine, session factory, and FastAPI dependency."""

from __future__ import annotations

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base

# Lazy initialization to avoid import errors during app startup
_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the global SQLAlchemy engine (created lazily)."""
    global _engine
    if _engine is None:
        from app.core.config import settings

        connect_args: dict = {}
        url = settings.database_url

        # SQLite needs check_same_thread=False for FastAPI
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        _engine = create_engine(
            url,
            echo=False,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _engine


def get_session_local() -> sessionmaker[Session]:
    """Return the global session factory (created lazily)."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()


def create_all_tables() -> None:
    """Create all tables from ORM metadata (dev convenience)."""
    Base.metadata.create_all(bind=get_engine())


def reset_engine() -> None:
    """Reset cached engine and session factory. Used by tests."""
    global _engine, _SessionLocal
    _engine = None
    _SessionLocal = None
