# research-mind-service Development Guide

> **Backend Service for research-mind**
> **Stack**: FastAPI 0.109 · Python 3.12+ · SQLAlchemy 2.0 · Alembic · PostgreSQL · Pydantic 2.5

This is the backend service for research-mind. It provides REST API endpoints for session management, content indexing, vector search, and AI-powered analysis.

---

## Quick Start

```bash
# From service directory
cd /Users/mac/workspace/research-mind/research-mind-service

# Install dependencies (uv required)
uv sync

# Set up environment variables
cp .env.example .env
# Edit .env with your database URL and settings

# Run database migrations
uv run alembic upgrade head

# Start development server (port 15010)
uv run uvicorn app.main:app --host 0.0.0.0 --port 15010 --reload
```

**Service**: http://localhost:15010
**API Docs**: http://localhost:15010/docs
**OpenAPI Spec**: http://localhost:15010/openapi.json

---

## Project Structure

```
research-mind-service/
├── app/
│   ├── main.py                # FastAPI app + middleware + settings
│   ├── routes/                # API endpoints (health.py, api.py)
│   ├── schemas/               # Pydantic models (common.py)
│   ├── models/                # SQLAlchemy ORM models (session.py)
│   ├── db/                    # Database session management
│   ├── auth/                  # Authentication stubs (JWT placeholders)
│   └── sandbox/               # Session workspace management
├── tests/
│   ├── conftest.py            # pytest fixtures (TestClient)
│   └── test_health.py         # Health endpoint tests
├── migrations/
│   ├── env.py                 # Alembic environment config
│   ├── versions/              # Migration files
│   └── script.py.mako         # Migration template
├── docs/
│   └── api-contract.md        # API contract (frozen, synced with UI)
├── alembic.ini                # Alembic configuration
├── pyproject.toml             # Dependencies + metadata
├── Makefile                   # Common commands
├── .env.example               # Environment variable template
└── README.md                  # Service documentation
```

### Directory Responsibilities

- **`app/main.py`**: FastAPI app initialization, CORS middleware, settings via `pydantic-settings`
- **`app/routes/`**: API routers (vertical slices: health check, version, future session endpoints)
- **`app/schemas/`**: Pydantic models for request/response validation (`ErrorResponse`, `PaginatedResponse`, `HealthResponse`)
- **`app/models/`**: SQLAlchemy ORM models with `declarative_base` (e.g., `Session` model with UUID primary key)
- **`app/db/`**: Database session factory using `get_db()` dependency injection pattern
- **`app/auth/`**: JWT authentication stubs (not implemented, production TBD)
- **`app/sandbox/`**: Session workspace file operations and isolation
- **`tests/`**: pytest + pytest-asyncio tests using `TestClient` for endpoint testing
- **`migrations/`**: Alembic database migrations with auto-generation support

---

## API Contract (Critical)

### The Golden Rule: API Contract is FROZEN

**Contract Location**: `docs/api-contract.md` (source of truth)

The API contract defines all communication between this service and `research-mind-ui`. All changes flow through the contract first.

### Full End-to-End Contract Sync Workflow

This workflow covers **both service and UI** responsibilities:

#### Backend (Service) Steps

1. **Update Contract**: Edit `research-mind-service/docs/api-contract.md`
   - Add new endpoints, change schemas, update error codes
   - Version bump if breaking change (major.minor.patch)
   - Add changelog entry

2. **Update Pydantic Schemas**: Add/modify models in `app/schemas/`
   ```python
   # Example: app/schemas/session.py
   from pydantic import BaseModel
   from datetime import datetime

   class SessionCreate(BaseModel):
       name: str
       description: str | None = None

   class SessionResponse(BaseModel):
       id: str
       name: str
       description: str | None
       status: str
       workspace: str
       created_at: datetime
       updated_at: datetime
       indexed_count: int
       last_indexed_at: datetime | None
   ```

3. **Implement Routes**: Add/update routes in `app/routes/`
   ```python
   # Example: app/routes/sessions.py
   from fastapi import APIRouter, Depends
   from sqlalchemy.orm import Session
   from app.db.session import get_db
   from app.schemas.session import SessionCreate, SessionResponse

   router = APIRouter(prefix="/sessions", tags=["sessions"])

   @router.post("/", response_model=SessionResponse, status_code=201)
   async def create_session(
       session_data: SessionCreate,
       db: Session = Depends(get_db)
   ):
       # Implementation
       pass
   ```

