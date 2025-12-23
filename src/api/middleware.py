"""Middleware for claude8code server.

Provides request context propagation and logging.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Awaitable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ..core import create_context, set_context, reset_context, get_context, log_request


logger = logging.getLogger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware that creates and propagates request context.

    Sets up a RequestContext for each incoming request with:
    - Unique request ID (from x-request-id header or generated)
    - Session ID (from x-session-id header)
    - Request metadata (path, method, client IP, user agent)

    The context is available via get_context() throughout the request lifecycle.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Extract or generate request ID
        request_id = request.headers.get("x-request-id")

        # Create context
        context = create_context(
            path=request.url.path,
            method=request.method,
            request_id=request_id,
            session_id=request.headers.get("x-session-id"),
            user_agent=request.headers.get("user-agent"),
            client_ip=request.client.host if request.client else None,
        )

        # Set context for this request
        token = set_context(context)

        try:
            # Process request
            response = await call_next(request)

            # Add request ID to response headers
            response.headers["x-request-id"] = context.request_id

            return response

        except Exception as e:
            context.set_error(e)
            raise

        finally:
            # Log request completion
            self._log_request(context, response if "response" in dir() else None)

            # Reset context
            reset_context(token)

    def _log_request(self, context, response: Response | None) -> None:  # type: ignore[no-untyped-def]
        """Log request completion."""
        status_code = response.status_code if response else 500
        level = logging.INFO if status_code < 400 else logging.WARNING

        log_data = context.to_log_dict()
        log_data["status_code"] = status_code

        logger.log(
            level,
            "[%s] %s %s %d %.2fms",
            context.request_id,
            context.method,
            context.path,
            status_code,
            context.duration_ms,
            extra=log_data,
        )

        # Log to access log database (fire and forget)
        asyncio.create_task(log_request(context, status_code))


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Simple request logging middleware.

    Logs each request with timing information.
    Use RequestContextMiddleware for full context propagation.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start_time = time.monotonic()
        request_id = request.headers.get("x-request-id", "-")

        try:
            response = await call_next(request)
            duration_ms = (time.monotonic() - start_time) * 1000

            logger.info(
                "[%s] %s %s %d %.2fms",
                request_id,
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )

            return response

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "[%s] %s %s ERROR %.2fms: %s",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
                str(e),
            )
            raise
