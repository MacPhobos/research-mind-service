"""Tests for chat export endpoints.

Tests cover:
- Full chat history export (PDF and Markdown)
- Single Q/A pair export
- Error cases (no messages, invalid format, not assistant message, etc.)
"""

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
from app.models.chat_message import ChatMessage, ChatRole, ChatStatus
from app.models.session import Session as SessionModel
from app.services.export.pdf import WEASYPRINT_AVAILABLE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    """Create a database session for tests."""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture()
def client(db_session, tmp_path):
    """TestClient with overridden DB dependency."""
    from app.core.config import settings

    # Override content sandbox root
    original_sandbox = settings.content_sandbox_root
    object.__setattr__(settings, "content_sandbox_root", str(tmp_path / "sandboxes"))

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()
    object.__setattr__(settings, "content_sandbox_root", original_sandbox)


@pytest.fixture()
def session_with_messages(db_session, tmp_path) -> str:
    """Create a session with chat messages for testing."""
    # Use valid UUID v4 format to pass middleware validation
    # UUID v4 format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx (y = 8, 9, a, or b)
    session_id = "11111111-1111-4111-a111-111111111111"
    user_msg_id = "22222222-2222-4222-a222-222222222222"
    assistant_msg_id = "33333333-3333-4333-a333-333333333333"

    # Create workspace directory
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create session
    session = SessionModel(
        session_id=session_id,
        name="Test Session",
        description="A test session with messages",
        workspace_path=str(workspace),
        status="active",
    )
    db_session.add(session)
    db_session.commit()

    # Create user message
    user_msg = ChatMessage(
        message_id=user_msg_id,
        session_id=session_id,
        role=ChatRole.USER.value,
        content="What is Python?",
        status=ChatStatus.COMPLETED.value,
    )
    db_session.add(user_msg)
    db_session.commit()

    # Create assistant message (after user message)
    assistant_msg = ChatMessage(
        message_id=assistant_msg_id,
        session_id=session_id,
        role=ChatRole.ASSISTANT.value,
        content="Python is a high-level, interpreted programming language known for its clear syntax and readability.",
        status=ChatStatus.COMPLETED.value,
    )
    db_session.add(assistant_msg)
    db_session.commit()

    return session_id


@pytest.fixture()
def empty_session(db_session, tmp_path) -> str:
    """Create a session without any chat messages."""
    session_id = "44444444-4444-4444-a444-444444444444"

    workspace = tmp_path / "workspace_empty"
    workspace.mkdir()

    session = SessionModel(
        session_id=session_id,
        name="Empty Session",
        workspace_path=str(workspace),
        status="active",
    )
    db_session.add(session)
    db_session.commit()

    return session_id


@pytest.fixture()
def user_message_id(session_with_messages) -> str:
    """Return the user message ID from the test session."""
    return "22222222-2222-4222-a222-222222222222"


@pytest.fixture()
def assistant_message_id(session_with_messages) -> str:
    """Return the assistant message ID from the test session."""
    return "33333333-3333-4333-a333-333333333333"


# ---------------------------------------------------------------------------
# Test Export Full Chat History
# ---------------------------------------------------------------------------


