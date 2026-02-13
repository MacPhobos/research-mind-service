"""Tests for session management endpoints (Phase 1.2)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  -- ensure models registered with Base.metadata
from app.db.base import Base
from app.db.session import get_db
from app.main import app


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


# ------------------------------------------------------------------
# POST /api/v1/sessions
# ------------------------------------------------------------------


class TestCreateSession:
    def test_create_session(self, client: TestClient, tmp_content_sandbox: str):
        response = client.post(
            "/api/v1/sessions/",
            json={"name": "My Session", "description": "Test description"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Session"
        assert data["description"] == "Test description"
        assert data["status"] == "active"
        assert data["archived"] is False
        assert "session_id" in data
        assert "workspace_path" in data
        assert "created_at" in data
        assert "last_accessed" in data
        # Workspace directory should have been created
        assert os.path.isdir(data["workspace_path"])

    def test_create_session_creates_claude_md(
        self, client: TestClient, tmp_content_sandbox: str
    ):
        """Verify that CLAUDE.md is created in the sandbox directory with correct content."""
        response = client.post(
            "/api/v1/sessions/",
            json={"name": "Claude MD Session"},
        )
        assert response.status_code == 201
        data = response.json()
        workspace_path = data["workspace_path"]

        # CLAUDE.md should exist in the workspace directory
        claude_md_path = os.path.join(workspace_path, "CLAUDE.md")
        assert os.path.isfile(claude_md_path), "CLAUDE.md should exist in sandbox"

        # Verify the content matches the expected template
        from app.services.session_service import SANDBOX_CLAUDE_MD_TEMPLATE

        with open(claude_md_path, "r") as f:
            content = f.read()

        assert (
            content == SANDBOX_CLAUDE_MD_TEMPLATE
        ), "CLAUDE.md content should match template"

    def test_create_session_minimal(self, client: TestClient):
        response = client.post(
            "/api/v1/sessions/",
            json={"name": "Minimal"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal"
        assert data["description"] is None

    def test_create_session_no_name(self, client: TestClient):
        response = client.post("/api/v1/sessions/", json={})
        assert response.status_code == 422

    def test_create_session_empty_name(self, client: TestClient):
        response = client.post("/api/v1/sessions/", json={"name": ""})
        assert response.status_code == 422

    def test_create_session_name_too_long(self, client: TestClient):
        response = client.post("/api/v1/sessions/", json={"name": "x" * 256})
        assert response.status_code == 422


# ------------------------------------------------------------------
# GET /api/v1/sessions/{session_id}
# ------------------------------------------------------------------


class TestGetSession:
    def test_get_session(self, client: TestClient):
        # Create first
        create_resp = client.post("/api/v1/sessions/", json={"name": "Fetched Session"})
        session_id = create_resp.json()["session_id"]

        # Fetch
        response = client.get(f"/api/v1/sessions/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["name"] == "Fetched Session"

    def test_get_session_not_found(self, client: TestClient):
        response = client.get("/api/v1/sessions/00000000-0000-4000-a000-000000000000")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"]["code"] == "SESSION_NOT_FOUND"


# ------------------------------------------------------------------
# GET /api/v1/sessions
# ------------------------------------------------------------------


class TestListSessions:
    def test_list_sessions_empty(self, client: TestClient):
        response = client.get("/api/v1/sessions/")
        assert response.status_code == 200
        data = response.json()
        assert data["sessions"] == []
        assert data["count"] == 0

    def test_list_sessions(self, client: TestClient):
        client.post("/api/v1/sessions/", json={"name": "S1"})
        client.post("/api/v1/sessions/", json={"name": "S2"})
        client.post("/api/v1/sessions/", json={"name": "S3"})

        response = client.get("/api/v1/sessions/")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3
        assert len(data["sessions"]) == 3

    def test_list_sessions_pagination(self, client: TestClient):
        for i in range(5):
            client.post("/api/v1/sessions/", json={"name": f"S{i}"})

        response = client.get("/api/v1/sessions/?limit=2&offset=0")
        data = response.json()
        assert len(data["sessions"]) == 2
        assert data["count"] == 5

        response2 = client.get("/api/v1/sessions/?limit=2&offset=4")
        data2 = response2.json()
        assert len(data2["sessions"]) == 1
        assert data2["count"] == 5


# ------------------------------------------------------------------
# DELETE /api/v1/sessions/{session_id}
# ------------------------------------------------------------------


class TestDeleteSession:
    def test_delete_session(self, client: TestClient):
        create_resp = client.post("/api/v1/sessions/", json={"name": "To Delete"})
        session_id = create_resp.json()["session_id"]
        workspace = create_resp.json()["workspace_path"]

        # Workspace dir should exist
        assert os.path.isdir(workspace)

        # Delete
        response = client.delete(f"/api/v1/sessions/{session_id}")
        assert response.status_code == 204

        # Workspace dir should be removed
        assert not os.path.isdir(workspace)

        # GET should 404
        get_resp = client.get(f"/api/v1/sessions/{session_id}")
        assert get_resp.status_code == 404

    def test_delete_session_not_found(self, client: TestClient):
        response = client.delete(
            "/api/v1/sessions/00000000-0000-4000-a000-000000000000"
        )
        assert response.status_code == 404


# ------------------------------------------------------------------
# Session isolation
# ------------------------------------------------------------------


class TestSessionIsolation:
    def test_multiple_sessions_coexist(self, client: TestClient):
        ids = []
        for i in range(3):
            resp = client.post("/api/v1/sessions/", json={"name": f"Isolated {i}"})
            ids.append(resp.json()["session_id"])

        # All three should be independently accessible
        for sid in ids:
            resp = client.get(f"/api/v1/sessions/{sid}")
            assert resp.status_code == 200

        # Delete one should not affect others
        client.delete(f"/api/v1/sessions/{ids[1]}")

        assert client.get(f"/api/v1/sessions/{ids[0]}").status_code == 200
        assert client.get(f"/api/v1/sessions/{ids[1]}").status_code == 404
        assert client.get(f"/api/v1/sessions/{ids[2]}").status_code == 200


# ------------------------------------------------------------------
# is_indexed reflects filesystem
# ------------------------------------------------------------------


class TestIsIndexed:
    def test_is_indexed_false_by_default(self, client: TestClient):
        resp = client.post("/api/v1/sessions/", json={"name": "Not Indexed"})
        assert resp.status_code == 201
        assert resp.json()["is_indexed"] is False

    def test_is_indexed_true_when_dir_exists(self, client: TestClient):
        resp = client.post("/api/v1/sessions/", json={"name": "Indexed"})
        data = resp.json()
        workspace = data["workspace_path"]
        session_id = data["session_id"]

        # Simulate indexing by creating the directory
        os.makedirs(os.path.join(workspace, ".mcp-vector-search"))

        # Re-fetch the session
        get_resp = client.get(f"/api/v1/sessions/{session_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["is_indexed"] is True


# ------------------------------------------------------------------
# Fixtures for sandbox skill deployment tests
# ------------------------------------------------------------------


@pytest.fixture()
def fake_monorepo_root(tmp_path: Path) -> Path:
    """Create a fake monorepo root with skill directories.

    Mirrors the structure of the real monorepo .claude/skills/ directory
    with the three skills referenced by MINIMAL_QA_SKILLS.
    """
    skills_root = tmp_path / "fake_monorepo" / ".claude" / "skills"

    # universal-data-json-data-handling: has skill.md, metadata.json, .etag_cache.json
    json_skill = skills_root / "universal-data-json-data-handling"
    json_skill.mkdir(parents=True)
    (json_skill / "skill.md").write_text("# JSON Data Handling\nTest content.")
    (json_skill / "metadata.json").write_text('{"name": "json-data-handling"}')
    (json_skill / ".etag_cache.json").write_text('{"etag": "abc123"}')

    # toolchains-ai-protocols-mcp: has skill.md only
    mcp_skill = skills_root / "toolchains-ai-protocols-mcp"
    mcp_skill.mkdir(parents=True)
    (mcp_skill / "skill.md").write_text("# MCP Protocol\nTest content.")

    # universal-collaboration-writing-plans: has skill.md, metadata.json,
    # .etag_cache.json, and a references/ subdirectory
    plans_skill = skills_root / "universal-collaboration-writing-plans"
    plans_skill.mkdir(parents=True)
    (plans_skill / "skill.md").write_text("# Writing Plans\nTest content.")
    (plans_skill / "metadata.json").write_text('{"name": "writing-plans"}')
    (plans_skill / ".etag_cache.json").write_text('{"etag": "def456"}')
    refs = plans_skill / "references"
    refs.mkdir()
    (refs / "example.md").write_text("# Example Reference")
    (refs / ".etag_cache.json").write_text('{"etag": "nested789"}')

    # universal-debugging-systematic-debugging: has skill.md only
    debug_skill = skills_root / "universal-debugging-systematic-debugging"
    debug_skill.mkdir(parents=True)
    (debug_skill / "skill.md").write_text("# Systematic Debugging\nTest content.")

    # toolchains-ai-techniques-session-compression: has skill.md only
    compression_skill = skills_root / "toolchains-ai-techniques-session-compression"
    compression_skill.mkdir(parents=True)
    (compression_skill / "skill.md").write_text("# Session Compression\nTest content.")

    return tmp_path / "fake_monorepo"


# ------------------------------------------------------------------
# claude-mpm configuration.yaml content tests
# ------------------------------------------------------------------


class TestClaudeMpmConfig:
    def test_config_lists_five_skills(self, tmp_path: Path):
        """Verify configuration.yaml has the 5 skill names in agent_referenced."""
        from app.services.session_service import create_sandbox_claude_mpm_config

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        create_sandbox_claude_mpm_config(sandbox)

        config_path = sandbox / ".claude-mpm" / "configuration.yaml"
        assert config_path.is_file()

        content = config_path.read_text()
        assert "agent_referenced:" in content
        assert "- json-data-handling" in content
        assert "- mcp" in content
        assert "- writing-plans" in content
        assert "- systematic-debugging" in content
        assert "- session-compression" in content

        # Verify exactly 5 skills listed
        lines = content.split("\n")
        skill_count = sum(1 for line in lines if line.strip().startswith("- "))
        assert skill_count == 5

    def test_config_disables_auto_deploy(self, tmp_path: Path):
        """Verify auto_deploy is false and agent_sync is disabled."""
        from app.services.session_service import create_sandbox_claude_mpm_config

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        create_sandbox_claude_mpm_config(sandbox)

        content = (sandbox / ".claude-mpm" / "configuration.yaml").read_text()
        assert "auto_deploy: false" in content
        assert "enabled: false" in content


# ------------------------------------------------------------------
# deploy_minimal_sandbox_skills unit tests
# ------------------------------------------------------------------


class TestDeployMinimalSandboxSkills:
    def test_copies_all_five_skill_dirs(self, tmp_path: Path, fake_monorepo_root: Path):
        """All five skill directories should be copied into the sandbox."""
        from app.services.session_service import deploy_minimal_sandbox_skills

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()

        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            deploy_minimal_sandbox_skills(sandbox)

        skills_dir = sandbox / ".claude" / "skills"
        assert (skills_dir / "universal-data-json-data-handling").is_dir()
        assert (skills_dir / "toolchains-ai-protocols-mcp").is_dir()
        assert (skills_dir / "universal-collaboration-writing-plans").is_dir()
        assert (skills_dir / "universal-debugging-systematic-debugging").is_dir()
        assert (skills_dir / "toolchains-ai-techniques-session-compression").is_dir()

        # Verify exactly 5 skill directories
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        assert len(skill_dirs) == 5

    def test_skill_files_are_copied(self, tmp_path: Path, fake_monorepo_root: Path):
        """Verify actual skill files (skill.md, metadata.json) are present."""
        from app.services.session_service import deploy_minimal_sandbox_skills

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()

        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            deploy_minimal_sandbox_skills(sandbox)

        skills_dir = sandbox / ".claude" / "skills"

        # JSON skill has skill.md and metadata.json
        assert (skills_dir / "universal-data-json-data-handling" / "skill.md").is_file()
        assert (
            skills_dir / "universal-data-json-data-handling" / "metadata.json"
        ).is_file()

        # MCP skill has skill.md only
        assert (skills_dir / "toolchains-ai-protocols-mcp" / "skill.md").is_file()

        # Writing plans skill has skill.md, metadata.json, and references/
        plans_dir = skills_dir / "universal-collaboration-writing-plans"
        assert (plans_dir / "skill.md").is_file()
        assert (plans_dir / "metadata.json").is_file()
        assert (plans_dir / "references" / "example.md").is_file()

    def test_etag_cache_json_excluded(self, tmp_path: Path, fake_monorepo_root: Path):
        """Files named .etag_cache.json should NOT be copied."""
        from app.services.session_service import deploy_minimal_sandbox_skills

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()

        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            deploy_minimal_sandbox_skills(sandbox)

        skills_dir = sandbox / ".claude" / "skills"

        # .etag_cache.json should be excluded at top level of each skill
        assert not (
            skills_dir / "universal-data-json-data-handling" / ".etag_cache.json"
        ).exists()
        assert not (
            skills_dir / "universal-collaboration-writing-plans" / ".etag_cache.json"
        ).exists()

        # .etag_cache.json should also be excluded in subdirectories
        assert not (
            skills_dir
            / "universal-collaboration-writing-plans"
            / "references"
            / ".etag_cache.json"
        ).exists()

    def test_missing_skill_skipped_gracefully(self, tmp_path: Path):
        """If a skill directory is missing, it should be skipped with a warning."""
        from app.services.session_service import deploy_minimal_sandbox_skills

        # Use an empty fake monorepo root (no skill dirs at all)
        empty_root = tmp_path / "empty_monorepo"
        empty_root.mkdir()

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()

        with patch("app.services.session_service._MONOREPO_ROOT", empty_root):
            # Should not raise -- missing skills are logged and skipped
            deploy_minimal_sandbox_skills(sandbox)

        # The .claude/skills/ dir is created but should be empty
        skills_dir = sandbox / ".claude" / "skills"
        assert skills_dir.is_dir()
        assert list(skills_dir.iterdir()) == []

    def test_partial_skills_available(self, tmp_path: Path, fake_monorepo_root: Path):
        """If only some skills exist, available ones are copied and missing ones skipped."""
        from app.services.session_service import deploy_minimal_sandbox_skills

        # Remove one skill directory from the fake monorepo
        import shutil

        shutil.rmtree(
            fake_monorepo_root / ".claude" / "skills" / "toolchains-ai-protocols-mcp"
        )

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()

        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            deploy_minimal_sandbox_skills(sandbox)

        skills_dir = sandbox / ".claude" / "skills"
        # Four skills should exist, one should be missing
        assert (skills_dir / "universal-data-json-data-handling").is_dir()
        assert not (skills_dir / "toolchains-ai-protocols-mcp").exists()
        assert (skills_dir / "universal-collaboration-writing-plans").is_dir()
        assert (skills_dir / "universal-debugging-systematic-debugging").is_dir()
        assert (skills_dir / "toolchains-ai-techniques-session-compression").is_dir()


# ------------------------------------------------------------------
# Integration: create_session deploys skills
# ------------------------------------------------------------------


class TestCreateSessionDeploysSkills:
    def test_create_session_deploys_skills(
        self, client: TestClient, fake_monorepo_root: Path
    ):
        """Creating a session should deploy skill directories into the workspace."""
        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            response = client.post(
                "/api/v1/sessions/",
                json={"name": "Skill Deploy Session"},
            )
        assert response.status_code == 201
        data = response.json()
        workspace = Path(data["workspace_path"])

        skills_dir = workspace / ".claude" / "skills"
        assert skills_dir.is_dir()
        assert (skills_dir / "universal-data-json-data-handling").is_dir()
        assert (skills_dir / "toolchains-ai-protocols-mcp").is_dir()
        assert (skills_dir / "universal-collaboration-writing-plans").is_dir()
        assert (skills_dir / "universal-debugging-systematic-debugging").is_dir()
        assert (skills_dir / "toolchains-ai-techniques-session-compression").is_dir()

    def test_create_session_excludes_etag_cache(
        self, client: TestClient, fake_monorepo_root: Path
    ):
        """Creating a session should not copy .etag_cache.json files."""
        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            response = client.post(
                "/api/v1/sessions/",
                json={"name": "No Etag Session"},
            )
        assert response.status_code == 201
        workspace = Path(response.json()["workspace_path"])

        skills_dir = workspace / ".claude" / "skills"
        # Walk all files and ensure no .etag_cache.json exists
        etag_files = list(skills_dir.rglob(".etag_cache.json"))
        assert (
            etag_files == []
        ), f"Found unexpected .etag_cache.json files: {etag_files}"


# ------------------------------------------------------------------
# migrate_sandbox_config unit tests (Plan 02)
# ------------------------------------------------------------------


class TestMigrateSandboxConfig:
    def test_already_minimal_returns_false(
        self, tmp_path: Path, fake_monorepo_root: Path
    ):
        """A sandbox with 5 correct skills and no agents returns False."""
        from app.services.session_service import (
            create_sandbox_claude_md,
            create_sandbox_claude_mpm_config,
            deploy_minimal_sandbox_skills,
            migrate_sandbox_config,
        )

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        create_sandbox_claude_md(sandbox)
        create_sandbox_claude_mpm_config(sandbox)

        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            deploy_minimal_sandbox_skills(sandbox)

        # Sandbox is already minimal
        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            result = migrate_sandbox_config(sandbox)

        assert result is False

    def test_legacy_sandbox_migrated(self, tmp_path: Path, fake_monorepo_root: Path):
        """A legacy sandbox with agents + 60 skills should be migrated."""
        from app.services.session_service import (
            create_sandbox_claude_md,
            migrate_sandbox_config,
        )

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        create_sandbox_claude_md(sandbox)

        # Create legacy agents directory with fake agent files
        agents_dir = sandbox / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "research.md").write_text("# Research Agent\n" * 100)
        (agents_dir / "engineer.md").write_text("# Engineer Agent\n" * 50)
        (agents_dir / "qa.md").write_text("# QA Agent\n" * 50)

        # Create legacy skills directory with many fake skills
        skills_dir = sandbox / ".claude" / "skills"
        skills_dir.mkdir(parents=True)
        for i in range(60):
            skill_dir = skills_dir / f"legacy-skill-{i}"
            skill_dir.mkdir()
            (skill_dir / "skill.md").write_text(f"# Legacy Skill {i}")

        # Create legacy configuration.yaml with 52 skills
        config_dir = sandbox / ".claude-mpm"
        config_dir.mkdir(parents=True)
        skill_lines = "\n".join(f"    - legacy-skill-{i}" for i in range(52))
        (config_dir / "configuration.yaml").write_text(
            "agent_sync:\n"
            "  enabled: false\n"
            "\n"
            "skills:\n"
            "  auto_deploy: false\n"
            "  agent_referenced:\n"
            f"{skill_lines}\n"
            "  user_defined: []\n"
        )

        # Migrate
        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            result = migrate_sandbox_config(sandbox)

        assert result is True

        # Agents should be removed
        assert not agents_dir.exists()

        # Skills should be replaced with 5 minimal skills
        assert skills_dir.is_dir()
        skill_dirs = sorted(d.name for d in skills_dir.iterdir() if d.is_dir())
        assert len(skill_dirs) == 5
        assert "universal-data-json-data-handling" in skill_dirs
        assert "toolchains-ai-protocols-mcp" in skill_dirs
        assert "universal-collaboration-writing-plans" in skill_dirs
        assert "universal-debugging-systematic-debugging" in skill_dirs
        assert "toolchains-ai-techniques-session-compression" in skill_dirs

        # Configuration should be updated
        config_content = (config_dir / "configuration.yaml").read_text()
        lines = config_content.split("\n")
        config_skill_count = sum(1 for line in lines if line.strip().startswith("- "))
        assert config_skill_count == 5

    def test_partial_state_agents_only(self, tmp_path: Path, fake_monorepo_root: Path):
        """Sandbox with agents but correct skills should only remove agents."""
        from app.services.session_service import (
            create_sandbox_claude_mpm_config,
            deploy_minimal_sandbox_skills,
            migrate_sandbox_config,
        )

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        create_sandbox_claude_mpm_config(sandbox)

        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            deploy_minimal_sandbox_skills(sandbox)

        # Add agents directory (simulating claude-mpm sync)
        agents_dir = sandbox / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "research.md").write_text("# Research Agent")

        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            result = migrate_sandbox_config(sandbox)

        assert result is True
        assert not agents_dir.exists()
        # Skills should still be 5
        skills_dir = sandbox / ".claude" / "skills"
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        assert len(skill_dirs) == 5

    def test_data_preservation(self, tmp_path: Path, fake_monorepo_root: Path):
        """Migration must preserve CLAUDE.md, .mcp.json, and content data."""
        from app.services.session_service import migrate_sandbox_config

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()

        # Create files that must be preserved
        (sandbox / "CLAUDE.md").write_text("# Research Assistant\nCustom content.")
        (sandbox / ".mcp.json").write_text('{"tools": ["vector-search"]}')
        content_dir = sandbox / "content"
        content_dir.mkdir()
        (content_dir / "doc.md").write_text("# Important Document")
        vector_dir = sandbox / ".mcp-vector-search"
        vector_dir.mkdir()
        (vector_dir / "index.bin").write_bytes(b"\x00\x01\x02\x03")
        settings_path = sandbox / ".claude" / "settings.local.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text('{"key": "value"}')

        # Create legacy agents + wrong skill count
        agents_dir = sandbox / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "research.md").write_text("# Agent")
        skills_dir = sandbox / ".claude" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        for i in range(10):
            d = skills_dir / f"old-skill-{i}"
            d.mkdir()
            (d / "skill.md").write_text(f"# Skill {i}")

        # Create legacy config
        config_dir = sandbox / ".claude-mpm"
        config_dir.mkdir(parents=True)
        (config_dir / "configuration.yaml").write_text(
            "agent_sync:\n  enabled: false\nskills:\n  auto_deploy: false\n"
            "  agent_referenced:\n"
            + "\n".join(f"    - old-skill-{i}" for i in range(10))
            + "\n  user_defined: []\n"
        )
        (config_dir / "config.json").write_text('{"project": "test"}')

        # Migrate
        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            result = migrate_sandbox_config(sandbox)

        assert result is True

        # Verify preserved files
        assert (
            sandbox / "CLAUDE.md"
        ).read_text() == "# Research Assistant\nCustom content."
        assert (sandbox / ".mcp.json").read_text() == '{"tools": ["vector-search"]}'
        assert (content_dir / "doc.md").read_text() == "# Important Document"
        assert (vector_dir / "index.bin").read_bytes() == b"\x00\x01\x02\x03"
        assert settings_path.read_text() == '{"key": "value"}'
        assert (config_dir / "config.json").read_text() == '{"project": "test"}'


# ------------------------------------------------------------------
# create_sandbox_pm_instructions unit tests (Plan 04)
# ------------------------------------------------------------------


class TestCreateSandboxPmInstructions:
    def test_creates_deployed_file(self, tmp_path: Path):
        """Verify PM_INSTRUCTIONS_DEPLOYED.md is created in .claude-mpm/."""
        from app.services.session_service import create_sandbox_pm_instructions

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        create_sandbox_pm_instructions(sandbox)

        deployed_path = sandbox / ".claude-mpm" / "PM_INSTRUCTIONS_DEPLOYED.md"
        assert deployed_path.is_file()

    def test_content_is_minimal(self, tmp_path: Path):
        """Verify the file content is much smaller than the ~56KB default."""
        from app.services.session_service import create_sandbox_pm_instructions

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        create_sandbox_pm_instructions(sandbox)

        deployed_path = sandbox / ".claude-mpm" / "PM_INSTRUCTIONS_DEPLOYED.md"
        content = deployed_path.read_text()

        # Minimal file should be well under 2000 bytes (vs ~56KB default)
        assert len(content) < 2000
        assert "Q&A Research Assistant" in content
        assert "mcp-vector-search" in content

    def test_version_comment_present(self, tmp_path: Path):
        """Verify the version comment is present and high enough to override source."""
        from app.services.session_service import create_sandbox_pm_instructions

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        create_sandbox_pm_instructions(sandbox)

        deployed_path = sandbox / ".claude-mpm" / "PM_INSTRUCTIONS_DEPLOYED.md"
        content = deployed_path.read_text()

        assert "PM_INSTRUCTIONS_VERSION: 9999" in content

    def test_creates_directory_if_missing(self, tmp_path: Path):
        """Verify .claude-mpm directory is created if it doesn't exist."""
        from app.services.session_service import create_sandbox_pm_instructions

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        # No .claude-mpm directory exists yet
        assert not (sandbox / ".claude-mpm").exists()

        create_sandbox_pm_instructions(sandbox)

        assert (sandbox / ".claude-mpm").is_dir()
        assert (sandbox / ".claude-mpm" / "PM_INSTRUCTIONS_DEPLOYED.md").is_file()

    def test_idempotent(self, tmp_path: Path):
        """Calling twice should produce the same result."""
        from app.services.session_service import create_sandbox_pm_instructions

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        create_sandbox_pm_instructions(sandbox)
        content1 = (sandbox / ".claude-mpm" / "PM_INSTRUCTIONS_DEPLOYED.md").read_text()

        create_sandbox_pm_instructions(sandbox)
        content2 = (sandbox / ".claude-mpm" / "PM_INSTRUCTIONS_DEPLOYED.md").read_text()

        assert content1 == content2


