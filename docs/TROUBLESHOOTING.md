# Troubleshooting Guide

Common issues and their solutions when running research-mind-service.

---

## mcp-vector-search: command not found

**Symptom**: Indexing endpoints return HTTP 500 with error code `TOOL_NOT_FOUND`. The service logs show:

```
WARNING: mcp-vector-search CLI not found on PATH. Indexing features will be unavailable.
```

**Cause**: The `mcp-vector-search` CLI tool is not installed or not on the system PATH.

**Solution**:

1. Install `mcp-vector-search` according to its documentation
2. Verify it is accessible:
   ```bash
   mcp-vector-search --version
   ```
3. If installed but not on PATH, add its location to your PATH:
   ```bash
   export PATH="/path/to/mcp-vector-search/bin:$PATH"
   ```
4. For Docker deployments, ensure the Dockerfile installs the tool (check the builder stage)
5. Restart the service after fixing PATH

**Note**: All non-indexing features (sessions, audit logs, health checks) work without `mcp-vector-search`.

---

## Indexing timed out

**Symptom**: Indexing endpoint returns HTTP 500 with error code `INDEXING_TIMEOUT`.

**Cause**: The `mcp-vector-search` subprocess exceeded the configured timeout. Common reasons:

- Large codebase with many files
- First-time indexing (model download adds time)
- Slow disk I/O or low memory

**Solution**:

1. Increase the timeout via environment variable:
   ```bash
   SUBPROCESS_TIMEOUT_INDEX=300  # 5 minutes
   ```

2. Or pass a higher timeout per-request:
   ```bash
   curl -X POST http://localhost:15010/api/v1/workspaces/{id}/index \
     -H "Content-Type: application/json" \
     -d '{"force": true, "timeout": 300}'
   ```

3. For very large codebases (1000+ files), use the large timeout:
   ```bash
   SUBPROCESS_TIMEOUT_LARGE=600  # 10 minutes
   ```

4. Check if the embedding model needs to download first (see "Model download fails" below)

---

## Permission denied on .mcp-vector-search/

**Symptom**: Indexing fails with permission errors related to `.mcp-vector-search/` directory.

**Cause**: The service process does not have write permissions to the workspace directory.

**Solution**:

1. Check workspace directory ownership:
   ```bash
   ls -la /path/to/workspaces/
   ```

2. For local development, ensure the `WORKSPACE_ROOT` directory is writable:
   ```bash
   mkdir -p ./workspaces
   chmod 755 ./workspaces
   ```

3. For Docker deployments, the `appuser` must own the workspace volume:
   ```bash
   # The Dockerfile already sets: chown -R appuser:appuser /var/lib/research-mind
   # If using bind mounts, ensure the host directory is writable
   ```

4. If running as a different user, fix ownership:
   ```bash
   sudo chown -R $(whoami) ./workspaces
   ```

---

## Index corruption

**Symptom**: Indexing or status checks fail with unexpected errors. The `.mcp-vector-search/` directory exists but contains corrupt data.

**Cause**: A previous indexing operation was interrupted (timeout, crash, disk full), leaving the index in an inconsistent state.

**Solution**:

1. Delete the corrupt index directory:
   ```bash
   rm -rf /path/to/workspace/.mcp-vector-search/
   ```

2. Re-index with force:
   ```bash
   curl -X POST http://localhost:15010/api/v1/workspaces/{id}/index \
     -H "Content-Type: application/json" \
     -d '{"force": true}'
   ```

3. If the problem persists, check disk space:
   ```bash
   df -h /path/to/workspaces
   ```

---

## Model download fails

**Symptom**: First-time indexing fails or times out. Logs may show download errors or network timeouts.

**Cause**: The `mcp-vector-search` tool needs to download the embedding model (default: `all-MiniLM-L6-v2`) on first use. This requires internet access and sufficient disk space.

**Solution**:

