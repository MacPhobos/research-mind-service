# research-mind Service

A FastAPI backend service for the research-mind project.

## Quick Start

1. **Install Dependencies**
   ```bash
   uv sync
   ```

2. **Configure Environment**
   ```bash
   cp .env.example .env
   ```

3. **Run Service**
   ```bash
   uv run uvicorn app.main:app --host 0.0.0.0 --port 15010 --reload
   ```

4. **Test**
   ```bash
   uv run pytest
   ```

Service will be available at: http://localhost:15010

## Features

- FastAPI web framework with automatic OpenAPI documentation
- SQLAlchemy 2.0 ORM with async support
- Alembic database migrations
- Pydantic v2 for data validation
- JWT authentication stubs
- CORS middleware for frontend integration
- Comprehensive test suite with pytest

## Directory Structure

```
app/
├── main.py           # FastAPI application
├── routes/           # API endpoints
│   ├── health.py    # Health check
│   └── api.py       # Versioned endpoints
├── schemas/          # Pydantic models
├── models/           # SQLAlchemy models
├── db/              # Database configuration
└── auth/            # Authentication

tests/                # Test suite
migrations/           # Alembic migrations
docs/                 # Documentation
```

## Development

### Run Tests

```bash
uv run pytest
uv run pytest -v           # Verbose
uv run pytest --cov=app    # With coverage
```

### Type Checking

```bash
uv run mypy app
```

### Code Formatting

```bash
uv run black app tests
uv run ruff check --fix app tests
```

### Database Migrations

```bash
# Apply migrations
uv run alembic upgrade head

# Create new migration
uv run alembic revision --autogenerate -m "description"

# Rollback
uv run alembic downgrade -1
```

## Configuration

Environment variables (see `.env.example`):

- `SERVICE_PORT` - Service port (default: 15010)
- `DATABASE_URL` - PostgreSQL connection string
- `CORS_ORIGINS` - Comma-separated CORS origins
- `SECRET_KEY` - JWT secret key
- `ALGORITHM` - JWT algorithm (HS256)

## API Documentation

- Interactive Docs: http://localhost:15010/docs
- ReDoc: http://localhost:15010/redoc
- OpenAPI Schema: http://localhost:15010/openapi.json

## Health Check

```bash
curl http://localhost:15010/health
```

Expected response:
```json
{
  "status": "ok",
  "name": "research-mind-service",
  "version": "0.1.0",
  "git_sha": "abc1234"
}
```

## License

MIT
