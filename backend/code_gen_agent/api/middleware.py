"""HTTP request/response lifecycle logging middleware.

Logs method, path, query, status code, duration, client IP, user agent,
and optional request/response body previews. Body capture is skipped for
SSE endpoints and file downloads to avoid buffering large streams.

Secret headers (Authorization, token, api_key, password, …) are redacted
from the logged header map. Bodies are truncated at BODY_PREVIEW_BYTES.
"""
from __future__ import annotations

import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from code_gen_agent.observability.logger import get_logger

log = get_logger("http")

BODY_PREVIEW_BYTES = 1024

# Paths where body capture must be skipped (streaming / binary responses).
_SKIP_BODY_SUFFIXES = ("/events", "/download")

_REDACT_HEADERS = frozenset({
    "authorization", "x-api-key", "api_key", "token", "password",
    "x-access-token", "x-auth-token",
})


def _safe_headers(request: Request) -> dict[str, str]:
    return {
        k.lower(): ("***" if k.lower() in _REDACT_HEADERS else v)
        for k, v in request.headers.items()
    }


def _skip_body(path: str) -> bool:
    return any(path.endswith(s) for s in _SKIP_BODY_SUFFIXES)


class HttpLoggingMiddleware(BaseHTTPMiddleware):
    """Emit one structured log line per HTTP request with lifecycle metadata."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        path = request.url.path
        query = str(request.url.query) if request.url.query else None

        req_body: str | None = None
        if not _skip_body(path) and request.method in ("POST", "PUT", "PATCH"):
            try:
                raw = await request.body()
                req_body = raw[:BODY_PREVIEW_BYTES].decode("utf-8", errors="replace")
                if len(raw) > BODY_PREVIEW_BYTES:
                    req_body += f"…[{len(raw)} bytes total]"
            except Exception:
                req_body = "<unreadable>"

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        extra: dict = {
            "event": "http_request",
            "method": request.method,
            "path": path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "content_type": request.headers.get("content-type"),
        }
        if query:
            extra["query"] = query
        if req_body is not None:
            extra["req_body"] = req_body

        level = "WARNING" if response.status_code >= 400 else "INFO"
        log.log(
            getattr(__import__("logging"), level),
            "http_request",
            extra=extra,
        )
        return response