4. **Run Backend Tests**: Ensure all tests pass
   ```bash
   uv run pytest -v
   ```

5. **Verify OpenAPI Spec**: Start server, check `/openapi.json`
   ```bash
   uv run uvicorn app.main:app --host 0.0.0.0 --port 15010 --reload
   curl http://localhost:15010/openapi.json | jq .
   ```

#### Frontend (UI) Steps

6. **Copy Contract to UI**: Synchronize contract file
   ```bash
   cp research-mind-service/docs/api-contract.md research-mind-ui/docs/api-contract.md
   ```

7. **Regenerate TypeScript Types**: From `research-mind-ui/` directory
   ```bash
   npm run gen:api
   # Runs: openapi-typescript http://localhost:15010/openapi.json -o src/lib/api/generated.ts
   ```

8. **Update UI Code**: Use new generated types in components
   ```typescript
   import type { SessionResponse } from '$lib/api/generated';

   async function fetchSession(id: string): Promise<SessionResponse> {
     const response = await fetch(`/api/v1/sessions/${id}`);
     return response.json();
   }
   ```

9. **Run UI Tests**: Ensure all tests pass
   ```bash
   npm test
   ```

### Contract Change Checklist

Before deploying any API change:

- [ ] Updated `research-mind-service/docs/api-contract.md`
- [ ] Version bumped (major/minor/patch as appropriate)
- [ ] Changelog entry added to contract
- [ ] Backend Pydantic schemas updated
- [ ] Backend routes implemented
- [ ] Backend tests pass (`uv run pytest`)
- [ ] Contract copied to `research-mind-ui/docs/api-contract.md`
- [ ] UI types regenerated (`npm run gen:api`)
- [ ] UI code updated to use new types
- [ ] UI tests pass (`npm test`)
- [ ] Both `api-contract.md` files are identical

### Important Rules

- **Never** manually edit `research-mind-ui/src/lib/api/generated.ts` (auto-generated)
- **Never** update service without updating contract first
- **Never** deploy UI without regenerating types after backend changes
- **Never** let the two `api-contract.md` files diverge
- **Always** bump version for breaking changes (major), new features (minor), or bug fixes (patch)

---

## FastAPI Development Patterns

### Adding a New Endpoint

1. **Define Pydantic Schema** (`app/schemas/`)
   ```python
   # app/schemas/content.py
   from pydantic import BaseModel

   class AddContentRequest(BaseModel):
       repository_path: str

   class AddContentResponse(BaseModel):
       session_id: str
       files_copied: int
       bytes_copied: int
       excluded: list[str]
       workspace_path: str
   ```

2. **Create Router** (`app/routes/`)
   ```python
   # app/routes/content.py
   from fastapi import APIRouter, HTTPException
   from app.schemas.content import AddContentRequest, AddContentResponse

   router = APIRouter(prefix="/sessions", tags=["content"])

   @router.post("/{session_id}/add-content", response_model=AddContentResponse)
   async def add_content(
       session_id: str,
       request: AddContentRequest
   ):
       # Implementation
       return AddContentResponse(
           session_id=session_id,
           files_copied=142,
           bytes_copied=2458123,
           excluded=[".git", "node_modules", "__pycache__"],
           workspace_path=f"/var/lib/research-mind/sessions/{session_id}/content"
       )
   ```

3. **Register Router** (`app/main.py`)
   ```python
   from app.routes import health, api, content

   app.include_router(health.router)
   app.include_router(api.router, prefix="/api/v1")
   app.include_router(content.router, prefix="/api/v1")
   ```

4. **Write Tests** (`tests/`)
   ```python
   # tests/test_content.py
   from fastapi.testclient import TestClient
   from app.main import app

   client = TestClient(app)

   def test_add_content():
       response = client.post(
           "/api/v1/sessions/sess_123/add-content",
           json={"repository_path": "/path/to/code"}
       )
       assert response.status_code == 200
       data = response.json()
       assert data["session_id"] == "sess_123"
       assert data["files_copied"] > 0
   ```

