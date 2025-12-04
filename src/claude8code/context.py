"""Request context propagation for claude8code.

Provides correlation IDs and request metadata that follows async call chains.
Uses contextvars for automatic propagation across async boundaries.
"""

from __future__ import annotations

import contextvars
import time
from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4


@dataclass
class RequestContext:
    """Context for a single request.

    Carries request metadata and correlation ID through async call chains.
    Mutable fields (tokens, error) can be updated during request processing.
    """

    request_id: str
    path: str
    method: str
    start_time: float = field(default_factory=time.monotonic)

    # Optional request metadata
    session_id: Optional[str] = None
    model: Optional[str] = None
    user_agent: Optional[str] = None
    client_ip: Optional[str] = None

    # Mutable during request processing
    tokens_in: int = 0
    tokens_out: int = 0
    error: Optional[str] = None
    stream: bool = False
    disconnect_reason: Optional[str] = None

    @property
    def duration_seconds(self) -> float:
        """Get elapsed time since request started."""
        return time.monotonic() - self.start_time

    @property
    def duration_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        return self.duration_seconds * 1000

    @property
    def total_tokens(self) -> int:
        """Get total tokens used."""
        return self.tokens_in + self.tokens_out

    def update_tokens(self, input_tokens: int, output_tokens: int) -> None:
        """Update token counts."""
        self.tokens_in += input_tokens
        self.tokens_out += output_tokens

    def set_error(self, error: str | Exception) -> None:
        """Set error message."""
        if isinstance(error, Exception):
            self.error = f"{type(error).__name__}: {str(error)}"
        else:
            self.error = error

    def to_log_dict(self) -> dict[str, object]:
        """Convert to dictionary for logging."""
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "path": self.path,
            "method": self.method,
            "model": self.model,
            "duration_ms": round(self.duration_ms, 2),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "stream": self.stream,
            "error": self.error,
        }


# Context variable for request context
_request_context: contextvars.ContextVar[RequestContext | None] = contextvars.ContextVar(
    "request_context", default=None
)


def set_context(ctx: RequestContext) -> contextvars.Token[RequestContext | None]:
    """Set the request context for the current async context.

    Args:
        ctx: RequestContext to set

    Returns:
        Token that can be used to reset the context
    """
    return _request_context.set(ctx)


def get_context() -> RequestContext | None:
    """Get the current request context.

    Returns:
        Current RequestContext, or None if not in a request context
    """
    return _request_context.get()


def reset_context(token: contextvars.Token[RequestContext | None]) -> None:
    """Reset the request context to a previous state.

    Args:
        token: Token from set_context()
    """
    _request_context.reset(token)


def create_context(
    path: str,
    method: str,
    request_id: str | None = None,
    session_id: str | None = None,
    user_agent: str | None = None,
    client_ip: str | None = None,
) -> RequestContext:
    """Create a new request context.

    Args:
        path: Request path
        method: HTTP method
        request_id: Optional request ID (generated if not provided)
        session_id: Optional session ID
        user_agent: Optional user agent
        client_ip: Optional client IP

    Returns:
        New RequestContext
    """
    if request_id is None:
        request_id = f"req_{uuid4().hex[:12]}"

    return RequestContext(
        request_id=request_id,
        path=path,
        method=method,
        session_id=session_id,
        user_agent=user_agent,
        client_ip=client_ip,
    )


class RequestContextManager:
    """Context manager for request context.

    Usage:
        async with RequestContextManager(path="/v1/messages", method="POST") as ctx:
            # ctx is available here
            # and via get_context() anywhere in the async chain
    """

    def __init__(
        self,
        path: str,
        method: str,
        request_id: str | None = None,
        session_id: str | None = None,
        user_agent: str | None = None,
        client_ip: str | None = None,
    ):
        self.context = create_context(
            path=path,
            method=method,
            request_id=request_id,
            session_id=session_id,
            user_agent=user_agent,
            client_ip=client_ip,
        )
        self._token: contextvars.Token[RequestContext | None] | None = None

    async def __aenter__(self) -> RequestContext:
        self._token = set_context(self.context)
        return self.context

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        if exc_val is not None:
            self.context.set_error(exc_val)
        if self._token is not None:
            reset_context(self._token)

    def __enter__(self) -> RequestContext:
        self._token = set_context(self.context)
        return self.context

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        if exc_val is not None:
            self.context.set_error(exc_val)
        if self._token is not None:
            reset_context(self._token)