# ------------------------------------------------------------------
# Integration: create_session deploys minimal PM_INSTRUCTIONS (Plan 04)
# ------------------------------------------------------------------


class TestCreateSessionDeploysPmInstructions:
    def test_create_session_creates_minimal_pm_instructions(
        self, client: TestClient, fake_monorepo_root: Path
    ):
        """Creating a session should write minimal PM_INSTRUCTIONS_DEPLOYED.md."""
        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            response = client.post(
                "/api/v1/sessions/",
                json={"name": "PM Instructions Session"},
            )
        assert response.status_code == 201
        workspace = Path(response.json()["workspace_path"])

        deployed_path = workspace / ".claude-mpm" / "PM_INSTRUCTIONS_DEPLOYED.md"
        assert deployed_path.is_file()

        content = deployed_path.read_text()
        assert len(content) < 2000
        assert "Q&A Research Assistant" in content
        assert "PM_INSTRUCTIONS_VERSION: 9999" in content


# ------------------------------------------------------------------
# migrate_sandbox_config replaces large PM_INSTRUCTIONS (Plan 04)
# ------------------------------------------------------------------


class TestMigratePmInstructions:
    def test_large_deployed_file_replaced(
        self, tmp_path: Path, fake_monorepo_root: Path
    ):
        """Migration should replace a large PM_INSTRUCTIONS_DEPLOYED.md."""
        from app.services.session_service import (
            create_sandbox_claude_md,
            create_sandbox_claude_mpm_config,
            deploy_minimal_sandbox_skills,
            migrate_sandbox_config,
        )

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        create_sandbox_claude_md(sandbox)
        create_sandbox_claude_mpm_config(sandbox)

        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            deploy_minimal_sandbox_skills(sandbox)

        # Simulate a large PM_INSTRUCTIONS_DEPLOYED.md (like the ~56KB default)
        deployed_path = sandbox / ".claude-mpm" / "PM_INSTRUCTIONS_DEPLOYED.md"
        deployed_path.write_text("# Full PM Instructions\n" * 500)
        assert deployed_path.stat().st_size > 2000

        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            result = migrate_sandbox_config(sandbox)

        assert result is True
        content = deployed_path.read_text()
        assert len(content) < 2000
        assert "Q&A Research Assistant" in content

    def test_small_deployed_file_not_replaced(
        self, tmp_path: Path, fake_monorepo_root: Path
    ):
        """Migration should NOT replace an already-minimal PM_INSTRUCTIONS_DEPLOYED.md."""
        from app.services.session_service import (
            create_sandbox_claude_md,
            create_sandbox_claude_mpm_config,
            create_sandbox_pm_instructions,
            deploy_minimal_sandbox_skills,
            migrate_sandbox_config,
        )

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        create_sandbox_claude_md(sandbox)
        create_sandbox_claude_mpm_config(sandbox)
        create_sandbox_pm_instructions(sandbox)

        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            deploy_minimal_sandbox_skills(sandbox)

        # Sandbox is already fully minimal (including PM_INSTRUCTIONS)
        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            result = migrate_sandbox_config(sandbox)

        assert result is False

    def test_missing_deployed_file_not_error(
        self, tmp_path: Path, fake_monorepo_root: Path
    ):
        """Migration should not fail if PM_INSTRUCTIONS_DEPLOYED.md doesn't exist."""
        from app.services.session_service import (
            create_sandbox_claude_md,
            create_sandbox_claude_mpm_config,
            deploy_minimal_sandbox_skills,
            migrate_sandbox_config,
        )

        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        create_sandbox_claude_md(sandbox)
        create_sandbox_claude_mpm_config(sandbox)

        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            deploy_minimal_sandbox_skills(sandbox)

        # No PM_INSTRUCTIONS_DEPLOYED.md exists
        deployed_path = sandbox / ".claude-mpm" / "PM_INSTRUCTIONS_DEPLOYED.md"
        assert not deployed_path.exists()

        with patch("app.services.session_service._MONOREPO_ROOT", fake_monorepo_root):
            result = migrate_sandbox_config(sandbox)

        # Should be False because everything else is already minimal
        assert result is False
