# research-mind API Contract

> **Version**: 1.5.0
> **Last Updated**: 2026-02-03
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
7. [Workspace Indexing](#workspace-indexing)
8. [Chat](#chat)
9. [Audit Logs](#audit-logs)
10. [Search (Planned)](#search-planned)
11. [Analysis (Planned)](#analysis-planned)
12. [Pagination](#pagination)
13. [Error Handling](#error-handling)
14. [Status Codes](#status-codes)
15. [CORS Configuration](#cors-configuration)
16. [Authentication](#authentication)

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
  content_count: number;          // Number of content items in session
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
  "is_indexed": false,
  "content_count": 0
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
      "is_indexed": true,
      "content_count": 5
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

## Content Management

Content items are pieces of data (text, files, URLs, git repos) added to a session for analysis. Each content item is stored in a sandboxed directory and tracked in the database.

### Content Types

| Type | Description |
|------|-------------|
| `text` | Plain text content (source contains the text) |
| `file_upload` | Uploaded file (use multipart form) |
| `url` | Fetch content from URL (source contains the URL) |
| `git_repo` | Clone a git repository (source contains the repo URL) |
| `mcp_source` | Content from MCP tool (source contains MCP reference) |

### Content Status

| Status | Description |
|--------|-------------|
| `pending` | Content item created, retrieval not started |
| `processing` | Content is being fetched/processed |
| `ready` | Content successfully retrieved and stored |
| `error` | Retrieval failed, see `error_message` |

### Content Item Schema

```typescript
interface ContentItem {
  content_id: string;           // UUID
  session_id: string;           // Parent session UUID
  content_type: string;         // "text" | "file_upload" | "url" | "git_repo" | "mcp_source"
  title: string;                // Display name (max 512 chars)
  source_ref?: string;          // Original source reference (max 2048 chars)
  storage_path?: string;        // Path where content is stored
  status: string;               // "pending" | "processing" | "ready" | "error"
  error_message?: string;       // Error details if status is "error"
  size_bytes?: number;          // Size of stored content
  mime_type?: string;           // MIME type of content
  metadata_json?: object;       // Additional metadata
  created_at: string;           // ISO 8601 timestamp
  updated_at: string;           // ISO 8601 timestamp
}
```

### Add Content

#### `POST /api/v1/sessions/{session_id}/content`

Add content to a session. Uses multipart/form-data to support file uploads.

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |

**Form Fields**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content_type` | string | yes | Content type: text, file_upload, url, git_repo, mcp_source |
| `title` | string | no | Content title (max 512 chars) |
| `source` | string | no | Source reference - text content, URL, or repo URL (max 2048 chars) |
| `metadata` | string | no | JSON string of additional metadata |
| `file` | file | no | File to upload (required for file_upload type) |

**Response** `201 Created`

```json
{
  "content_id": "b1c2d3e4-f5g6-7890-hijk-lm1234567890",
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "content_type": "text",
  "title": "API Design Notes",
  "source_ref": "REST API design principles...",
  "storage_path": "content.txt",
  "status": "ready",
  "error_message": null,
  "size_bytes": 1234,
  "mime_type": "text/plain",
  "metadata_json": {},
  "created_at": "2026-02-03T10:30:00",
  "updated_at": "2026-02-03T10:30:00"
}
```

**Response** `400 Bad Request` - Invalid metadata JSON

```json
{
  "detail": {
    "error": {
      "code": "INVALID_METADATA",
      "message": "metadata must be valid JSON"
    }
  }
}
```

**Response** `404 Not Found` - Session not found

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

**curl** (text content):
```bash
curl -X POST http://localhost:15010/api/v1/sessions/{session_id}/content \
  -F "content_type=text" \
  -F "title=API Notes" \
  -F "source=REST API design principles and best practices..."
```

**curl** (file upload):
```bash
curl -X POST http://localhost:15010/api/v1/sessions/{session_id}/content \
  -F "content_type=file_upload" \
  -F "title=Research Paper" \
  -F "file=@/path/to/document.pdf"
```

**curl** (URL):
```bash
curl -X POST http://localhost:15010/api/v1/sessions/{session_id}/content \
  -F "content_type=url" \
  -F "title=Reference Article" \
  -F "source=https://example.com/article.html"
```

---

### List Content

#### `GET /api/v1/sessions/{session_id}/content`

List all content items for a session with pagination.

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |

**Query Parameters**

| Parameter | Type    | Default | Description |
| --------- | ------- | ------- | ----------- |
| `limit`   | integer | 50      | Items per page |
| `offset`  | integer | 0       | Starting position |

**Response** `200 OK`

```json
{
  "items": [
    {
      "content_id": "b1c2d3e4-f5g6-7890-hijk-lm1234567890",
      "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "content_type": "text",
      "title": "API Design Notes",
      "source_ref": "REST API design principles...",
      "storage_path": "content.txt",
      "status": "ready",
      "error_message": null,
      "size_bytes": 1234,
      "mime_type": "text/plain",
      "metadata_json": {},
      "created_at": "2026-02-03T10:30:00",
      "updated_at": "2026-02-03T10:30:00"
    }
  ],
  "count": 1
}
```

**Response** `404 Not Found` - Session not found

**curl**:
```bash
curl "http://localhost:15010/api/v1/sessions/{session_id}/content?limit=50&offset=0"
```

---

### Get Content

#### `GET /api/v1/sessions/{session_id}/content/{content_id}`

Get a single content item by ID.

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |
| `content_id` | string | Content UUID |

**Response** `200 OK` - ContentItem object

**Response** `404 Not Found` - Content not found

```json
{
  "detail": {
    "error": {
      "code": "CONTENT_NOT_FOUND",
      "message": "Content 'content-id' not found in session 'session-id'"
    }
  }
}
```

**curl**:
```bash
curl http://localhost:15010/api/v1/sessions/{session_id}/content/{content_id}
```

---

### Delete Content

#### `DELETE /api/v1/sessions/{session_id}/content/{content_id}`

Delete a content item and its storage files.

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |
| `content_id` | string | Content UUID |

**Response** `204 No Content`

**Response** `404 Not Found` - Content not found

```json
{
  "detail": {
    "error": {
      "code": "CONTENT_NOT_FOUND",
      "message": "Content 'content-id' not found in session 'session-id'"
    }
  }
}
```

**curl**:
```bash
curl -X DELETE http://localhost:15010/api/v1/sessions/{session_id}/content/{content_id}
```

---

### Content Cascade Behavior

When a session is deleted:
- All associated content items are automatically deleted (CASCADE)
- Content storage directories are cleaned up from disk

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

## Chat

Chat messages allow users to query session content using AI. Each session maintains its own chat history.

### Chat Message Schema

```typescript
interface ChatMessage {
  message_id: string;           // UUID
  session_id: string;           // Parent session UUID
  role: "user" | "assistant";   // Message author
  content: string;              // Message content
  status: "pending" | "streaming" | "completed" | "error";
  error_message?: string;       // Error details if status is "error"
  created_at: string;           // ISO 8601 timestamp
  completed_at?: string;        // ISO 8601 timestamp (when response finished)
  token_count?: number;         // Approximate token count
  duration_ms?: number;         // Response generation time
  metadata_json?: object;       // Additional metadata (model, etc.)
}
```

### Send Chat Message

#### `POST /api/v1/sessions/{session_id}/chat`

Send a new chat message and get a stream URL for the response.

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |

**Request Body**

```json
{
  "content": "What authentication patterns are used in this codebase?"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `content` | string | yes | 1-10000 characters |

**Response** `201 Created`

```json
{
  "message_id": "c1d2e3f4-g5h6-7890-ijkl-mn1234567890",
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "role": "user",
  "content": "What authentication patterns are used in this codebase?",
  "status": "pending",
  "created_at": "2026-02-03T10:30:00Z",
  "stream_url": "/api/v1/sessions/a1b2c3d4.../chat/stream/c1d2e3f4..."
}
```

**Response** `404 Not Found` - Session not found

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

**Response** `400 Bad Request` - Session not indexed

```json
{
  "detail": {
    "error": {
      "code": "SESSION_NOT_INDEXED",
      "message": "Session must be indexed before chat is available"
    }
  }
}
```

**curl**:
```bash
curl -X POST http://localhost:15010/api/v1/sessions/{session_id}/chat \
  -H "Content-Type: application/json" \
  -d '{"content": "What authentication patterns are used?"}'
```

---

### List Chat Messages

#### `GET /api/v1/sessions/{session_id}/chat`

List all chat messages for a session with pagination.

**Path Parameters**

| Parameter   | Type   | Description |
| ----------- | ------ | ----------- |
| `session_id` | string | Session UUID |

**Query Parameters**

| Parameter | Type    | Default | Description |
| --------- | ------- | ------- | ----------- |
| `limit`   | integer | 50      | Items per page |
| `offset`  | integer | 0       | Starting position |

**Response** `200 OK`

```json
{
  "messages": [
    {
      "message_id": "c1d2e3f4-g5h6-7890-ijkl-mn1234567890",
      "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "role": "user",
      "content": "What patterns are used?",
      "status": "completed",
      "created_at": "2026-02-03T10:30:00Z"
    },
    {
      "message_id": "d2e3f4g5-h6i7-8901-jklm-no2345678901",
      "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "role": "assistant",
      "content": "Based on my analysis, the codebase uses...",
      "status": "completed",
      "created_at": "2026-02-03T10:30:05Z",
      "completed_at": "2026-02-03T10:30:12Z",
      "token_count": 542,
      "duration_ms": 7000
    }
  ],
  "count": 2
}
```

**Response** `404 Not Found` - Session not found

**curl**:
```bash
curl "http://localhost:15010/api/v1/sessions/{session_id}/chat?limit=50&offset=0"
```

---

### Get Chat Message

#### `GET /api/v1/sessions/{session_id}/chat/{message_id}`

Get a single chat message by ID.

**Path Parameters**

| Parameter    | Type   | Description |
| ------------ | ------ | ----------- |
| `session_id` | string | Session UUID |
| `message_id` | string | Message UUID |

**Response** `200 OK` - ChatMessage object

**Response** `404 Not Found` - Message not found

```json
{
  "detail": {
    "error": {
      "code": "CHAT_MESSAGE_NOT_FOUND",
      "message": "Chat message 'message-id' not found in session 'session-id'"
    }
  }
}
```

**curl**:
```bash
curl http://localhost:15010/api/v1/sessions/{session_id}/chat/{message_id}
```

---

### Delete Chat Message

#### `DELETE /api/v1/sessions/{session_id}/chat/{message_id}`

Delete a chat message.

**Path Parameters**

| Parameter    | Type   | Description |
| ------------ | ------ | ----------- |
| `session_id` | string | Session UUID |
| `message_id` | string | Message UUID |

**Response** `204 No Content`

**Response** `404 Not Found` - Message not found

```json
{
  "detail": {
    "error": {
      "code": "CHAT_MESSAGE_NOT_FOUND",
      "message": "Chat message 'message-id' not found in session 'session-id'"
    }
  }
}
```

**curl**:
```bash
curl -X DELETE http://localhost:15010/api/v1/sessions/{session_id}/chat/{message_id}
```

---

### Clear Chat History

#### `DELETE /api/v1/sessions/{session_id}/chat`

Delete all chat messages for a session.

**Path Parameters**

| Parameter    | Type   | Description  |
| ------------ | ------ | ------------ |
| `session_id` | string | Session UUID |

**Response**: `204 No Content`

No response body on success.

**Error Responses**

| Status | Code              | Description            |
| ------ | ----------------- | ---------------------- |
| 404    | SESSION_NOT_FOUND | Session does not exist |

**Examples**

```json
// Error Response (404)
{
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "Session 'invalid-id' not found"
  }
}
```

**curl**:
```bash
curl -X DELETE http://localhost:15010/api/v1/sessions/{session_id}/chat
```

---

### Stream Chat Response

#### `GET /api/v1/sessions/{session_id}/chat/stream/{message_id}`

Stream the AI response for a chat message using Server-Sent Events (SSE).

**Two-Stage Response Streaming**

The streaming response is divided into two stages:

| Stage | Name | Description | Persisted |
|-------|------|-------------|-----------|
| 1 | EXPANDABLE | Plain text initialization + system events | No |
| 2 | PRIMARY | Final answer from assistant/result events | Yes |

**Stage 1 (Expandable)**: Full process output shown in collapsible accordion
- Plain text initialization (claude-mpm banner, agent sync, etc.)
- System JSON events (initialization, hooks)
- NOT persisted to database

**Stage 2 (Primary)**: Final answer shown prominently
- Assistant message content
- Result with metadata (tokens, duration, cost)
- Persisted to database

**Path Parameters**

| Parameter    | Type   | Description |
| ------------ | ------ | ----------- |
| `session_id` | string | Session UUID |
| `message_id` | string | Message UUID (from POST /chat response) |

**Response**: `200 OK` with `Content-Type: text/event-stream`

**SSE Event Types**

| Event Type | Stage | Description |
|------------|-------|-------------|
| `start` | - | Session started, message_id returned |
| `chunk` | 1 or 2 | Streaming content with stage classification |
| `complete` | - | Streaming finished, final content + metadata |
| `error` | - | Error occurred during processing |
| `heartbeat` | - | Keep-alive ping (every 15 seconds) |

**Chunk Event Schema**

```typescript
interface ChatStreamChunkEvent {
  content: string;                    // Line content
  event_type: ChatStreamEventType;    // Classification of this chunk
  stage: 1 | 2;                       // EXPANDABLE (1) or PRIMARY (2)
  raw_json?: object;                  // Original JSON event (if applicable)
}

enum ChatStreamEventType {
  START = "start",
  INIT_TEXT = "init_text",       // Plain text initialization (Stage 1)
  SYSTEM_INIT = "system_init",   // JSON system init event (Stage 1)
  SYSTEM_HOOK = "system_hook",   // JSON hook events (Stage 1)
  STREAM_TOKEN = "stream_token", // Token streaming if available (Stage 1)
  ASSISTANT = "assistant",       // Complete assistant message (Stage 2)
  RESULT = "result",             // Final result with metadata (Stage 2)
  ERROR = "error",
  HEARTBEAT = "heartbeat",
}
```

**Complete Event Schema**

```typescript
interface ChatStreamCompleteEvent {
  message_id: string;
  status: "completed";
  content: string;                    // Final answer (Stage 2 content only)
  metadata?: ChatStreamResultMetadata;
  token_count?: number;               // Legacy field
  duration_ms?: number;               // Legacy field
}

interface ChatStreamResultMetadata {
  token_count?: number;        // output_tokens
  input_tokens?: number;       // input_tokens
  cache_read_tokens?: number;  // cache_read_input_tokens
  duration_ms?: number;        // Total duration
  duration_api_ms?: number;    // API call duration
  cost_usd?: number;           // total_cost_usd
  session_id?: string;         // Claude session ID
  num_turns?: number;          // Number of turns
}
```

**Example SSE Stream**

```
event: start
data: {"message_id":"abc123","status":"streaming"}

event: chunk
data: {"content":"Syncing agents...","event_type":"init_text","stage":1,"raw_json":null}

event: chunk
data: {"content":"{\"type\":\"system\",\"subtype\":\"init\"...}","event_type":"system_init","stage":1,"raw_json":{...}}

event: chunk
data: {"content":"The answer is 4.","event_type":"assistant","stage":2,"raw_json":{...}}

event: chunk
data: {"content":"The answer is 4.","event_type":"result","stage":2,"raw_json":{...}}

event: complete
data: {"message_id":"abc123","status":"completed","content":"The answer is 4.","metadata":{"token_count":15,"duration_ms":3064,"cost_usd":0.17}}
```

**Error Event Schema**

```typescript
interface ChatStreamErrorEvent {
  message_id: string;
  status: "error";
  error: string;
}
```

**curl**:
```bash
curl -N "http://localhost:15010/api/v1/sessions/{session_id}/chat/stream/{message_id}"
```

**JavaScript EventSource**:
```javascript
const eventSource = new EventSource(streamUrl);
let stage1Content = '';
let stage2Content = '';

eventSource.addEventListener('chunk', (e) => {
  const data = JSON.parse(e.data);
  if (data.stage === 1) {
    stage1Content += data.content + '\n';  // Expandable accordion
  } else {
    stage2Content = data.content;           // Primary display
  }
});

eventSource.addEventListener('complete', (e) => {
  const data = JSON.parse(e.data);
  console.log('Final answer:', data.content);
  console.log('Metadata:', data.metadata);
  eventSource.close();
});
```

---

### Chat Cascade Behavior

When a session is deleted:
- All associated chat messages are automatically deleted (CASCADE)

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

| Code                      | HTTP Status | Description                          |
| ------------------------- | ----------- | ------------------------------------ |
| `VALIDATION_ERROR`        | 400         | Invalid request parameters           |
| `INVALID_METADATA`        | 400         | Invalid JSON in metadata field       |
| `SESSION_NOT_INDEXED`     | 400         | Session must be indexed before chat  |
| `SESSION_NOT_FOUND`       | 404         | Session UUID not found               |
| `CONTENT_NOT_FOUND`       | 404         | Content item not found               |
| `CHAT_MESSAGE_NOT_FOUND`  | 404         | Chat message UUID not found          |
| `WORKSPACE_NOT_FOUND`     | 404         | Workspace directory not found        |
| `TOOL_NOT_FOUND`          | 500         | mcp-vector-search CLI missing        |
| `INDEXING_TIMEOUT`        | 500         | Indexing subprocess timed out        |
| `CLAUDE_MPM_NOT_AVAILABLE`| 500         | claude-mpm CLI not found on PATH     |
| `CLAUDE_MPM_TIMEOUT`      | 500         | claude-mpm response timed out        |
| `INTERNAL_ERROR`          | 500         | Unexpected server error              |

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
| 1.2.0   | 2026-02-03 | Added Content Management endpoints: POST/GET/DELETE content items with support for text, file_upload, url, git_repo, mcp_source types. Added CONTENT_NOT_FOUND and INVALID_METADATA error codes. |
| 1.3.0   | 2026-02-03 | Added Chat endpoints: POST/GET/DELETE chat messages with session-scoped history. Added SESSION_NOT_INDEXED, CHAT_MESSAGE_NOT_FOUND, CLAUDE_MPM_NOT_AVAILABLE, CLAUDE_MPM_TIMEOUT error codes. SSE streaming endpoint marked as planned (Phase 2). |
| 1.4.0   | 2026-02-03 | Implemented Two-Stage Response Streaming: SSE events now include event_type, stage classification, and raw_json. Stage 1 (EXPANDABLE) for initialization/system events (not persisted). Stage 2 (PRIMARY) for assistant/result events (persisted). Added ChatStreamResultMetadata with token counts, duration, and cost. New event types: init_text, system_init, system_hook, stream_token, assistant, result. |
| 1.5.0   | 2026-02-04 | Added Clear Chat History endpoint: DELETE /api/v1/sessions/{session_id}/chat to delete all chat messages for a session. |

---

_This contract is the source of truth. Service and UI implementations must conform to these definitions. Changes to this contract require version bump and synchronization with `research-mind-ui/docs/api-contract.md`._
