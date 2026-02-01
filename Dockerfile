# =============================================================================
# research-mind-service  --  Multi-stage Dockerfile
# =============================================================================
# Build:  docker build -t research-mind-service .
# Run:    docker run -p 15010:15010 research-mind-service

# ---------- Stage 1: Builder ----------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy dependency spec first (layer caching)
COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .

# ---------- Stage 2: Runtime ----------
FROM python:3.12-slim AS runtime

WORKDIR /app

# System dependencies for psycopg and general health
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic.ini ./

# Create workspace directory
RUN mkdir -p /var/lib/research-mind/workspaces

# Verify mcp-vector-search is available
RUN mcp-vector-search --version || echo "WARNING: mcp-vector-search not found"

# Non-root user
RUN useradd --create-home appuser && chown -R appuser:appuser /app /var/lib/research-mind
USER appuser

EXPOSE 15010

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:15010/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "15010"]
