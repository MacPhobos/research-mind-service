# research-mind API Contract

> **Version**: 1.0.0
> **Last Updated**: 2026-01-31
> **Status**: FROZEN - Changes require version bump and UI sync

This document defines the API contract between `research-mind-service` (FastAPI backend) and `research-mind-ui` (SvelteKit frontend).

---

## Table of Contents

1. [Base Configuration](#base-configuration)
2. [Type Generation Strategy](#type-generation-strategy)
3. [Common Types](#common-types)
4. [Health & Version](#health--version)
5. [Sessions](#sessions)
6. [Content Management](#content-management)
7. [Indexing](#indexing)
8. [Search](#search)
9. [Analysis](#analysis)
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

**Workflow**: Backend changes models → Backend tests pass → UI runs `npm run gen:api` → UI updates code → UI tests pass

---

## Common Types

### PaginatedResponse

All list endpoints return paginated responses.

```typescript
interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    limit: number;     // Items per page
    offset: number;    // Starting position (0-indexed)
    total: number;     // Total count of all items
  };
}
```

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

All timestamps are ISO 8601 format (UTC). Example: `2026-01-31T14:30:00Z`

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
  "version": "1.0.0",
  "git_sha": "abc1234def5678"
}
```

---

### API Version

#### `GET /api/v1/version`

Returns current API version information.

**Response** `200 OK`

```json
{
  "name": "research-mind-service",
  "version": "1.0.0",
  "git_sha": "abc1234def5678"
}
```

---

## Sessions

A **Session** is a sandbox environment for research. Each session has:
- A unique ID
- A workspace directory on disk
- A collection in ChromaDB for this session's indexed content
- Audit logs of all operations

### Session Schema

```typescript
interface Session {
  id: string;                    // UUID
  name: string;                  // User-friendly name
  description?: string;          // Optional description
  status: "active" | "archived"; // Current status
  workspace: string;             // Path on disk: /var/lib/research-mind/sessions/{id}
  created_at: string;            // ISO 8601 timestamp
  updated_at: string;            // ISO 8601 timestamp
  indexed_count: number;         // Number of indexed documents in this session
  last_indexed_at?: string;      // ISO 8601 timestamp of last indexing job
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

**Response** `201 Created`

```json
{
  "id": "sess_abc123def456",
  "name": "OAuth2 Auth Module Research",
  "description": "Understanding token refresh and scope management",
  "status": "active",
  "workspace": "/var/lib/research-mind/sessions/sess_abc123def456",
  "created_at": "2026-01-31T14:30:00Z",
  "updated_at": "2026-01-31T14:30:00Z",
  "indexed_count": 0,
  "last_indexed_at": null
}
```

---

### List Sessions

#### `GET /api/v1/sessions`

List all research sessions with pagination.

**Query Parameters**

| Parameter  | Type    | Default | Description         |
| ---------- | ------- | ------- | ------------------- |
| `limit`    | integer | 10      | Items per page (max: 100) |
| `offset`   | integer | 0       | Starting position   |

**Response** `200 OK` - `PaginatedResponse<Session>`

```json
{
  "data": [
    {
      "id": "sess_abc123def456",
      "name": "OAuth2 Auth Module Research",
      "description": "Understanding token refresh and scope management",
      "status": "active",
      "workspace": "/var/lib/research-mind/sessions/sess_abc123def456",
      "created_at": "2026-01-31T14:30:00Z",
      "updated_at": "2026-01-31T14:30:00Z",
      "indexed_count": 42,
      "last_indexed_at": "2026-01-31T14:45:30Z"
    }
  ],
  "pagination": {
    "limit": 10,
    "offset": 0,
    "total": 1
  }
}
```

---

### Get Session

#### `GET /api/v1/sessions/{session_id}`

Get details of a specific session.

**Path Parameters**

| Parameter   | Type   | Description         |
| ----------- | ------ | ------------------- |
| `session_id` | string | Session UUID        |

**Response** `200 OK` - Session object

**Response** `404 Not Found`

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session 'sess_unknown' not found"
  }
}
```

---

### Update Session

#### `PATCH /api/v1/sessions/{session_id}`

Update session metadata (name, description, status).

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |

**Request Body** (all fields optional)

```json
{
  "name": "Updated Session Name",
  "description": "Updated description",
  "status": "archived"
}
```

**Response** `200 OK` - Updated Session object

---

### Delete Session

#### `DELETE /api/v1/sessions/{session_id}`

Delete a session and all associated data (workspace files and ChromaDB collection).

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |

**Response** `204 No Content`

**Response** `404 Not Found`

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session 'sess_unknown' not found"
  }
}
```

---

## Content Management

### Add Content to Session

#### `POST /api/v1/sessions/{session_id}/add-content`

Copy source files/directories into the session workspace. This prepares content for indexing.

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |

**Request Body**

```json
{
  "repository_path": "/path/to/codebase"
}
```

The service will:
1. Validate the source path exists
2. Copy files to `{session.workspace}/content`
3. Exclude common patterns (.git, node_modules, __pycache__, etc.)

**Response** `200 OK`

```json
{
  "session_id": "sess_abc123def456",
  "files_copied": 142,
  "bytes_copied": 2458123,
  "excluded": [".git", "node_modules", "__pycache__"],
  "workspace_path": "/var/lib/research-mind/sessions/sess_abc123def456/content"
}
```

**Response** `400 Bad Request`

```json
{
  "error": {
    "code": "INVALID_PATH",
    "message": "Source path does not exist: /path/to/nonexistent"
  }
}
```

---

## Indexing

Indexing is **asynchronous**. Clients must poll for job status.

### IndexingJob Schema

```typescript
interface IndexingJob {
  id: string;                         // UUID (job_abc123)
  session_id: string;                 // Parent session UUID
  status: "pending" | "running" | "completed" | "failed"; // Current status
  started_at?: string;                // ISO 8601 timestamp
  completed_at?: string;              // ISO 8601 timestamp
  error?: string;                     // Error message if failed
  documents_indexed: number;          // Count of documents indexed
  chunks_created: number;             // Count of chunks created
  progress_percent: number;           // 0-100
}
```

### Start Indexing

#### `POST /api/v1/sessions/{session_id}/index`

Start an async indexing job for the session's content.

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |

**Request Body** (optional)

```json
{
  "force": false
}
```

- `force`: If true, reindex all content even if previously indexed. Default: false.

**Response** `202 Accepted`

```json
{
  "id": "job_xyz789abc123",
  "session_id": "sess_abc123def456",
  "status": "pending",
  "started_at": null,
  "completed_at": null,
  "documents_indexed": 0,
  "chunks_created": 0,
  "progress_percent": 0
}
```

---

### Get Indexing Job Status

#### `GET /api/v1/sessions/{session_id}/index/jobs/{job_id}`

Poll the status of an indexing job.

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |
| `job_id`    | string | Job UUID    |

**Response** `200 OK` - IndexingJob object

Example of a running job:

```json
{
  "id": "job_xyz789abc123",
  "session_id": "sess_abc123def456",
  "status": "running",
  "started_at": "2026-01-31T14:31:00Z",
  "completed_at": null,
  "documents_indexed": 45,
  "chunks_created": 312,
  "progress_percent": 32
}
```

Example of a completed job:

```json
{
  "id": "job_xyz789abc123",
  "session_id": "sess_abc123def456",
  "status": "completed",
  "started_at": "2026-01-31T14:31:00Z",
  "completed_at": "2026-01-31T14:45:30Z",
  "documents_indexed": 142,
  "chunks_created": 987,
  "progress_percent": 100
}
```

Example of a failed job:

```json
{
  "id": "job_xyz789abc123",
  "session_id": "sess_abc123def456",
  "status": "failed",
  "started_at": "2026-01-31T14:31:00Z",
  "completed_at": "2026-01-31T14:35:00Z",
  "error": "Out of memory while processing large file: src/data/huge.bin",
  "documents_indexed": 45,
  "chunks_created": 312,
  "progress_percent": 32
}
```

**Response** `404 Not Found`

```json
{
  "error": {
    "code": "JOB_NOT_FOUND",
    "message": "Indexing job 'job_unknown' not found"
  }
}
```

---

## Search

### SearchResult Schema

```typescript
interface SearchResult {
  file: string;                  // Relative path in session: "src/auth/oauth2.py"
  line_start: number;            // Starting line number (1-indexed)
  line_end: number;              // Ending line number
  code: string;                  // The actual code snippet
  relevance_score: number;       // 0.0 - 1.0
}
```

### Vector Search

#### `POST /api/v1/sessions/{session_id}/search`

Search the indexed content using vector similarity.

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |

**Request Body**

```json
{
  "query": "How does token refresh work?",
  "top_k": 10
}
```

| Field | Type    | Default | Description                |
| ----- | ------- | ------- | -------------------------- |
| `query` | string | required | Natural language search query |
| `top_k` | integer | 10      | Number of results (max: 50) |

**Response** `200 OK`

```json
{
  "query": "How does token refresh work?",
  "results": [
    {
      "file": "src/auth/oauth2.py",
      "line_start": 42,
      "line_end": 67,
      "code": "def refresh_token(old_token: str) -> str:\n    \"\"\"Refresh an expired OAuth2 token.\"\"\"\n    ...",
      "relevance_score": 0.94
    },
    {
      "file": "src/auth/schemas.py",
      "line_start": 12,
      "line_end": 18,
      "code": "class TokenRefreshRequest(BaseModel):\n    old_token: str\n    client_id: str",
      "relevance_score": 0.87
    }
  ],
  "count": 2
}
```

**Response** `404 Not Found` (session not found)

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session 'sess_unknown' not found"
  }
}
```

**Response** `400 Bad Request` (session not indexed yet)

```json
{
  "error": {
    "code": "SESSION_NOT_INDEXED",
    "message": "Session has no indexed content. Please run indexing first."
  }
}
```

---

## Analysis

### AnalysisResult Schema

```typescript
interface AnalysisResult {
  session_id: string;             // Parent session UUID
  question: string;               // Original question
  agent: string;                  // Agent name used ("research-analyst")
  answer: string;                 // LLM-generated synthesis
  evidence: EvidenceItem[];        // Supporting code snippets and citations
  generated_at: string;           // ISO 8601 timestamp
}

interface EvidenceItem {
  source: string;                 // "src/auth/oauth2.py:42-67"
  code: string;                   // Code snippet
  confidence: number;             // 0.0 - 1.0
}
```

### Analyze Session

#### `POST /api/v1/sessions/{session_id}/analyze`

Invoke an agent to synthesize an answer based on the session's indexed content and search results.

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |

**Request Body**

```json
{
  "question": "How does token refresh work?",
  "agent": "research-analyst"
}
```

| Field     | Type   | Default | Description                      |
| --------- | ------ | ------- | -------------------------------- |
| `question` | string | required | Research question to answer     |
| `agent`    | string | "research-analyst" | Agent to use for synthesis |

The service will:
1. Search indexed content for relevant code
2. Pass search results to the specified agent
3. Agent synthesizes answer with citations
4. Return comprehensive analysis

**Response** `200 OK`

```json
{
  "session_id": "sess_abc123def456",
  "question": "How does token refresh work?",
  "agent": "research-analyst",
  "answer": "Token refresh is implemented in src/auth/oauth2.py. The refresh_token() function takes an expired token, validates it against the refresh token in the database, and returns a new access token...",
  "evidence": [
    {
      "source": "src/auth/oauth2.py:42-67",
      "code": "def refresh_token(old_token: str) -> str:\n    \"\"\"Refresh an expired OAuth2 token.\"\"\"\n    ...",
      "confidence": 0.94
    },
    {
      "source": "src/auth/schemas.py:12-18",
      "code": "class TokenRefreshRequest(BaseModel):\n    old_token: str\n    client_id: str",
      "confidence": 0.87
    }
  ],
  "generated_at": "2026-01-31T14:50:15Z"
}
```

**Response** `400 Bad Request` (session not indexed)

```json
{
  "error": {
    "code": "SESSION_NOT_INDEXED",
    "message": "Session has no indexed content. Please run indexing first."
  }
}
```

**Response** `404 Not Found`

```json
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session 'sess_unknown' not found"
  }
}
```

**Response** `400 Bad Request` (unknown agent)

```json
{
  "error": {
    "code": "AGENT_NOT_FOUND",
    "message": "Agent 'unknown-agent' is not available"
  }
}
```

---

## Pagination

High-volume list endpoints use consistent pagination.

### Request Parameters

| Parameter | Type    | Default | Max | Description              |
| --------- | ------- | ------- | --- | ------------------------ |
| `limit`   | integer | 10      | 100 | Items per page           |
| `offset`  | integer | 0       | -   | Starting position (0-indexed) |

### Edge Cases

- `offset` + `limit` > `total`: Returns remaining items, valid pagination meta
- `offset` > `total`: Returns empty `data` array, valid pagination meta
- `limit` > 100: Clamped to 100
- Negative values: Treated as defaults

---

## Error Handling

### Error Response Shape

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description",
    "details": { }
  }
}
```

### Standard Error Codes

| Code                  | HTTP Status | Description                    |
| --------------------- | ----------- | ------------------------------ |
| `VALIDATION_ERROR`    | 400         | Invalid request parameters     |
| `SESSION_NOT_FOUND`   | 404         | Session UUID not found         |
| `SESSION_NOT_INDEXED` | 400         | Session has no indexed content |
| `JOB_NOT_FOUND`       | 404         | Indexing job not found         |
| `INVALID_PATH`        | 400         | Source path does not exist     |
| `AGENT_NOT_FOUND`     | 404         | Agent not available            |
| `RATE_LIMITED`        | 429         | Too many requests              |
| `INTERNAL_ERROR`      | 500         | Unexpected server error        |

---

## Status Codes

| Code | Meaning                    | Usage                        |
| ---- | -------------------------- | ---------------------------- |
| `200` | OK                        | Successful GET, PATCH        |
| `201` | Created                   | Successful POST (resource creation) |
| `202` | Accepted                  | Async job queued (indexing)  |
| `204` | No Content                | Successful DELETE            |
| `400` | Bad Request               | Validation error, missing content |
| `404` | Not Found                 | Resource not found           |
| `409` | Conflict                  | State conflict               |
| `429` | Too Many Requests         | Rate limited (future)        |
| `500` | Internal Server Error     | Unexpected error             |

---

## CORS Configuration

### Development

```
Origins: http://localhost:15000
Credentials: Allowed
Methods: GET, POST, PATCH, DELETE, OPTIONS
Headers: Content-Type, Accept
```

### Production

Configure via environment variable: `CORS_ORIGINS`

Example:
```
CORS_ORIGINS=https://research-mind.io,https://api.research-mind.io
```

---

## Authentication

**Current Status**: Not implemented (stubs exist in `app/auth/`)

**Future Implementation**: JWT token-based authentication planned for production.

All endpoints are currently open. Authentication will be added in a future version with proper:
- Token validation
- Role-based access control (RBAC)
- Session-level permissions
- Audit logging of all operations

---

## Changelog

| Version | Date       | Changes                                    |
| ------- | ---------- | ------------------------------------------ |
| 1.0.0   | 2026-01-31 | Initial contract: Sessions, indexing, search, analysis |

---

_This contract is the source of truth. Service and UI implementations must conform to these definitions. Changes to this contract require version bump and synchronization with `research-mind-ui/docs/api-contract.md`._
