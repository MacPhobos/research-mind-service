"""Middleware for validating session/workspace IDs in URL paths.

Protects routes under /api/v1/sessions/{uuid} and /api/v1/workspaces/{uuid}
by ensuring the UUID path parameter is a valid UUID v4 format.

Does NOT perform database lookups — route handlers own that responsibility.
"""

from __future__ import annotations

import logging
import re

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Matches a valid UUID v4 (lowercase hex with dashes)
_UUID_V4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Routes that require UUID validation: /api/v1/{resource}/{uuid}/...
_PROTECTED_PREFIXES = (
    "/api/v1/sessions/",
    "/api/v1/workspaces/",
)


class SessionValidationMiddleware(BaseHTTPMiddleware):
    """Validate UUID format in session and workspace URL paths.

    For protected routes (sessions/{id}/... and workspaces/{id}/...),
    extracts the ID segment and validates it as UUID v4. Returns 400
    for invalid formats. Passes through for non-protected paths.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        for prefix in _PROTECTED_PREFIXES:
            if path.startswith(prefix):
                # Extract the ID segment after the prefix
                remainder = path[len(prefix):]
                # The ID is the first path segment
                id_segment = remainder.split("/")[0] if remainder else ""

                if not id_segment:
                    # No ID in path — let the router handle it
                    # (e.g., /api/v1/sessions/ is the list endpoint)
                    break

                if not _UUID_V4_PATTERN.match(id_segment):
                    logger.warning(
                        "INVALID_UUID: Rejected '%s' in path '%s'",
                        id_segment,
                        path,
                    )
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": {
                                "code": "INVALID_UUID_FORMAT",
                                "message": (
                                    f"Invalid UUID format: '{id_segment}'. "
                                    "Expected UUID v4 format."
                                ),
                            }
                        },
                    )
                # Valid UUID — continue to handler
                break

        return await call_next(request)
