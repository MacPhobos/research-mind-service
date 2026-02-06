"""Tests for audit logging (Phase 1.5)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  -- ensure models registered with Base.metadata
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.session import Session as SessionModel
from app.services.audit_service import AuditService


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


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


def _seed_session(db: Session, session_id: str = "test-session-1") -> SessionModel:
    """Insert a minimal session row for FK-free audit testing."""
    sess = SessionModel(
        session_id=session_id,
        name="Test Session",
        workspace_path=f"/tmp/ws-{session_id}",
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


# ------------------------------------------------------------------
# Model creation
# ------------------------------------------------------------------


class TestAuditLogModel:
    def test_audit_log_model_creation(self, db_session: Session):
        entry = AuditLog(
            session_id="sess-1",
            action="session_create",
            status="success",
            metadata_json={"name": "My Session"},
        )
        db_session.add(entry)
        db_session.commit()
        db_session.refresh(entry)

        assert entry.id is not None
        assert entry.session_id == "sess-1"
        assert entry.action == "session_create"
        assert entry.status == "success"
        assert entry.timestamp is not None
        assert entry.metadata_json == {"name": "My Session"}


# ------------------------------------------------------------------
# AuditService logging methods
# ------------------------------------------------------------------


class TestAuditServiceLogging:
    def test_log_session_create(self, db_session: Session):
        AuditService.log_session_create(db_session, "s1", "My Session")

        logs = db_session.query(AuditLog).filter_by(session_id="s1").all()
        assert len(logs) == 1
        assert logs[0].action == "session_create"
        assert logs[0].status == "success"
        assert logs[0].metadata_json["name"] == "My Session"

    def test_log_session_delete(self, db_session: Session):
        AuditService.log_session_delete(db_session, "s2")

        logs = db_session.query(AuditLog).filter_by(session_id="s2").all()
        assert len(logs) == 1
        assert logs[0].action == "session_delete"

    def test_log_index_start(self, db_session: Session):
        AuditService.log_index_start(db_session, "s3", "/tmp/workspace")

        logs = db_session.query(AuditLog).filter_by(session_id="s3").all()
        assert len(logs) == 1
        assert logs[0].action == "index_start"
        assert logs[0].metadata_json["workspace_path"] == "/tmp/workspace"

    def test_log_index_complete(self, db_session: Session):
        AuditService.log_index_complete(db_session, "s4", 1500, stdout_summary="OK")

        logs = db_session.query(AuditLog).filter_by(session_id="s4").all()
        assert len(logs) == 1
        assert logs[0].action == "index_complete"
        assert logs[0].duration_ms == 1500
        assert logs[0].metadata_json["stdout_summary"] == "OK"

    def test_log_subprocess_spawn(self, db_session: Session):
        AuditService.log_subprocess_spawn(
            db_session, "s5", "mcp-vector-search init", "/tmp/ws"
        )

        logs = db_session.query(AuditLog).filter_by(session_id="s5").all()
        assert len(logs) == 1
        assert logs[0].action == "subprocess_spawn"
        assert logs[0].metadata_json["command"] == "mcp-vector-search init"

    def test_log_subprocess_complete(self, db_session: Session):
        AuditService.log_subprocess_complete(
            db_session,
            "s6",
            "mcp-vector-search index",
            0,
            3200,
            stdout_summary="indexed 42 files",
        )

        logs = db_session.query(AuditLog).filter_by(session_id="s6").all()
        assert len(logs) == 1
        assert logs[0].action == "subprocess_complete"
        assert logs[0].duration_ms == 3200
        assert logs[0].metadata_json["exit_code"] == 0

    def test_log_subprocess_error(self, db_session: Session):
        AuditService.log_subprocess_error(
            db_session, "s7", "mcp-vector-search index", 1, 500, stderr_summary="crash"
        )

        logs = db_session.query(AuditLog).filter_by(session_id="s7").all()
        assert len(logs) == 1
        assert logs[0].action == "subprocess_error"
        assert logs[0].status == "failed"
        assert logs[0].error == "crash"
        assert logs[0].metadata_json["exit_code"] == 1

    def test_log_subprocess_timeout(self, db_session: Session):
        AuditService.log_subprocess_timeout(
            db_session, "s8", "mcp-vector-search index", 120, "/tmp/ws"
        )

        logs = db_session.query(AuditLog).filter_by(session_id="s8").all()
        assert len(logs) == 1
        assert logs[0].action == "subprocess_timeout"
        assert logs[0].status == "failed"
        assert "120" in logs[0].error

    def test_log_failed_request(self, db_session: Session):
        AuditService.log_failed_request(db_session, "s9", "search", "index not found")

        logs = db_session.query(AuditLog).filter_by(session_id="s9").all()
        assert len(logs) == 1
        assert logs[0].action == "failed_request"
        assert logs[0].status == "failed"
        assert logs[0].error == "index not found"
        assert logs[0].metadata_json["original_action"] == "search"


# ------------------------------------------------------------------
# AuditService query methods
# ------------------------------------------------------------------


class TestAuditServiceQuery:
    def test_get_audit_logs(self, db_session: Session):
        # Create several entries
        for i in range(5):
            AuditService.log_session_create(db_session, "q1", f"Session {i}")

        logs, count = AuditService.get_audit_logs(db_session, "q1")
        assert count == 5
        assert len(logs) == 5

    def test_get_audit_logs_pagination(self, db_session: Session):
        for i in range(10):
            AuditService.log_session_create(db_session, "q2", f"Session {i}")

        logs, count = AuditService.get_audit_logs(db_session, "q2", limit=3, offset=0)
        assert count == 10
        assert len(logs) == 3

        logs2, count2 = AuditService.get_audit_logs(db_session, "q2", limit=3, offset=9)
        assert count2 == 10
        assert len(logs2) == 1


# ------------------------------------------------------------------
# Endpoint tests
# ------------------------------------------------------------------


class TestAuditEndpoint:
    def test_audit_endpoint(self, client: TestClient):
        # Create a session first
        create_resp = client.post("/api/v1/sessions/", json={"name": "Audit Test"})
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session_id"]

        # Fetch audit logs (may have session_create entry from service layer
        # or may be empty depending on integration -- at minimum should return 200)
        response = client.get(f"/api/v1/sessions/{session_id}/audit")
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data
        assert "count" in data
        assert isinstance(data["logs"], list)
        assert isinstance(data["count"], int)

    def test_audit_endpoint_session_not_found(self, client: TestClient):
        response = client.get(
            "/api/v1/sessions/00000000-0000-4000-a000-000000000000/audit"
        )
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"]["code"] == "SESSION_NOT_FOUND"
