"""Tests for Clear Chat History endpoint (DELETE /api/v1/sessions/{session_id}/chat)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  -- ensure models registered with Base.metadata
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.chat_message import ChatMessage, ChatStatus


@pytest.fixture()
def tmp_content_sandbox(tmp_path):
    """Provide a temporary content sandbox root directory."""
    return str(tmp_path / "content_sandboxes")


@pytest.fixture()
def db_engine():
    """Create an in-memory SQLite engine shared across connections."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """Yield a SQLAlchemy session bound to the shared in-memory engine."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def client(db_engine, tmp_content_sandbox):
    """TestClient with overridden DB dependency and content_sandbox_root."""
    from app.core.config import settings

    # Override content_sandbox_root (bypass pydantic model immutability)
    original_content_sandbox_root = settings.content_sandbox_root
    object.__setattr__(settings, "content_sandbox_root", tmp_content_sandbox)

    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )

    def _override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()
    object.__setattr__(settings, "content_sandbox_root", original_content_sandbox_root)


def _create_session(client: TestClient, name: str = "Test Session") -> dict:
    """Helper to create a session and return its data."""
    response = client.post("/api/v1/sessions/", json={"name": name})
    assert response.status_code == 201, f"Failed to create session: {response.text}"
    return response.json()


def _create_chat_message(
    db_session, session_id: str, role: str, content: str
) -> ChatMessage:
    """Helper to create a chat message directly in the database."""
    message = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        status=ChatStatus.COMPLETED.value,
    )
    db_session.add(message)
    db_session.commit()
    db_session.refresh(message)
    return message


# ------------------------------------------------------------------
# DELETE /api/v1/sessions/{session_id}/chat
# ------------------------------------------------------------------


class TestClearChatHistory:
    """Test cases for the Clear Chat History endpoint."""

    def test_clear_chat_history_with_messages(
        self, client: TestClient, db_engine, tmp_content_sandbox: str
    ):
        """Clear chat history should delete all messages and return 204."""
        # Create a session
        session_data = _create_session(client, "Chat Test Session")
        session_id = session_data["session_id"]

        # Create messages directly in the database
        TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=db_engine
        )
        db = TestingSessionLocal()
        try:
            _create_chat_message(db, session_id, "user", "Hello")
            _create_chat_message(db, session_id, "assistant", "Hi there!")
            _create_chat_message(db, session_id, "user", "How are you?")

            # Verify messages exist
            message_count = (
                db.query(ChatMessage).filter_by(session_id=session_id).count()
            )
            assert message_count == 3
        finally:
            db.close()

        # Clear chat history
        response = client.delete(f"/api/v1/sessions/{session_id}/chat")
        assert response.status_code == 204
        assert response.content == b""

        # Verify messages are deleted
        db = TestingSessionLocal()
        try:
            message_count = (
                db.query(ChatMessage).filter_by(session_id=session_id).count()
            )
            assert message_count == 0
        finally:
            db.close()

    def test_clear_chat_history_no_messages(
        self, client: TestClient, tmp_content_sandbox: str
    ):
        """Clear chat history on empty session should return 204."""
        # Create a session with no messages
        session_data = _create_session(client, "Empty Chat Session")
        session_id = session_data["session_id"]

        # Clear chat history (should succeed even with no messages)
        response = client.delete(f"/api/v1/sessions/{session_id}/chat")
        assert response.status_code == 204
        assert response.content == b""

    def test_clear_chat_history_nonexistent_session(self, client: TestClient):
        """Clear chat history for non-existent session should return 404."""
        # Use a valid UUID v4 format that doesn't exist in the database
        # UUID v4 requires: 13th digit = '4', 17th digit in [8,9,a,b]
        nonexistent_uuid = "00000000-0000-4000-8000-000000000000"
        response = client.delete(f"/api/v1/sessions/{nonexistent_uuid}/chat")
        assert response.status_code == 404

        data = response.json()
        # FastAPI HTTPException wraps errors in "detail" key
        error_detail = data.get("detail", data)
        if isinstance(error_detail, dict) and "error" in error_detail:
            assert error_detail["error"]["code"] == "SESSION_NOT_FOUND"
            assert nonexistent_uuid in error_detail["error"]["message"]
        else:
            # Fallback for different error structure
            assert "SESSION_NOT_FOUND" in str(data) or "not found" in str(data).lower()

    def test_clear_chat_history_preserves_other_sessions(
        self, client: TestClient, db_engine, tmp_content_sandbox: str
    ):
        """Clear chat history should only affect the specified session."""
        # Create two sessions
        session_a = _create_session(client, "Session A")
        session_b = _create_session(client, "Session B")
        session_a_id = session_a["session_id"]
        session_b_id = session_b["session_id"]

        # Create messages in both sessions
        TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=db_engine
        )
        db = TestingSessionLocal()
        try:
            _create_chat_message(db, session_a_id, "user", "Message in A")
            _create_chat_message(db, session_b_id, "user", "Message in B")
        finally:
            db.close()

        # Clear only session A's chat history
        response = client.delete(f"/api/v1/sessions/{session_a_id}/chat")
        assert response.status_code == 204

        # Verify session A has no messages
        db = TestingSessionLocal()
        try:
            count_a = db.query(ChatMessage).filter_by(session_id=session_a_id).count()
            assert count_a == 0

            # Verify session B still has its message
            count_b = db.query(ChatMessage).filter_by(session_id=session_b_id).count()
            assert count_b == 1
        finally:
            db.close()
