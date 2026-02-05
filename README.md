# research-mind-service

A FastAPI backend service for research-mind. Provides session management, subprocess-based code indexing via `mcp-vector-search`, audit logging, and workspace isolation for code research sessions.

**Stack**: Python 3.12+ | FastAPI 0.109 | SQLAlchemy 2.0 | PostgreSQL | Pydantic 2.5 | Alembic

---

## Quick Start

> **First time?** See the monorepo [Getting Started Guide](../docs/GETTING_STARTED.md) for complete prerequisites and setup.

### Local Development (without Docker)

**Prerequisites**: Python 3.12+, PostgreSQL 18+, [uv](https://docs.astral.sh/uv/)

```bash
# 1. Install dependencies
uv sync

# 2. Configure environment
cp .env.example .env
# Edit .env: set DATABASE_URL to your local PostgreSQL instance

# 3. Run database migrations
uv run alembic upgrade head

# 4. Start the development server
uv run uvicorn app.main:app --host 0.0.0.0 --port 15010 --reload

# 5. Verify
curl http://localhost:15010/health
```

### With Docker Compose

From the **monorepo root** (`research-mind/`):

```bash
docker compose up -d
```

This starts PostgreSQL and the service. The service is available at http://localhost:15010.

### Verify Installation

```bash
# Health check
curl http://localhost:15010/health

# Expected response:
# {"status":"ok","name":"research-mind-service","version":"0.1.0","git_sha":"abc1234"}
```

**URLs**:
- Service: http://localhost:15010
- Interactive API Docs (Swagger): http://localhost:15010/docs
- ReDoc: http://localhost:15010/redoc
- OpenAPI Schema: http://localhost:15010/openapi.json

---

## Architecture Overview

```
                         +-------------------+
                         |   FastAPI App      |
                         |   (app/main.py)    |
                         +--------+----------+
                                  |
               +------------------+------------------+
               |                  |                  |
     +---------v------+  +-------v--------+  +------v--------+
     | Session Routes |  | Indexing Routes |  | Audit Routes  |
     | /api/v1/       |  | /api/v1/       |  | /api/v1/      |
     | sessions/      |  | workspaces/    |  | sessions/     |
     +-------+--------+  +-------+--------+  | {id}/audit    |
             |                    |           +------+--------+
             |                    |                  |
     +-------v--------+  +-------v--------+  +------v--------+
     | Session Service|  | Indexing Service|  | Audit Service |
     +-------+--------+  +-------+--------+  +------+--------+
             |                    |                  |
             +--------------------+------------------+
                                  |
                         +--------v---------+
                         |   PostgreSQL     |
                         |   (SQLAlchemy)   |
                         +------------------+

                   Indexing subprocess flow:
                   +--------------------------+
                   | IndexingService          |
                   |   calls WorkspaceIndexer |
                   +------------+-------------+
                                |
                    +-----------v-----------+
                    |  subprocess.run(...)   |
                    |  cwd = workspace_dir   |
                    +-----------+-----------+
                                |
                    +-----------v-----------+
                    |  mcp-vector-search    |
                    |  CLI tool (external)  |
                    +-----------------------+
```

### Subprocess-Based Indexing

The service uses `mcp-vector-search` as an **external CLI tool**, not a Python library. All interactions happen via `subprocess.run()`:

```
Step 1: mcp-vector-search init --force
        (creates .mcp-vector-search/ directory in workspace)

Step 2: mcp-vector-search index --force
        (builds the vector index from source files)
```

The subprocess runs with `cwd` set to the workspace directory. Output (stdout/stderr) is captured and returned via the API. Timeouts are configurable per-operation.

---

## API Endpoints

### Health & Version

```bash
# Root health check (no /api/v1 prefix)
curl http://localhost:15010/health

# API-prefixed health check
curl http://localhost:15010/api/v1/health

# API version
curl http://localhost:15010/api/v1/version
```

### Sessions

```bash
# Create a session
curl -X POST http://localhost:15010/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"name": "OAuth2 Research", "description": "Token refresh patterns"}'

# List sessions (with pagination)
curl "http://localhost:15010/api/v1/sessions?limit=20&offset=0"

# Get a specific session
curl http://localhost:15010/api/v1/sessions/{session_id}

# Delete a session
curl -X DELETE http://localhost:15010/api/v1/sessions/{session_id}
```

### Workspace Indexing

```bash
# Trigger indexing for a workspace (session_id used as workspace_id)
curl -X POST http://localhost:15010/api/v1/workspaces/{session_id}/index \
  -H "Content-Type: application/json" \
  -d '{"force": true, "timeout": 120}'

# Check index status
curl http://localhost:15010/api/v1/workspaces/{session_id}/index/status
```

### Audit Logs

```bash
# Get audit logs for a session
curl "http://localhost:15010/api/v1/sessions/{session_id}/audit?limit=50&offset=0"
```

### Response Examples

**Create Session (201 Created)**:
```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "OAuth2 Research",
  "description": "Token refresh patterns",
  "workspace_path": "./content_sandboxes/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created_at": "2026-01-31T14:30:00",
  "last_accessed": "2026-01-31T14:30:00",
  "status": "active",
  "archived": false,
  "ttl_seconds": null,
  "is_indexed": false
}
```

**Index Result (200 OK)**:
```json
{
  "workspace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "success": true,
  "status": "completed",
  "elapsed_seconds": 12.345,
  "stdout": "Indexed 142 files...",
  "stderr": null
}
```

**Error Response (404)**:
```json
{
  "detail": {
    "error": {
      "code": "SESSION_NOT_FOUND",
      "message": "Session 'nonexistent-id' not found"
    }
  }
}
```

---

## Configuration Reference

All configuration is via environment variables. See `.env.example` for a complete template.

| Variable | Default | Description |
|---|---|---|
| `SERVICE_ENV` | `development` | Environment name (`development`, `production`) |
| `HOST` | `0.0.0.0` | Bind host |
| `PORT` | `15010` | Bind port |
| `DEBUG` | `false` | Enable debug mode |
| `DATABASE_URL` | `postgresql+psycopg://postgres:password@localhost:5432/research_mind` | PostgreSQL connection string (psycopg v3) |
| `CONTENT_SANDBOX_ROOT` | `./content_sandboxes` | Root directory for session data (content and indexes) |
| `SUBPROCESS_TIMEOUT_INIT` | `30` | Timeout (seconds) for `mcp-vector-search init` |
| `SUBPROCESS_TIMEOUT_INDEX` | `60` | Timeout (seconds) for `mcp-vector-search index` |
| `SUBPROCESS_TIMEOUT_LARGE` | `600` | Timeout (seconds) for large workspace indexing |
| `SESSION_MAX_DURATION_MINUTES` | `60` | Maximum session lifetime |
| `SESSION_IDLE_TIMEOUT_MINUTES` | `30` | Session idle timeout |
| `CORS_ORIGINS` | `http://localhost:15000,http://localhost:3000` | Allowed CORS origins (JSON array or comma-separated) |
| `ENABLE_AGENT_INTEGRATION` | `false` | Enable agent analysis features (future) |
| `ENABLE_CACHING` | `false` | Enable response caching (future) |
| `ENABLE_WARM_POOLS` | `false` | Enable subprocess warm pools (future) |
| `PATH_VALIDATOR_ENABLED` | `true` | Enable path traversal validation |
| `AUDIT_LOGGING_ENABLED` | `true` | Enable audit log recording |
| `SECRET_KEY` | `dev-secret-change-in-production` | JWT secret key (change in production) |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `HF_HOME` | `${HOME}/.cache/huggingface` | HuggingFace model cache directory |
| `VECTOR_SEARCH_ENABLED` | `true` | Enable vector search features |
| `VECTOR_SEARCH_MODEL` | `all-MiniLM-L6-v2` | Embedding model for vector search |

---

## Testing

### Run All Tests

```bash
uv run python -m pytest tests/ -v
```

### Unit Tests vs Integration Tests

```bash
# Unit tests only (fast, no database required)
uv run python -m pytest tests/ -v -k "not integration"

# Integration tests (requires PostgreSQL)
uv run python -m pytest tests/ -v -k "integration"

# With coverage report
uv run python -m pytest tests/ --cov=app --cov-report=html

# Specific test file
uv run python -m pytest tests/test_health.py -v
```

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures (TestClient, DB session)
├── test_health.py           # Health endpoint tests
├── test_sessions.py         # Session CRUD tests
├── test_indexing.py         # Indexing endpoint tests
├── test_audit.py            # Audit log tests
├── test_workspace_indexer.py # WorkspaceIndexer unit tests
├── test_path_validator.py   # Path validation security tests
└── ...                      # Additional test modules
```

### Code Quality

```bash
# Format code
uv run black app tests
uv run ruff check --fix app tests

# Type checking
uv run mypy app

# Lint
uv run ruff check app tests
```

---

## Security Features

### Path Validation

All file path operations are validated to prevent path traversal attacks. The `PathValidator` ensures:

- No `..` components in paths
- Paths resolve within the allowed workspace root
- Symlinks are checked and restricted
- Absolute paths outside workspace are rejected

### Session Isolation

Each session gets its own directory under `CONTENT_SANDBOX_ROOT`. Sessions cannot access files belonging to other sessions. The `SessionValidationMiddleware` enforces this at the HTTP layer.

### Audit Logging

All significant operations are recorded in the audit log table:

- Session creation, access, and deletion
- Indexing operations (start, completion, failure)
- Search queries and result counts
- Error events with stack traces

Query audit logs via `GET /api/v1/sessions/{session_id}/audit`.

### Structured Error Responses

All errors follow a consistent format with machine-readable error codes:

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Human-readable description"
  }
}
```

---

## How Indexing Works

### Subprocess Flow

```
Client                 Service                 mcp-vector-search CLI
  |                      |                            |
  |  POST /workspaces/   |                            |
  |  {id}/index          |                            |
  |--------------------->|                            |
  |                      |  subprocess.run(           |
  |                      |    "mcp-vector-search      |
  |                      |     init --force",         |
  |                      |    cwd=workspace_dir)      |
  |                      |--------------------------->|
  |                      |                            |
  |                      |   Creates .mcp-vector-     |
  |                      |   search/ directory        |
  |                      |<---------------------------|
  |                      |                            |
  |                      |  subprocess.run(           |
  |                      |    "mcp-vector-search      |
  |                      |     index --force",        |
  |                      |    cwd=workspace_dir)      |
  |                      |--------------------------->|
  |                      |                            |
  |                      |   Reads source files,      |
  |                      |   generates embeddings,    |
  |                      |   builds vector index      |
  |                      |<---------------------------|
  |                      |                            |
  |  200 OK              |                            |
  |  {success, elapsed}  |                            |
  |<---------------------|                            |
```

### Key Details

- **Two-step process**: `init` creates the index directory, `index` builds embeddings
- **Synchronous execution**: The HTTP request blocks until indexing completes
- **Configurable timeouts**: `SUBPROCESS_TIMEOUT_INIT` and `SUBPROCESS_TIMEOUT_INDEX`
- **Force re-index**: Pass `"force": true` to rebuild the index from scratch
- **Index detection**: `GET .../index/status` checks for `.mcp-vector-search/` directory
- **Error propagation**: CLI errors (timeout, not found, non-zero exit) are mapped to HTTP error codes

---

## Database Migrations

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Create a new migration after model changes
uv run alembic revision --autogenerate -m "description of change"

# Rollback one migration
uv run alembic downgrade -1

# Show current migration version
uv run alembic current

# Show migration history
uv run alembic history
```

---

## Project Structure

```
research-mind-service/
├── app/
│   ├── main.py                    # FastAPI app, middleware, lifecycle
│   ├── core/
│   │   ├── config.py              # Pydantic Settings configuration
│   │   ├── workspace_indexer.py   # Subprocess-based mcp-vector-search driver
│   │   └── path_validator.py      # Path traversal prevention
│   ├── routes/
│   │   ├── health.py              # GET /health
│   │   ├── api.py                 # GET /api/v1/version
│   │   ├── sessions.py            # Session CRUD endpoints
│   │   ├── indexing.py            # Workspace indexing endpoints
│   │   └── audit.py              # Audit log endpoints
│   ├── schemas/                   # Pydantic request/response models
│   ├── models/                    # SQLAlchemy ORM models
│   ├── services/                  # Business logic layer
│   ├── middleware/                 # HTTP middleware (session validation)
│   ├── db/                        # Database session management
│   └── auth/                      # Authentication stubs
├── tests/                         # pytest test suite (142 tests)
├── migrations/                    # Alembic database migrations
├── docs/
│   ├── api-contract.md            # API contract (frozen, synced with UI)
│   ├── DEPLOYMENT.md              # Deployment guide
│   └── TROUBLESHOOTING.md         # Common issues and solutions
├── Dockerfile                     # Multi-stage Docker build
├── pyproject.toml                 # Dependencies and metadata
├── alembic.ini                    # Alembic configuration
├── .env.example                   # Environment variable template
└── README.md                      # This file
```

---

## Future Plans

- **Search via Claude Code MCP**: Natural language search over indexed codebases using vector similarity
- **Agent Analysis**: AI-powered code analysis and question answering with evidence citations
- **Warm subprocess pools**: Pre-initialized `mcp-vector-search` processes for lower latency
- **Response caching**: Multi-level caching for search results
- **Authentication**: JWT-based authentication with role-based access control

---

## License

MIT
