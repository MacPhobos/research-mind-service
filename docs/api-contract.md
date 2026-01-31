# research-mind API Contract

## Overview

Base URL: `http://localhost:15010`

All timestamps are in ISO 8601 format (UTC).

## Endpoints

### Health Check

**GET** `/health`

Returns service health status and metadata.

Response (200 OK):
```json
{
  "status": "ok",
  "name": "research-mind-service",
  "version": "0.1.0",
  "git_sha": "abc1234"
}
```

### API Version

**GET** `/api/v1/version`

Returns API version and git SHA.

Response (200 OK):
```json
{
  "name": "research-mind-service",
  "version": "0.1.0",
  "git_sha": "abc1234"
}
```

## Error Responses

All error responses follow this format:

```json
{
  "error": {
    "message": "Error description",
    "code": "error_code"
  }
}
```

Common HTTP Status Codes:
- `200` - OK
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `500` - Internal Server Error

## CORS

CORS is enabled for the following origins (configure in `.env`):
- `http://localhost:15000` (development)

## Authentication

Authentication is not yet implemented. Stubs exist in `app/auth/`.

JWT token-based authentication is planned for production.

## Rate Limiting

Rate limiting is not yet implemented.

## Pagination

Endpoints supporting pagination use query parameters:
- `limit` (default: 10, max: 100)
- `offset` (default: 0)

Response format:
```json
{
  "data": [...],
  "pagination": {
    "limit": 10,
    "offset": 0,
    "total": 50
  }
}
```