1. Pre-download the model manually:
   ```bash
   # The model is cached in HF_HOME (default: ~/.cache/huggingface)
   python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
   ```

2. Set a generous timeout for first-time indexing:
   ```bash
   SUBPROCESS_TIMEOUT_INIT=120
   SUBPROCESS_TIMEOUT_INDEX=300
   ```

3. If behind a proxy, configure proxy environment variables:
   ```bash
   HTTP_PROXY=http://proxy:8080
   HTTPS_PROXY=http://proxy:8080
   ```

4. For air-gapped environments, copy the model cache directory:
   ```bash
   # On a machine with internet:
   ls ~/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/

   # Copy to the target machine's HF_HOME location
   ```

---

## Database connection refused

**Symptom**: Service fails to start or returns 500 errors. Logs show:

```
sqlalchemy.exc.OperationalError: connection refused
```

**Cause**: PostgreSQL is not running, wrong connection string, or network issue.

**Solution**:

1. Verify PostgreSQL is running:
   ```bash
   pg_isready -h localhost -p 5432
   ```

2. Check your `DATABASE_URL` in `.env`:
   ```bash
   DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/research_mind
   ```

3. Verify the database exists:
   ```bash
   psql -U postgres -l | grep research_mind
   ```

4. If using Docker Compose, ensure the postgres service is healthy:
   ```bash
   docker compose ps
   docker compose logs postgres
   ```

5. If the database exists but tables are missing, run migrations:
   ```bash
   uv run alembic upgrade head
   ```

6. Common connection string mistakes:
   - Using `psycopg2://` instead of `psycopg://` (this project uses psycopg v3)
   - Wrong port number
   - Missing database name

---

## Port 15010 already in use

**Symptom**: Service fails to start with:

```
ERROR: [Errno 48] Address already in use
```

**Cause**: Another process is already listening on port 15010.

**Solution**:

1. Find the process using the port:
   ```bash
   lsof -i :15010
   ```

2. Stop the conflicting process:
   ```bash
   kill <PID>
   ```

3. Or use a different port:
   ```bash
   PORT=15011 uv run uvicorn app.main:app --host 0.0.0.0 --port 15011
   ```

4. If using Docker, check for conflicting containers:
   ```bash
   docker ps --filter "publish=15010"
   ```

---

## Alembic migration errors

**Symptom**: `alembic upgrade head` fails with schema errors.

**Solution**:

1. Check current migration state:
   ```bash
   uv run alembic current
   ```

2. If the database is out of sync, stamp it to the current state:
   ```bash
   uv run alembic stamp head
   ```

3. For development, reset the database:
   ```bash
   dropdb research_mind && createdb research_mind
   uv run alembic upgrade head
   ```

4. If a migration file is corrupt, check the `migrations/versions/` directory

---

## Session workspace not found

**Symptom**: Operations on a session return `WORKSPACE_NOT_FOUND` even though the session exists in the database.

**Cause**: The workspace directory on disk was deleted or the `WORKSPACE_ROOT` changed.

**Solution**:

1. Check if the workspace directory exists:
   ```bash
   ls -la $WORKSPACE_ROOT/{session_id}/
   ```

2. Verify `WORKSPACE_ROOT` is set correctly in `.env`

3. If the workspace was deleted, delete the session and create a new one

4. For Docker deployments, ensure the workspace volume is mounted correctly

---

## High memory usage during indexing

**Symptom**: The service or `mcp-vector-search` process consumes excessive memory during indexing.

**Cause**: Large codebases generate many embeddings. The embedding model itself requires memory.

**Solution**:

1. Index smaller subsets of code at a time
2. Increase container memory limits if using Docker:
   ```yaml
   service:
     deploy:
       resources:
         limits:
           memory: 4G
   ```
3. Monitor memory usage during indexing:
   ```bash
   watch -n 1 'ps aux --sort=-%mem | head -5'
   ```