class TestExportChatHistory:
    """Tests for POST /{session_id}/chat/export endpoint."""

    def test_export_markdown_success(self, client: TestClient, session_with_messages: str):
        """Test successful markdown export."""
        response = client.post(
            f"/api/v1/sessions/{session_with_messages}/chat/export",
            json={"format": "markdown"},
        )

        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        assert ".md" in response.headers["content-disposition"]

        # Verify content
        content = response.content.decode("utf-8")
        assert "# Chat Export:" in content
        assert "**User**" in content
        assert "**Assistant**" in content
        assert "What is Python?" in content
        assert "Python is a high-level" in content

    def test_export_markdown_without_metadata(
        self, client: TestClient, session_with_messages: str
    ):
        """Test markdown export without metadata header."""
        response = client.post(
            f"/api/v1/sessions/{session_with_messages}/chat/export",
            json={"format": "markdown", "include_metadata": False},
        )

        assert response.status_code == 200
        content = response.content.decode("utf-8")
        assert "# Chat Export:" not in content
        assert "**User**" in content

    def test_export_markdown_without_timestamps(
        self, client: TestClient, session_with_messages: str
    ):
        """Test markdown export without timestamps."""
        response = client.post(
            f"/api/v1/sessions/{session_with_messages}/chat/export",
            json={"format": "markdown", "include_timestamps": False},
        )

        assert response.status_code == 200
        content = response.content.decode("utf-8")
        # Should have role headers without timestamps
        assert "### **User**\n" in content or "### **User**" in content

    @pytest.mark.skipif(not WEASYPRINT_AVAILABLE, reason="weasyprint not installed")
    def test_export_pdf_success(self, client: TestClient, session_with_messages: str):
        """Test successful PDF export."""
        response = client.post(
            f"/api/v1/sessions/{session_with_messages}/chat/export",
            json={"format": "pdf"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment" in response.headers["content-disposition"]
        assert ".pdf" in response.headers["content-disposition"]
        # PDF magic number
        assert response.content[:4] == b"%PDF"

    def test_export_session_not_found(self, client: TestClient):
        """Test export with non-existent session."""
        response = client.post(
            "/api/v1/sessions/99999999-9999-4999-a999-999999999999/chat/export",
            json={"format": "markdown"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"]["code"] == "SESSION_NOT_FOUND"

    def test_export_no_messages(self, client: TestClient, empty_session: str):
        """Test export with no chat messages."""
        response = client.post(
            f"/api/v1/sessions/{empty_session}/chat/export",
            json={"format": "markdown"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"]["code"] == "NO_CHAT_MESSAGES"

    def test_export_invalid_format(self, client: TestClient, session_with_messages: str):
        """Test export with invalid format."""
        response = client.post(
            f"/api/v1/sessions/{session_with_messages}/chat/export",
            json={"format": "invalid"},
        )

        # Pydantic validation error
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test Export Single Q/A Pair
# ---------------------------------------------------------------------------


class TestExportSingleMessage:
    """Tests for POST /{session_id}/chat/{message_id}/export endpoint."""

    def test_export_single_qa_markdown_success(
        self,
        client: TestClient,
        session_with_messages: str,
        assistant_message_id: str,
    ):
        """Test successful single Q/A markdown export."""
        response = client.post(
            f"/api/v1/sessions/{session_with_messages}/chat/{assistant_message_id}/export",
            json={"format": "markdown"},
        )

        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]

        content = response.content.decode("utf-8")
        assert "**User**" in content
        assert "**Assistant**" in content
        assert "What is Python?" in content
        assert "Python is a high-level" in content

    @pytest.mark.skipif(not WEASYPRINT_AVAILABLE, reason="weasyprint not installed")
    def test_export_single_qa_pdf_success(
        self,
        client: TestClient,
        session_with_messages: str,
        assistant_message_id: str,
    ):
        """Test successful single Q/A PDF export."""
        response = client.post(
            f"/api/v1/sessions/{session_with_messages}/chat/{assistant_message_id}/export",
            json={"format": "pdf"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content[:4] == b"%PDF"

    def test_export_non_assistant_message(
        self,
        client: TestClient,
        session_with_messages: str,
        user_message_id: str,
    ):
        """Test export from user message fails."""
        response = client.post(
            f"/api/v1/sessions/{session_with_messages}/chat/{user_message_id}/export",
            json={"format": "markdown"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"]["code"] == "NOT_ASSISTANT_MESSAGE"

    def test_export_message_not_found(
        self, client: TestClient, session_with_messages: str
    ):
        """Test export with non-existent message."""
        response = client.post(
            f"/api/v1/sessions/{session_with_messages}/chat/88888888-8888-4888-a888-888888888888/export",
            json={"format": "markdown"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"]["code"] == "CHAT_MESSAGE_NOT_FOUND"

    def test_export_session_not_found_single(self, client: TestClient):
        """Test single export with non-existent session."""
        response = client.post(
            "/api/v1/sessions/99999999-9999-4999-a999-999999999999/chat/88888888-8888-4888-a888-888888888888/export",
            json={"format": "markdown"},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"]["code"] == "SESSION_NOT_FOUND"


# ---------------------------------------------------------------------------
# Test Export Service Unit Tests
# ---------------------------------------------------------------------------


class TestMarkdownExporter:
    """Unit tests for MarkdownExporter."""

    def test_content_type(self):
        """Test correct MIME type."""
        from app.services.export.markdown import MarkdownExporter

        exporter = MarkdownExporter()
        assert exporter.content_type == "text/markdown"

    def test_file_extension(self):
        """Test correct file extension."""
        from app.services.export.markdown import MarkdownExporter

        exporter = MarkdownExporter()
        assert exporter.file_extension == "md"

    def test_generate_filename(self):
        """Test filename generation."""
        from app.services.export.markdown import MarkdownExporter

        exporter = MarkdownExporter()
        filename = exporter.generate_filename("test-session-12345678")
        assert filename.startswith("chat-export-test-ses")
        assert filename.endswith(".md")


class TestPDFExporter:
    """Unit tests for PDFExporter."""

    def test_content_type(self):
        """Test correct MIME type."""
        from app.services.export.pdf import PDFExporter

        exporter = PDFExporter()
        assert exporter.content_type == "application/pdf"

    def test_file_extension(self):
        """Test correct file extension."""
        from app.services.export.pdf import PDFExporter

        exporter = PDFExporter()
        assert exporter.file_extension == "pdf"

    def test_generate_filename(self):
        """Test filename generation."""
        from app.services.export.pdf import PDFExporter

        exporter = PDFExporter()
        filename = exporter.generate_filename("test-session-12345678")
        assert filename.startswith("chat-export-test-ses")
        assert filename.endswith(".pdf")


class TestExportFactory:
    """Unit tests for export factory function."""

    def test_get_markdown_exporter(self):
        """Test getting markdown exporter."""
        from app.schemas.chat import ChatExportFormat
        from app.services.export import get_exporter
        from app.services.export.markdown import MarkdownExporter

        exporter = get_exporter(ChatExportFormat.MARKDOWN)
        assert isinstance(exporter, MarkdownExporter)

    def test_get_pdf_exporter(self):
        """Test getting PDF exporter."""
        from app.schemas.chat import ChatExportFormat
        from app.services.export import get_exporter
        from app.services.export.pdf import PDFExporter

        exporter = get_exporter(ChatExportFormat.PDF)
        assert isinstance(exporter, PDFExporter)
