# research-mind API Contract

> **Version**: 1.1.0
> **Last Updated**: 2026-02-01
> **Status**: FROZEN - Changes require version bump and UI sync

This document defines the API contract between `research-mind-service` (FastAPI backend) and `research-mind-ui` (SvelteKit frontend).

---

## Table of Contents

1. [Base Configuration](#base-configuration)
2. [Type Generation Strategy](#type-generation-strategy)
3. [Common Types](#common-types)
4. [Health & Version](#health--version)
5. [Sessions](#sessions)
6. [Workspace Indexing](#workspace-indexing)
7. [Audit Logs](#audit-logs)
8. [Search (Planned)](#search-planned)
9. [Analysis (Planned)](#analysis-planned)
10. [Pagination](#pagination)
11. [Error Handling](#error-handling)
12. [Status Codes](#status-codes)
13. [CORS Configuration](#cors-configuration)
14. [Authentication](#authentication)

---

## Base Configuration

| Environment | Base URL            |
| ----------- | ------------------- |
| Development | `http://localhost:15010` |
| Production  | `https://api.research-mind.io` (TBD) |

All endpoints are prefixed with `/api/v1` except `/health` and `/openapi.json`.

---

## Type Generation Strategy

**This strategy is LOCKED. Do not deviate.**

### Backend (Python FastAPI)

- OpenAPI spec auto-generated at `/openapi.json`
- All response models defined with Pydantic models in `app/schemas/`
- All models properly typed with docstrings

### Frontend (SvelteKit + TypeScript)

- Generated types at `src/lib/api/generated.ts`
- Generation script: `npm run gen:api`
- Script calls: `openapi-typescript http://localhost:15010/openapi.json -o src/lib/api/generated.ts`

**Workflow**: Backend changes models -> Backend tests pass -> UI runs `npm run gen:api` -> UI updates code -> UI tests pass

---

## Common Types

### ErrorResponse

All errors follow this shape.

```typescript
interface ErrorResponse {
  error: {
    code: string;       // Machine-readable error code
    message: string;    // Human-readable error message
    details?: unknown;  // Optional additional context
  };
}
```

### Timestamp Format

All timestamps are ISO 8601 format (UTC). Example: `2026-02-01T14:30:00Z`

---

## Health & Version

### Health Check

#### `GET /health`

Health check endpoint. No authentication required. No `/api/v1` prefix.

**Response** `200 OK`

```json
{
  "status": "ok",
  "name": "research-mind-service",
  "version": "0.1.0",
  "git_sha": "abc1234"
}
```

**curl**:
```bash
curl http://localhost:15010/health
```

---

### API Health Check

#### `GET /api/v1/health`

Health check under the API prefix. Returns environment info.

**Response** `200 OK`

```json
{
  "status": "ok",
  "name": "research-mind-service",
  "version": "0.1.0",
  "environment": "development"
}
```

**curl**:
```bash
curl http://localhost:15010/api/v1/health
```

---

### API Version

#### `GET /api/v1/version`

Returns current API version information.

**Response** `200 OK`

```json
{
  "name": "research-mind-service",
  "version": "0.1.0",
  "git_sha": "abc1234"
}
```

**curl**:
```bash
curl http://localhost:15010/api/v1/version
```

---

## Sessions

A **Session** is a sandbox environment for research. Each session has:
- A unique ID (UUID)
- A workspace directory on disk
- Audit logs of all operations

### Session Schema

```typescript
interface Session {
  session_id: string;             // UUID
  name: string;                   // User-friendly name (1-255 chars)
  description?: string;           // Optional description (max 1024 chars)
  workspace_path: string;         // Path on disk
  created_at: string;             // ISO 8601 timestamp
  last_accessed: string;          // ISO 8601 timestamp
  status: string;                 // "active" or "archived"
  archived: boolean;              // Whether session is archived
  ttl_seconds?: number;           // Time-to-live (null if no expiry)
  is_indexed: boolean;            // Whether workspace has been indexed
}
```

### Create Session

#### `POST /api/v1/sessions`

Create a new research session.

**Request Body**

```json
{
  "name": "OAuth2 Auth Module Research",
  "description": "Understanding token refresh and scope management"
}
```

| Field | Type | Required | Constraints |
|---|---|---|---|
| `name` | string | yes | 1-255 characters |
| `description` | string | no | max 1024 characters |

**Response** `201 Created`

```json
{
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "OAuth2 Auth Module Research",
  "description": "Understanding token refresh and scope management",
  "workspace_path": "./workspaces/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "created_at": "2026-02-01T14:30:00",
  "last_accessed": "2026-02-01T14:30:00",
  "status": "active",
  "archived": false,
  "ttl_seconds": null,
  "is_indexed": false
}
```

**curl**:
```bash
curl -X POST http://localhost:15010/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"name": "OAuth2 Research", "description": "Token refresh patterns"}'
```

---

### List Sessions

#### `GET /api/v1/sessions`

List all research sessions with pagination.

**Query Parameters**

| Parameter  | Type    | Default | Description         |
| ---------- | ------- | ------- | ------------------- |
| `limit`    | integer | 20      | Items per page      |
| `offset`   | integer | 0       | Starting position   |

**Response** `200 OK`

```json
{
  "sessions": [
    {
      "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "name": "OAuth2 Auth Module Research",
      "description": "Understanding token refresh and scope management",
      "workspace_path": "./workspaces/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "created_at": "2026-02-01T14:30:00",
      "last_accessed": "2026-02-01T14:30:00",
      "status": "active",
      "archived": false,
      "ttl_seconds": null,
      "is_indexed": true
    }
  ],
  "count": 1
}
```

**curl**:
```bash
curl "http://localhost:15010/api/v1/sessions?limit=20&offset=0"
```

---

### Get Session

#### `GET /api/v1/sessions/{session_id}`

Get details of a specific session.

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |

**Response** `200 OK` - Session object

**Response** `404 Not Found`

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

**curl**:
```bash
curl http://localhost:15010/api/v1/sessions/{session_id}
```

---

### Delete Session

#### `DELETE /api/v1/sessions/{session_id}`

Delete a session and its workspace directory.

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |

**Response** `204 No Content`

**Response** `404 Not Found`

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

**curl**:
```bash
curl -X DELETE http://localhost:15010/api/v1/sessions/{session_id}
```

---

## Workspace Indexing

Indexing uses `mcp-vector-search` as an external CLI tool via subprocess. The session's `session_id` is used as the `workspace_id`.

### Index Workspace

#### `POST /api/v1/workspaces/{workspace_id}/index`

Trigger indexing for a workspace. Runs `mcp-vector-search init --force` followed by `mcp-vector-search index --force` synchronously.

**Path Parameters**

| Parameter      | Type   | Description |
| -------------- | ------ | ----------- |
| `workspace_id` | string | Session UUID (used as workspace identifier) |

**Request Body** (optional)

```json
{
  "force": true,
  "timeout": 120
}
```

| Field | Type | Default | Constraints | Description |
|---|---|---|---|---|
| `force` | boolean | `true` | - | Re-index from scratch |
| `timeout` | integer | null | 10-600 | Custom timeout in seconds |

**Response** `200 OK`

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

**Response** `404 Not Found` - Session not found

**Response** `500 Internal Server Error` - Tool not found or timeout

```json
{
  "detail": {
    "error": {
      "code": "TOOL_NOT_FOUND",
      "message": "mcp-vector-search CLI is not available on PATH"
    }
  }
}
```

```json
{
  "detail": {
    "error": {
      "code": "INDEXING_TIMEOUT",
      "message": "Indexing operation timed out"
    }
  }
}
```

**curl**:
```bash
curl -X POST http://localhost:15010/api/v1/workspaces/{session_id}/index \
  -H "Content-Type: application/json" \
  -d '{"force": true, "timeout": 120}'
```

---

### Get Index Status

#### `GET /api/v1/workspaces/{workspace_id}/index/status`

Check the indexing status of a workspace.

**Path Parameters**

| Parameter      | Type   | Description |
| -------------- | ------ | ----------- |
| `workspace_id` | string | Session UUID |

**Response** `200 OK`

```json
{
  "workspace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "is_indexed": true,
  "status": "indexed",
  "message": "Workspace has been indexed"
}
```

Not indexed:

```json
{
  "workspace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "is_indexed": false,
  "status": "not_indexed",
  "message": "Workspace has not been indexed yet"
}
```

**Response** `404 Not Found` - Session not found

**curl**:
```bash
curl http://localhost:15010/api/v1/workspaces/{session_id}/index/status
```

---

## Audit Logs

### Audit Log Schema

```typescript
interface AuditLog {
  id: number;                     // Auto-increment ID
  timestamp: string;              // ISO 8601 timestamp
  session_id: string;             // Parent session UUID
  action: string;                 // Action type (e.g., "session_created", "index_started")
  query?: string;                 // Search query (for search actions)
  result_count?: number;          // Number of results returned
  duration_ms?: number;           // Operation duration in milliseconds
  status: string;                 // "success" or "error"
  error?: string;                 // Error message if failed
  metadata_json?: object;         // Additional metadata
}
```

### Get Audit Logs

#### `GET /api/v1/sessions/{session_id}/audit`

Retrieve audit logs for a session.

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |

**Query Parameters**

| Parameter | Type    | Default | Description         |
| --------- | ------- | ------- | ------------------- |
| `limit`   | integer | 50      | Items per page      |
| `offset`  | integer | 0       | Starting position   |

**Response** `200 OK`

```json
{
  "logs": [
    {
      "id": 1,
      "timestamp": "2026-02-01T14:30:00",
      "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "action": "session_created",
      "query": null,
      "result_count": null,
      "duration_ms": 15,
      "status": "success",
      "error": null,
      "metadata_json": null
    }
  ],
  "count": 1
}
```

**Response** `404 Not Found` - Session not found

**curl**:
```bash
curl "http://localhost:15010/api/v1/sessions/{session_id}/audit?limit=50&offset=0"
```

---

## Search (Planned)

> **Status**: Not yet implemented. Planned for a future phase.

Search will use `mcp-vector-search` to perform natural language queries over indexed workspaces.

### Planned: Vector Search

#### `POST /api/v1/sessions/{session_id}/search`

**Request Body** (planned):
```json
{
  "query": "How does token refresh work?",
  "top_k": 10
}
```

---

## Analysis (Planned)

> **Status**: Not yet implemented. Planned for a future phase.

Analysis will invoke an AI agent to synthesize answers from indexed code with evidence citations.

### Planned: Analyze Session

#### `POST /api/v1/sessions/{session_id}/analyze`

**Request Body** (planned):
```json
{
  "question": "How does token refresh work?",
  "agent": "research-analyst"
}
```

---

## Pagination

List endpoints use consistent pagination via query parameters.

### Request Parameters

| Parameter | Type    | Default | Description              |
| --------- | ------- | ------- | ------------------------ |
| `limit`   | integer | varies  | Items per page           |
| `offset`  | integer | 0       | Starting position (0-indexed) |

### Edge Cases

- `offset` + `limit` > `total`: Returns remaining items, valid count
- `offset` > `total`: Returns empty list, valid count
- Negative values: Treated as defaults

---

## Error Handling

### Error Response Shape

Errors are returned inside `detail` (FastAPI HTTPException format):

```json
{
  "detail": {
    "error": {
      "code": "ERROR_CODE",
      "message": "Human-readable description"
    }
  }
}
```

### Standard Error Codes

| Code                  | HTTP Status | Description                    |
| --------------------- | ----------- | ------------------------------ |
| `VALIDATION_ERROR`    | 400         | Invalid request parameters     |
| `SESSION_NOT_FOUND`   | 404         | Session UUID not found         |
| `WORKSPACE_NOT_FOUND` | 404         | Workspace directory not found  |
| `TOOL_NOT_FOUND`      | 500         | mcp-vector-search CLI missing  |
| `INDEXING_TIMEOUT`    | 500         | Indexing subprocess timed out  |
| `INTERNAL_ERROR`      | 500         | Unexpected server error        |

---

## Status Codes

| Code | Meaning                    | Usage                        |
| ---- | -------------------------- | ---------------------------- |
| `200` | OK                        | Successful GET, POST (indexing) |
| `201` | Created                   | Successful POST (session creation) |
| `204` | No Content                | Successful DELETE            |
| `400` | Bad Request               | Validation error             |
| `404` | Not Found                 | Resource not found           |
| `500` | Internal Server Error     | Tool not found, timeout, unexpected error |

---

## CORS Configuration

### Development

```
Origins: http://localhost:15000, http://localhost:3000
Credentials: Allowed
Methods: GET, POST, PATCH, DELETE, OPTIONS
Headers: *
```

### Production

Configure via environment variable: `CORS_ORIGINS`

```
CORS_ORIGINS=https://research-mind.io
```

---

## Authentication

**Current Status**: Not implemented (stubs exist in `app/auth/`)

**Future Implementation**: JWT token-based authentication planned for production.

All endpoints are currently open. Authentication will be added in a future version with:
- Token validation middleware
- Role-based access control (RBAC)
- Session-level permissions

---

## Changelog

| Version | Date       | Changes                                    |
| ------- | ---------- | ------------------------------------------ |
| 1.0.0   | 2026-01-31 | Initial contract: Sessions, indexing (planned), search, analysis |
| 1.1.0   | 2026-02-01 | Updated to match implemented endpoints: workspace indexing (subprocess-based), audit logs, index status. Marked search/analysis as planned. |

---

_This contract is the source of truth. Service and UI implementations must conform to these definitions. Changes to this contract require version bump and synchronization with `research-mind-ui/docs/api-contract.md`._
