from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine
from typing import Generator

# Lazy initialization to avoid import errors during app startup
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        from app.main import settings

        _engine = create_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
        )
    return _engine


def get_session_local():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=get_engine()
        )
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()
