# research-mind Service Development Guide

## Quick Start

```bash
cd /Users/mac/workspace/research-mind/research-mind-service
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 15010 --reload
```

Service: http://localhost:15010

## Project Structure

- **app/**: Application code
  - **main.py**: FastAPI app initialization with CORS middleware
  - **routes/**: Endpoint implementations (health.py, api.py)
  - **schemas/**: Pydantic models for request/response validation
  - **db/**: Database session and engine setup
  - **models/**: SQLAlchemy ORM models
  - **auth/**: Authentication stubs

- **tests/**: Test suite using pytest + pytest-asyncio

- **migrations/**: Alembic database migrations

## Common Tasks

```bash
# Run service with auto-reload
uv run uvicorn app.main:app --host 0.0.0.0 --port 15010 --reload

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=app --cov-report=html

# Type checking
uv run mypy app

# Format and lint
uv run black app tests
uv run ruff check --fix app tests

# Database migrations
uv run alembic upgrade head
uv run alembic downgrade -1
```

## API Endpoints

### Health Check
```bash
GET /health
```

Response:
```json
{
  "status": "ok",
  "name": "research-mind-service",
  "version": "0.1.0",
  "git_sha": "abc1234"
}
```

### API Version
```bash
GET /api/v1/version
```

Response:
```json
{
  "name": "research-mind-service",
  "version": "0.1.0",
  "git_sha": "abc1234"
}
```

## Configuration

All configuration is managed via environment variables. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Key variables:
- `SERVICE_PORT`: Service port (default: 15010)
- `DATABASE_URL`: PostgreSQL connection string
- `CORS_ORIGINS`: Comma-separated CORS allowed origins
- `SECRET_KEY`: JWT secret key
- `ALGORITHM`: JWT algorithm (HS256)

## Database

Database configuration uses SQLAlchemy with PostgreSQL. Connection details are in `.env`.

### Running Migrations

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Rollback one migration
uv run alembic downgrade -1

# Create new migration
uv run alembic revision --autogenerate -m "description"
```

## Testing

Tests use pytest and pytest-asyncio for async endpoint testing.

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_health.py

# Run with coverage
uv run pytest --cov=app --cov-report=html
```

## Vertical Slice Architecture

This service follows a vertical slice architecture pattern:
- Each feature is a complete slice: route → schema → model → test
- Shared utilities in `app/db/`, `app/schemas/`, `app/auth/`
- Tests collocate with slices

Example: Health check endpoint
- Route: `app/routes/health.py`
- Schema: `app/schemas/common.py` (HealthResponse)
- Test: `tests/test_health.py`

## CORS Configuration

CORS is configured in `app/main.py` to allow requests from:
- `http://localhost:15000` (development UI)

Modify `CORS_ORIGINS` in `.env` to add more origins:
```bash
CORS_ORIGINS=http://localhost:15000,https://example.com
```

## Production Considerations

- Set `SERVICE_ENV=production` in `.env`
- Change `SECRET_KEY` to a secure value
- Use environment-specific database URL
- Enable HTTPS/SSL
- Set up proper logging and monitoring
- Run migrations before deployment
