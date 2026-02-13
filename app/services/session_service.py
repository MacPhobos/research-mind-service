"""Business logic for session CRUD operations."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.models.content_item import ContentItem
from app.models.session import Session
from app.schemas.session import (
    CreateSessionRequest,
    SessionResponse,
    UpdateSessionRequest,
)

logger = logging.getLogger(__name__)

# Skills to deploy into Q&A sandbox directories for better answer quality.
# Maps the claude-mpm skill name to the directory name under .claude/skills/.
# Rationale: docs/team-research/agents-and-skills-reduction/03-final-recommendations.md
MINIMAL_QA_SKILLS: tuple[tuple[str, str], ...] = (
    ("json-data-handling", "universal-data-json-data-handling"),
    ("mcp", "toolchains-ai-protocols-mcp"),
    ("writing-plans", "universal-collaboration-writing-plans"),
    ("systematic-debugging", "universal-debugging-systematic-debugging"),
    ("session-compression", "toolchains-ai-techniques-session-compression"),
)

# Monorepo root (parent of the service directory)
_MONOREPO_ROOT = Path(__file__).resolve().parents[3]

# Template content for CLAUDE.md in session sandbox directories
SANDBOX_CLAUDE_MD_TEMPLATE = """# Research Assistant

You are a research assistant answering questions based on content in this directory.

## Rules

1. Answer ONLY from content in this directory. If the content doesn't cover the question, say so.
2. Cite sources by including file paths for claims (e.g., "According to `{content_id}/file.md`...").
3. Keep answers concise and evidence-based. Quote relevant passages when helpful.
4. If a question is ambiguous, state your interpretation before answering.

## How to Find Information

Content is organized in subdirectories named by UUID (content_id). Each contains files retrieved from various sources (URLs, documents, git repos, text).

**For broad or conceptual questions**: Use the `mcp-vector-search` tools:
- `search_code` with a natural language query to find relevant content
- `search_context` with a description and focus areas for deeper search

**For specific lookups**: Use the Read tool to read files directly when you already know the path.

**Search strategy**: Start with `search_code` to find relevant files, then Read the most relevant results to get full context before answering.

## Output Format

- Use markdown formatting for structure (headings, lists, code blocks).
- Cite sources inline by referencing file paths in backticks (e.g., "According to `{content_id}/file.md`...").
- For code questions, include relevant code snippets with file paths.
- Do NOT include a separate "Sources" or "References" section at the end. Inline citations are sufficient.

## What NOT to Do

