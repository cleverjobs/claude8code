"""HTTP/API layer for claude8code.

This package contains:
- security: API key authentication
- middleware: Request context and logging middleware
- streaming: Streaming response utilities
- app: FastAPI application (imported separately)
- routes: API route handlers (imported separately)
"""

from .middleware import RequestContextMiddleware, RequestLoggingMiddleware
from .security import verify_api_key
from .streaming import StreamingResponseWithLogging, wrap_stream_with_logging

__all__ = [
    "verify_api_key",
    "RequestContextMiddleware",
    "RequestLoggingMiddleware",
    "StreamingResponseWithLogging",
    "wrap_stream_with_logging",
]
