"""Pydantic v2 schemas for audit log endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    """Single audit log entry returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    session_id: str
    action: str
    query: str | None = None
    result_count: int | None = None
    duration_ms: int | None = None
    status: str
    error: str | None = None
    metadata_json: dict[str, Any] | None = None


class AuditLogListResponse(BaseModel):
    """Paginated list of audit log entries."""

    logs: list[AuditLogResponse]
    count: int