### Error Handling Patterns

Always use FastAPI's `HTTPException` with consistent error responses:

```python
from fastapi import HTTPException

# Not Found
if not session:
    raise HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "SESSION_NOT_FOUND",
                "message": f"Session '{session_id}' not found"
            }
        }
    )

# Bad Request (Validation)
if not path.exists():
    raise HTTPException(
        status_code=400,
        detail={
            "error": {
                "code": "INVALID_PATH",
                "message": f"Source path does not exist: {path}"
            }
        }
    )

# Internal Error
try:
    # Risky operation
    pass
except Exception as e:
    logger.exception("Operation failed")
    raise HTTPException(
        status_code=500,
        detail={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": str(e)
            }
        }
    )
```

### Dependency Injection Pattern

Use FastAPI's `Depends` for database sessions and other dependencies:

```python
from fastapi import Depends
from sqlalchemy.orm import Session
from app.db.session import get_db

@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    db: Session = Depends(get_db)  # Injected dependency
):
    session = db.query(SessionModel).filter_by(session_id=session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
```

---

## Database & SQLAlchemy Patterns

### ORM Model Pattern

All models use `declarative_base` with these conventions:

```python
from datetime import datetime
from uuid import uuid4
from sqlalchemy import Column, String, DateTime, Integer, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Session(Base):
    __tablename__ = "sessions"

    # UUID primary key (immutable)
    session_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))

    # Required fields
    name = Column(String(255), nullable=False)
    workspace_path = Column(String(512), nullable=False, unique=True)

    # Optional fields
    description = Column(String(1024), nullable=True)

    # Timestamps (UTC)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_accessed = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Status enum (use String, validate in Pydantic)
    status = Column(String(50), nullable=False, default="active")

    # JSON metadata
    index_stats = Column(JSON, nullable=True, default=dict)

    def __repr__(self):
        return f"<Session {self.session_id}: {self.name}>"
```

**Key Patterns**:
- UUID primary keys (`session_id`, `job_id`, etc.) as `String(36)`
- `created_at` and `updated_at` timestamps (UTC, auto-populated)
- `nullable=False` for required fields, `nullable=True` for optional
- Use `JSON` column type for flexible metadata (e.g., `index_stats`)
- `unique=True` for workspace paths to prevent conflicts

### Session Management

Database sessions use generator pattern with `yield`:

```python
# app/db/session.py
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine
from typing import Generator

_engine = None
_SessionLocal = None

def get_engine():
    global _engine
    if _engine is None:
        from app.main import settings
        _engine = create_engine(
            settings.DATABASE_URL,
            echo=False,           # Set to True for SQL logging
            pool_pre_ping=True,   # Check connection before use
        )
    return _engine

def get_session_local():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine()
        )
    return _SessionLocal

def get_db() -> Generator[Session, None, None]:
    """Dependency for FastAPI route handlers."""
    db = get_session_local()()
    try:
        yield db
    finally:
        db.close()
```

**Usage in Routes**:
```python
from fastapi import Depends
from sqlalchemy.orm import Session
from app.db.session import get_db

@router.get("/sessions")
async def list_sessions(db: Session = Depends(get_db)):
    sessions = db.query(SessionModel).all()
    return {"data": sessions, "pagination": {...}}
```

### Alembic Migration Workflow

1. **Create Migration** (after model changes):
   ```bash
   make migrate-new MSG="Add sessions table"
   # Or: uv run alembic revision --autogenerate -m "Add sessions table"
   ```

2. **Review Generated Migration** (`migrations/versions/xxx_add_sessions_table.py`)
   ```python
   def upgrade() -> None:
       op.create_table(
           'sessions',
           sa.Column('session_id', sa.String(36), primary_key=True),
           sa.Column('name', sa.String(255), nullable=False),
           sa.Column('created_at', sa.DateTime(), nullable=False),
       )

   def downgrade() -> None:
       op.drop_table('sessions')
   ```

3. **Apply Migration**:
   ```bash
   make migrate
   # Or: uv run alembic upgrade head
   ```

4. **Rollback** (if needed):
   ```bash
   make migrate-down
   # Or: uv run alembic downgrade -1
   ```