- Do not make up information not present in the content.
- Do not execute commands or modify files.
- Do not search the web or use external knowledge to supplement answers.
"""


# Minimal system prompt for Q&A sandboxes, replacing the ~56KB default
# PM_INSTRUCTIONS.md (~14K tokens) that claude-mpm normally injects.
# This is loaded by claude-mpm's InstructionLoader via
# .claude-mpm/PM_INSTRUCTIONS_DEPLOYED.md (Priority 1 in the loader).
# Version must be >= source PM_INSTRUCTIONS_VERSION (currently 0009).
MINIMAL_QA_PM_INSTRUCTIONS = (
    "<!-- PM_INSTRUCTIONS_VERSION: 9999 -->\n"
    "# Q&A Research Assistant\n\n"
    "You are a research assistant answering questions about indexed documents.\n\n"
    "## Rules\n"
    "- Answer ONLY from documents in the current working directory\n"
    "- Cite sources with file paths\n"
    "- Use mcp-vector-search tools for semantic search\n"
    "- If the answer is not found in the documents, say so clearly\n"
    "- Keep answers concise and evidence-based\n"
    "- Do not make up information or hallucinate sources\n"
)


def create_sandbox_pm_instructions(sandbox_path: Path | str) -> None:
    """Create minimal PM_INSTRUCTIONS_DEPLOYED.md for Q&A sandbox.

    Replaces the ~56KB default PM_INSTRUCTIONS that claude-mpm injects as a
    system prompt (~14K tokens) with a minimal Q&A-focused version (~125 tokens).

    The file is written to ``.claude-mpm/PM_INSTRUCTIONS_DEPLOYED.md`` because
    that is what claude-mpm's InstructionLoader reads (Priority 1), with a
    version comment (``PM_INSTRUCTIONS_VERSION: 9999``) to ensure it is always
    preferred over the packaged source.

    Args:
        sandbox_path: Path to the session sandbox directory.
    """
    sandbox_path = Path(sandbox_path)
    pm_dir = sandbox_path / ".claude-mpm"
    pm_dir.mkdir(parents=True, exist_ok=True)
    deployed_path = pm_dir / "PM_INSTRUCTIONS_DEPLOYED.md"
    deployed_path.write_text(MINIMAL_QA_PM_INSTRUCTIONS)
    logger.debug("Created minimal PM_INSTRUCTIONS_DEPLOYED.md in %s", sandbox_path)


def create_sandbox_claude_md(sandbox_path: Path | str) -> None:
    """Create CLAUDE.md file in the sandbox directory.

    Args:
        sandbox_path: Path to the session sandbox directory.
    """
    sandbox_path = Path(sandbox_path)
    claude_md_path = sandbox_path / "CLAUDE.md"
    claude_md_path.write_text(SANDBOX_CLAUDE_MD_TEMPLATE)
    logger.debug("Created CLAUDE.md in %s", sandbox_path)


def create_sandbox_claude_mpm_config(sandbox_path: Path | str) -> None:
    """Create optimized .claude-mpm/configuration.yaml for Q&A use case."""
    sandbox_path = Path(sandbox_path)
    config_dir = sandbox_path / ".claude-mpm"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "configuration.yaml"
    config_path.write_text(
        "agent_sync:\n"
        "  enabled: false\n"
        "\n"
        "skills:\n"
        "  auto_deploy: false\n"
        "  agent_referenced:\n"
        "    - json-data-handling\n"
        "    - mcp\n"
        "    - writing-plans\n"
        "    - systematic-debugging\n"
        "    - session-compression\n"
        "  user_defined: []\n"
    )
    logger.debug("Created claude-mpm configuration in %s", config_dir)


def deploy_minimal_sandbox_skills(sandbox_path: Path | str) -> None:
    """Copy a curated set of skill directories into the sandbox.

    Each skill directory from the monorepo root ``.claude/skills/`` is copied
    into ``<sandbox>/.claude/skills/``.  Files named ``.etag_cache.json`` are
    excluded because they contain ephemeral cache data irrelevant to the
    sandbox.

    Missing source skill directories are logged as warnings and skipped so
    that session creation never fails due to a missing skill.

    Args:
        sandbox_path: Path to the session sandbox directory.
    """
    sandbox_path = Path(sandbox_path)
    dest_skills_dir = sandbox_path / ".claude" / "skills"
    dest_skills_dir.mkdir(parents=True, exist_ok=True)

    source_skills_root = _MONOREPO_ROOT / ".claude" / "skills"

    def _ignore_etag_cache(directory: str, contents: list[str]) -> set[str]:
        """shutil.copytree ignore callback -- skip .etag_cache.json."""
        return {name for name in contents if name == ".etag_cache.json"}

    for _skill_name, dir_name in MINIMAL_QA_SKILLS:
        src = source_skills_root / dir_name
        dst = dest_skills_dir / dir_name
        if not src.is_dir():
            logger.warning("Skill directory not found, skipping: %s", src)
            continue
        shutil.copytree(src, dst, ignore=_ignore_etag_cache, dirs_exist_ok=True)
        logger.debug("Deployed skill %s -> %s", dir_name, dst)

    logger.debug(
        "Deployed %d sandbox skills to %s", len(MINIMAL_QA_SKILLS), dest_skills_dir
    )


def migrate_sandbox_config(sandbox_path: Path | str) -> bool:
    """Migrate a legacy sandbox to the minimal agent/skill configuration.

    Removes all agent files and replaces skills with the MINIMAL_QA_SKILLS
    set. Preserves CLAUDE.md, .mcp.json, indexed content, and all sandbox
    data outside ``.claude/agents/`` and ``.claude/skills/``.

    Args:
        sandbox_path: Path to the session sandbox directory.

    Returns:
        True if migration was performed, False if sandbox was already minimal.
    """
    sandbox_path = Path(sandbox_path)
    migrated = False

    # Step 1: Remove legacy agent files
    agents_dir = sandbox_path / ".claude" / "agents"
    if agents_dir.exists():
        shutil.rmtree(agents_dir)
        logger.info("Removed legacy agents from %s", sandbox_path)
        migrated = True

    # Step 2: Replace skills with minimal set
    skills_dir = sandbox_path / ".claude" / "skills"
    if skills_dir.exists():
        existing_skills = set(d.name for d in skills_dir.iterdir() if d.is_dir())
        expected_skills = set(dir_name for _, dir_name in MINIMAL_QA_SKILLS)

        if existing_skills != expected_skills:
            shutil.rmtree(skills_dir)
            deploy_minimal_sandbox_skills(sandbox_path)
            logger.info(
                "Replaced %d skills with %d minimal skills in %s",
                len(existing_skills),
                len(MINIMAL_QA_SKILLS),
                sandbox_path,
            )
            migrated = True

    # Step 3: Update configuration.yaml
    config_path = sandbox_path / ".claude-mpm" / "configuration.yaml"
    if config_path.exists():
        content = config_path.read_text()
        # Check if config still has the old 52-entry skill list
        if "agent_referenced:" in content:
            lines = content.split("\n")
            skill_count = sum(1 for line in lines if line.strip().startswith("- "))
            if skill_count != len(MINIMAL_QA_SKILLS):
                create_sandbox_claude_mpm_config(sandbox_path)
                logger.info("Updated configuration.yaml in %s", sandbox_path)
                migrated = True

    # Step 4: Replace PM_INSTRUCTIONS_DEPLOYED.md with minimal Q&A version
    deployed_path = sandbox_path / ".claude-mpm" / "PM_INSTRUCTIONS_DEPLOYED.md"
    if deployed_path.exists():
        original_size = deployed_path.stat().st_size
        if original_size > 2000:  # Only replace if it's the large default
            create_sandbox_pm_instructions(sandbox_path)
            logger.info(
                "Replaced PM_INSTRUCTIONS_DEPLOYED.md (%d bytes -> minimal) in %s",
                original_size,
                sandbox_path,
            )
            migrated = True

    if migrated:
        logger.info("Migrated sandbox config for %s", sandbox_path)
    else:
        logger.debug("Sandbox %s already has minimal config", sandbox_path)

    return migrated


def migrate_all_sandboxes() -> dict[str, int]:
    """Migrate all existing sandboxes to minimal configuration.

    Returns:
        Dict with counts: {"migrated": N, "skipped": M, "errors": E}
    """
    sandbox_root = Path(settings.content_sandbox_root)
    results = {"migrated": 0, "skipped": 0, "errors": 0}

    if not sandbox_root.exists():
        logger.warning("Sandbox root does not exist: %s", sandbox_root)
        return results

    for sandbox_dir in sandbox_root.iterdir():
        if not sandbox_dir.is_dir():
            continue
        # Skip directories that don't look like session sandboxes
        if not (sandbox_dir / "CLAUDE.md").exists():
            continue

        try:
            if migrate_sandbox_config(sandbox_dir):
                results["migrated"] += 1
            else:
                results["skipped"] += 1
        except Exception:
            logger.exception("Failed to migrate sandbox %s", sandbox_dir)
            results["errors"] += 1

    logger.info(
        "Batch migration complete: %d migrated, %d skipped, %d errors",
        results["migrated"],
        results["skipped"],
        results["errors"],
    )
    return results


def _build_response(session: Session, db: DbSession | None = None) -> SessionResponse:
    """Convert an ORM Session into a SessionResponse with is_indexed and content_count.

    Args:
        session: The ORM Session object.
        db: Optional database session for querying content count.
            If not provided, content_count defaults to 0.
    """
    content_count = 0
    if db is not None:
        content_count = (
            db.query(ContentItem)
            .filter(ContentItem.session_id == session.session_id)
            .count()
        )

    return SessionResponse(
        session_id=session.session_id,
        name=session.name,
        description=session.description,
        workspace_path=session.workspace_path,
        created_at=session.created_at,
        last_accessed=session.last_accessed,
        status=session.status,
        archived=session.archived,
        ttl_seconds=session.ttl_seconds,
        is_indexed=session.is_indexed(),
        content_count=content_count,
    )


def create_session(db: DbSession, request: CreateSessionRequest) -> SessionResponse:
    """Create a new session, persist it, and create the workspace directory."""
    # Generate session_id eagerly so we can derive workspace_path
    session_id = str(uuid4())
    workspace_path = os.path.join(settings.content_sandbox_root, session_id)

    session = Session(
        session_id=session_id,
        name=request.name,
        description=request.description,
        workspace_path=workspace_path,
    )

    db.add(session)
    db.commit()
    db.refresh(session)

    # Create workspace directory on disk
    os.makedirs(session.workspace_path, exist_ok=True)

    # Create CLAUDE.md file in the sandbox directory
    create_sandbox_claude_md(session.workspace_path)

    # Pre-create claude-mpm configuration for faster subprocess startup
    create_sandbox_claude_mpm_config(session.workspace_path)

    # Create minimal PM_INSTRUCTIONS for Q&A (instead of the 56KB default)
    create_sandbox_pm_instructions(session.workspace_path)

    # Deploy minimal skill files so the Q&A subprocess has context
    deploy_minimal_sandbox_skills(session.workspace_path)

    # Remove any agents that claude-mpm may have synced into the sandbox.
    # Agents serve no purpose in oneshot (--non-interactive) Q&A mode and
    # waste ~43K tokens per question if present.
    agents_dir = Path(session.workspace_path) / ".claude" / "agents"
    if agents_dir.exists():
        shutil.rmtree(agents_dir)
        logger.debug("Removed agents directory from sandbox %s", session.workspace_path)

    logger.info("Created session %s at %s", session.session_id, session.workspace_path)

    return _build_response(session, db)


def get_session(db: DbSession, session_id: str) -> SessionResponse | None:
    """Fetch a session by ID and update last_accessed. Returns None if not found."""
    session = db.query(Session).filter(Session.session_id == session_id).first()
    if session is None:
        return None

    session.mark_accessed()
    db.commit()
    db.refresh(session)

    return _build_response(session, db)


def list_sessions(
    db: DbSession, limit: int = 20, offset: int = 0
) -> tuple[list[SessionResponse], int]:
    """Return a paginated list of sessions and total count."""
    total = db.query(Session).count()
    rows = (
        db.query(Session)
        .order_by(Session.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    sessions = [_build_response(s, db) for s in rows]
    return sessions, total


def update_session(
    db: DbSession, session_id: str, request: UpdateSessionRequest
) -> SessionResponse | None:
    """Update a session's mutable fields (name, description, status).

    Returns the updated SessionResponse, or None if session not found.
    """
    session = db.query(Session).filter(Session.session_id == session_id).first()
    if session is None:
        return None

    # Update only fields that are provided (not None)
    if request.name is not None:
        session.name = request.name
    if request.description is not None:
        session.description = request.description
    if request.status is not None:
        session.status = request.status

    session.mark_accessed()
    db.commit()
    db.refresh(session)

    logger.info("Updated session %s", session_id)
    return _build_response(session, db)


def delete_session(db: DbSession, session_id: str) -> bool:
    """Delete a session record and remove its workspace directory.

    Returns True if the session was found and deleted, False otherwise.
    """
    session = db.query(Session).filter(Session.session_id == session_id).first()
    if session is None:
        return False

    workspace = session.workspace_path

    db.delete(session)
    db.commit()

    # Clean up workspace directory (contains content and index data)
    if workspace and os.path.isdir(workspace):
        shutil.rmtree(workspace, ignore_errors=True)
        logger.info("Removed session directory %s", workspace)

    logger.info("Deleted session %s", session_id)
    return True
