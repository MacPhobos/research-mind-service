# Deployment Guide

This guide covers deploying research-mind-service for local development and production environments.

---

## Prerequisites

- **Python 3.12+** with [uv](https://docs.astral.sh/uv/) package manager
- **PostgreSQL 15+** (local or remote)
- **mcp-vector-search** CLI tool installed and on PATH (for indexing features)
- **Docker** and **Docker Compose** (for containerized deployment)

---

## Local Development Setup

### 1. Install Dependencies

```bash
cd research-mind-service
uv sync
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set your database connection:

```bash
DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/research_mind
```

### 3. Create the Database

```bash
# Create the PostgreSQL database (if it does not already exist)
createdb research_mind

# Or via psql:
psql -U postgres -c "CREATE DATABASE research_mind;"
```

### 4. Run Migrations

```bash
uv run alembic upgrade head
```

This creates all required tables (sessions, audit_logs, etc.).

### 5. Install mcp-vector-search (Optional)

The indexing features require `mcp-vector-search` to be available on PATH. Install it according to its documentation. The service will log a warning at startup if the CLI is not found, but all other features will work normally.

### 6. Start the Development Server

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 15010 --reload
```

The `--reload` flag enables auto-reload on code changes. In development mode (`SERVICE_ENV=development`), the service will also auto-create database tables on startup as a convenience.

### 7. Verify

```bash
curl http://localhost:15010/health
# {"status":"ok","name":"research-mind-service","version":"0.1.0","git_sha":"..."}
```

---

## Docker Deployment

### Using Docker Compose (Recommended)

From the monorepo root (`research-mind/`):

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f service

# Stop all services
docker compose down

# Stop and remove volumes (full reset)
docker compose down -v
```

The Docker Compose configuration starts:

- **postgres**: PostgreSQL 15 with health checks and persistent volume
- **service**: The research-mind-service built from `./research-mind-service/Dockerfile`

### Database Migrations in Docker

After the first start, run migrations inside the service container:

```bash
docker compose exec service alembic upgrade head
```

Or add a migration step to your startup script.

### Building the Docker Image Standalone

```bash
cd research-mind-service
docker build -t research-mind-service .
docker run -p 15010:15010 \
  -e DATABASE_URL=postgresql+psycopg://postgres:postgres@host.docker.internal:5432/research_mind \
  research-mind-service
```

### Dockerfile Overview

The Dockerfile uses a multi-stage build:

1. **Builder stage**: Installs Python dependencies into a prefix directory
2. **Runtime stage**: Copies installed packages, application code, and migrations
3. Installs `curl` for health checks
4. Creates a non-root `appuser` for security
5. Verifies `mcp-vector-search` availability (warning only)
6. Configures a HEALTHCHECK that pings `/health`

---

## Database Setup

### PostgreSQL Requirements

- PostgreSQL 15+ recommended
- The `psycopg` (v3) driver is used by default
- Connection string format: `postgresql+psycopg://user:password@host:port/dbname`

### Creating the Database

```bash
# Local PostgreSQL
createdb research_mind

# Remote PostgreSQL
psql "postgresql://admin:password@db-host:5432/postgres" -c "CREATE DATABASE research_mind;"
```

### Running Migrations

```bash
# Apply all migrations
uv run alembic upgrade head

# Check current migration version
uv run alembic current

# View migration history
uv run alembic history
```

### Database Reset (Development Only)

```bash
# Drop and recreate
dropdb research_mind && createdb research_mind
uv run alembic upgrade head
```

---

## Subprocess Timeout Tuning

The service runs `mcp-vector-search` as a subprocess. Timeouts control how long each step is allowed to run.

| Variable | Default | Description |
|---|---|---|
| `SUBPROCESS_TIMEOUT_INIT` | `30` | Timeout for `mcp-vector-search init` |
| `SUBPROCESS_TIMEOUT_INDEX` | `60` | Timeout for `mcp-vector-search index` |
| `SUBPROCESS_TIMEOUT_LARGE` | `600` | Timeout for large workspace operations |

### Tuning Guidelines

- **Small codebases** (< 100 files): Default timeouts are sufficient
- **Medium codebases** (100-1000 files): Consider `SUBPROCESS_TIMEOUT_INDEX=120`
- **Large codebases** (1000+ files): Set `SUBPROCESS_TIMEOUT_INDEX=300` or higher
- **First-time indexing**: The first index takes longer because the embedding model must be downloaded. Set `SUBPROCESS_TIMEOUT_LARGE=600` or higher

The `timeout` field in the `POST /workspaces/{id}/index` request body can override the default per-request (range: 10-600 seconds).

---

## Production Considerations

### Security

1. **Change SECRET_KEY** to a cryptographically random value:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Set SERVICE_ENV=production** to disable auto-table creation

3. **Restrict CORS_ORIGINS** to your production domains:
   ```bash
   CORS_ORIGINS=https://research-mind.io
   ```

4. **Use strong database credentials** and restrict network access

5. **Run as non-root** (the Dockerfile already does this with `appuser`)

### SSL/TLS

The service does not handle TLS directly. Use a reverse proxy:

```
Client --> nginx (TLS termination) --> research-mind-service:15010
```

Example nginx configuration:

```nginx
server {
    listen 443 ssl;
    server_name api.research-mind.io;

    ssl_certificate /etc/ssl/certs/api.research-mind.io.pem;
    ssl_certificate_key /etc/ssl/private/api.research-mind.io.key;

    location / {
        proxy_pass http://localhost:15010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Monitoring

- **Health endpoint**: `GET /health` returns service status
- **Request logging**: All requests are logged with method, path, status, and duration
- **Audit logs**: Query via `GET /api/v1/sessions/{id}/audit`
- **Structured errors**: All errors include machine-readable codes for alerting

### Logging

The service uses Python's standard `logging` module. Configure log level via:

```bash
# In your startup command or environment
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### Backup

Back up the following:

- **PostgreSQL database**: Use `pg_dump` for database backups
- **Workspace files**: The `WORKSPACE_ROOT` directory contains session data and indexes
- **Environment configuration**: Keep `.env` files in a secrets manager

---

## Environment Variables Reference

See the full list in the [README.md Configuration Reference](../README.md#configuration-reference) section and the `.env.example` file.