**Important**:
- Always review auto-generated migrations before applying
- Test migrations on development database first
- Keep migrations idempotent (safe to run multiple times)
- Never modify applied migrations (create new one to fix)

---

## Pydantic Schema Patterns

### Request/Response Models

```python
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

# Request model (input validation)
class CreateSessionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1024)

# Response model (output serialization)
class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # Enable ORM mode

    id: str
    name: str
    description: str | None
    status: str  # "active" | "archived"
    workspace: str
    created_at: datetime
    updated_at: datetime
    indexed_count: int
    last_indexed_at: datetime | None
```

**Pydantic v2 Patterns**:
- Use `model_config = ConfigDict(from_attributes=True)` instead of `class Config: orm_mode = True`
- Use `str | None` instead of `Optional[str]` (Python 3.10+)
- Use `Field(...)` for required fields with validation
- Use `Field(None, ...)` for optional fields with defaults

### Generic Types

```python
from pydantic import BaseModel
from typing import TypeVar, Generic

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    pagination: dict[str, int]  # {"limit": 10, "offset": 0, "total": 42}

# Usage
from app.schemas.session import SessionResponse

@router.get("/sessions", response_model=PaginatedResponse[SessionResponse])
async def list_sessions():
    return PaginatedResponse(
        data=[...],
        pagination={"limit": 10, "offset": 0, "total": 42}
    )
```

### Validation Patterns

```python
from pydantic import BaseModel, field_validator, model_validator
from pathlib import Path

class AddContentRequest(BaseModel):
    repository_path: str

    @field_validator("repository_path")
    @classmethod
    def validate_path_exists(cls, v: str) -> str:
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Path does not exist: {v}")
        if not path.is_dir():
            raise ValueError(f"Path is not a directory: {v}")
        return str(path.resolve())

class IndexingRequest(BaseModel):
    force: bool = False
    chunk_size: int = 512

    @model_validator(mode="after")
    def validate_chunk_size(self):
        if self.chunk_size < 128 or self.chunk_size > 2048:
            raise ValueError("chunk_size must be between 128 and 2048")
        return self
```

---

## Testing Conventions

### Test Structure

```
tests/
├── conftest.py          # Shared fixtures
├── test_health.py       # Health endpoint tests
├── test_sessions.py     # Session CRUD tests
└── test_search.py       # Search endpoint tests
```

### pytest Fixtures (`conftest.py`)

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.session import get_db
from app.models.session import Base

# Test database URL (use in-memory SQLite or test Postgres)
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

