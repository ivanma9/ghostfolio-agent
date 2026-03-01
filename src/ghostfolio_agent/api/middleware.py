"""Request logging middleware with correlation IDs."""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ghostfolio_agent.logging_config import set_request_id

logger = structlog.get_logger()

# Paths that generate noise — only log at debug level
_QUIET_PREFIXES = ("/api/health", "/assets/", "/favicon")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        set_request_id(request_id)

        start_time = time.monotonic()

        response = await call_next(request)

        duration_ms = round((time.monotonic() - start_time) * 1000, 1)

        path = request.url.path
        quiet = any(path.startswith(p) for p in _QUIET_PREFIXES)
        log = logger.debug if quiet else logger.info

        log(
            "request",
            method=request.method,
            path=path,
            status=response.status_code,
            ms=duration_ms,
        )

        response.headers["x-request-id"] = request_id
        return response