@pytest.fixture
def db_engine():
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session(db_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSessionLocal()
    yield session
    session.close()

@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
```

### TestClient Usage

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "git_sha" in data

def test_create_session(client):
    response = client.post(
        "/api/v1/sessions",
        json={"name": "Test Session", "description": "Test description"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Session"
    assert "id" in data

def test_session_not_found(client):
    response = client.get("/api/v1/sessions/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "SESSION_NOT_FOUND"
```

### Async Tests (pytest-asyncio)

```python
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    result = await some_async_function()
    assert result == expected_value
```

**Testing Best Practices**:
- One test file per route module
- Use fixtures for database setup/teardown
- Test happy path, error cases, and edge cases
- Use `TestClient` for endpoint integration tests
- Mock external dependencies (vector search, LLM APIs)
- Test validation errors (400), not found (404), internal errors (500)

---

## Environment & Configuration

### Environment Variables (`.env`)

```bash
# Server Configuration
SERVICE_ENV=development
SERVICE_HOST=0.0.0.0
SERVICE_PORT=15010

# Database Configuration
DATABASE_URL=postgresql://postgres:password@localhost:5432/research_mind

# CORS Configuration
CORS_ORIGINS=http://localhost:15000

# Authentication (Development - Change for Production!)
SECRET_KEY=dev-secret-change-in-production
ALGORITHM=HS256

# HuggingFace & Model Caching
HF_HOME=${HOME}/.cache/huggingface
TRANSFORMERS_CACHE=${HF_HOME}/transformers
HF_HUB_CACHE=${HF_HOME}/hub

# Vector Search Configuration
VECTOR_SEARCH_ENABLED=true
VECTOR_SEARCH_MODEL=all-MiniLM-L6-v2
SQLALCHEMY_ECHO=false
```

### Settings Pattern (pydantic-settings)

```python
# app/main.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SERVICE_ENV: str = "development"
    SERVICE_HOST: str = "0.0.0.0"
    SERVICE_PORT: int = 15010
    DATABASE_URL: str = "postgresql://postgres:devpass123@localhost:5432/research_mind_db"
    CORS_ORIGINS: str = "http://localhost:15000"
    SECRET_KEY: str = "dev-secret-change-in-production"
    ALGORITHM: str = "HS256"

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore unknown env vars

settings = Settings()

# Usage
app = FastAPI(title="research-mind API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Important**:
- Never commit `.env` to git (use `.env.example` template)
- Always use `settings.VARIABLE` instead of `os.getenv()`
- Change `SECRET_KEY` in production
- Set `SQLALCHEMY_ECHO=true` for SQL query debugging

---

## Guard Rails

### Mandatory Practices

1. **Migrations Required**: All schema changes via Alembic
   ```bash
   # ❌ NEVER modify database schema manually
   # ✅ ALWAYS create migration
   make migrate-new MSG="Add new column"
   make migrate
   ```

2. **Type Safety**: All routes use Pydantic models
   ```python
   # ❌ WRONG - No validation
   @router.post("/sessions")
   async def create_session(data: dict):
       return data

   # ✅ CORRECT - Pydantic validation
   @router.post("/sessions", response_model=SessionResponse)
   async def create_session(data: CreateSessionRequest):
       return SessionResponse(...)
   ```

3. **Error Handling**: Use `HTTPException` with error codes
   ```python
   # ❌ WRONG - Generic error
   raise HTTPException(status_code=404, detail="Not found")

   # ✅ CORRECT - Structured error
   raise HTTPException(
       status_code=404,
       detail={
           "error": {
               "code": "SESSION_NOT_FOUND",
               "message": f"Session '{session_id}' not found"
           }
       }
   )
   ```

4. **Contract Sync**: Never deploy without UI type regeneration
   ```bash
   # After backend changes:
   cp docs/api-contract.md ../research-mind-ui/docs/api-contract.md
   cd ../research-mind-ui
   npm run gen:api  # Regenerate types
   ```

5. **Tests Required**: Minimum 1 test per endpoint
   ```python
   # tests/test_sessions.py
   def test_create_session(client):
       response = client.post("/api/v1/sessions", json={...})
       assert response.status_code == 201
   ```

6. **No `.env` in Git**: Always use `.env.example`
   ```bash
   # ❌ NEVER commit
   git add .env

   # ✅ Update template only
   git add .env.example
   ```

---

## Common Commands

### Development

```bash
# Install dependencies
make install
# Or: uv sync

# Start development server (auto-reload on port 15010)
make dev
# Or: uv run uvicorn app.main:app --host 0.0.0.0 --port 15010 --reload

# Start production server (no reload)
make run-prod
# Or: uv run uvicorn app.main:app --host 0.0.0.0 --port 15010
```

### Testing

```bash
# Run all tests
make test
# Or: uv run pytest -v

# Run specific test file
uv run pytest tests/test_health.py -v

# Run with coverage
uv run pytest --cov=app --cov-report=html

# Watch mode (requires pytest-watch)
make test-watch
# Or: uv run pytest --watch
```

### Code Quality

```bash
# Format code (black + ruff)
make fmt
# Or: uv run black app tests && uv run ruff check --fix app tests

# Lint (ruff)
make lint
# Or: uv run ruff check app tests

# Type check (mypy)
make typecheck
# Or: uv run mypy app

# Run all checks (lint + typecheck + test)
make check
```

### Database Migrations

```bash
# Apply all pending migrations
make migrate
# Or: uv run alembic upgrade head

# Create new migration (after model changes)
make migrate-new MSG="Add users table"
# Or: uv run alembic revision --autogenerate -m "Add users table"

# Rollback one migration
make migrate-down
# Or: uv run alembic downgrade -1

# Show current migration version
uv run alembic current

# Show migration history
uv run alembic history
```

### Cleanup

```bash
# Remove __pycache__, .mypy_cache, .pytest_cache
make clean
```

---

## API Endpoints (Current State)

### Health Check

**`GET /health`** (no `/api/v1` prefix)

Returns service health status.

```bash
curl http://localhost:15010/health
```

Response:
```json
{
  "status": "ok",
  "name": "research-mind-service",
  "version": "0.1.0",
  "git_sha": "fb40e9c"
}
```

### API Version

**`GET /api/v1/version`**

Returns API version information.

```bash
curl http://localhost:15010/api/v1/version
```

Response:
```json
{
  "name": "research-mind-service",
  "version": "0.1.0",
  "git_sha": "fb40e9c"
}
```

### Future Endpoints (See `docs/api-contract.md`)

- **Sessions**: `POST /api/v1/sessions`, `GET /api/v1/sessions`, `GET /api/v1/sessions/{id}`, `PATCH /api/v1/sessions/{id}`, `DELETE /api/v1/sessions/{id}`
- **Content**: `POST /api/v1/sessions/{id}/add-content`
- **Indexing**: `POST /api/v1/sessions/{id}/index`, `GET /api/v1/sessions/{id}/index/jobs/{job_id}`
- **Search**: `POST /api/v1/sessions/{id}/search`
- **Analysis**: `POST /api/v1/sessions/{id}/analyze`

**See full endpoint details in `docs/api-contract.md`.**

---

## CORS Configuration

CORS is configured in `app/main.py` to allow requests from the UI.

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),  # "http://localhost:15000"
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Development**: `CORS_ORIGINS=http://localhost:15000`
**Production**: `CORS_ORIGINS=https://research-mind.io,https://api.research-mind.io`

---

## Authentication

**Current Status**: Not implemented (stubs exist in `app/auth/`)

**Future Implementation**: JWT token-based authentication planned for production.

All endpoints are currently open. Authentication will be added in a future version with:
- Token validation middleware
- Role-based access control (RBAC)
- Session-level permissions
- Audit logging of all operations

---

## Production Considerations

### Before Deploying

1. **Change `SECRET_KEY`** in `.env` to a secure random value
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Set `SERVICE_ENV=production`** in `.env`

3. **Use Production Database URL**
   ```bash
   DATABASE_URL=postgresql://user:pass@prod-db.example.com:5432/research_mind
   ```

4. **Enable HTTPS/SSL** (use reverse proxy like nginx)

5. **Run Migrations** before deployment
   ```bash
   uv run alembic upgrade head
   ```

6. **Set Up Logging** (production-grade logging)
   ```python
   import logging
   logging.basicConfig(level=logging.INFO)
   ```

7. **Enable Monitoring** (Sentry, DataDog, etc.)

8. **Configure CORS** for production domains
   ```bash
   CORS_ORIGINS=https://research-mind.io
   ```

---

## Tech Stack Details

- **FastAPI 0.109**: High-performance async web framework
- **Python 3.12+**: Modern Python with type hints
- **SQLAlchemy 2.0**: SQL toolkit and ORM
- **Alembic 1.13**: Database migration tool
- **PostgreSQL**: Production database (via `psycopg` binary)
- **Pydantic 2.5**: Data validation using Python type annotations
- **pydantic-settings**: Settings management from environment variables
- **python-jose**: JWT token creation/validation (future auth)
- **passlib**: Password hashing (future auth)
- **pytest 7.4**: Testing framework
- **pytest-asyncio**: Async test support
- **httpx**: Test client for FastAPI
- **ruff**: Fast Python linter
- **black**: Code formatter
- **mypy**: Static type checker
- **uv**: Fast Python package installer

---

## Port Configuration

**Service Port**: `15010` (default)

Change in `.env`:
```bash
SERVICE_PORT=15010
```

**Important**: Service port must differ from UI port (15000) to avoid conflicts.

---

## Summary

This service follows FastAPI best practices with:
- **Type Safety**: Pydantic models for all inputs/outputs
- **Database**: SQLAlchemy ORM with Alembic migrations
- **Testing**: pytest with TestClient for endpoint testing
- **API Contract**: Frozen contract synced with UI
- **CORS**: Configured for UI access
- **Settings**: Environment-based configuration
- **Quality**: Linting (ruff), formatting (black), type checking (mypy)

**Key Workflow**: Contract → Schemas → Routes → Tests → UI Sync

Always refer to `docs/api-contract.md` for API definitions and keep it synchronized with the UI.
