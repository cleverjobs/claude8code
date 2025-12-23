"""Streaming response utilities for claude8code.

Provides StreamingResponseWithLogging for automatic stream completion logging.
"""

from __future__ import annotations

import logging
import time
from typing import AsyncIterator, Any

from starlette.responses import StreamingResponse

from ..core import RequestContext, get_context, record_stream_completion


logger = logging.getLogger(__name__)


class StreamingResponseWithLogging(StreamingResponse):
    """StreamingResponse that automatically logs on completion.

    Wraps the content generator to track bytes sent and duration,
    then logs when the stream completes (success, error, or client disconnect).

    Usage:
        @app.post("/v1/messages")
        async def create_message(request: MessagesRequest):
            stream = process_streaming(request)
            context = get_context()
            return StreamingResponseWithLogging(content=stream, context=context)
    """

    def __init__(
        self,
        content: AsyncIterator[bytes | str],
        context: RequestContext | None = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str = "text/event-stream",
        **kwargs: Any,
    ):
        # Get context from current request if not provided
        if context is None:
            context = get_context()

        self._context = context
        self._wrapped_content = self._wrap_with_logging(content)

        super().__init__(
            content=self._wrapped_content,
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            **kwargs,
        )

    async def _wrap_with_logging(
        self,
        content: AsyncIterator[bytes | str],
    ) -> AsyncIterator[bytes]:
        """Wrap content generator with logging on completion."""
        bytes_sent = 0
        chunks_sent = 0
        start_time = time.monotonic()
        error: Exception | None = None
        disconnect = False

        try:
            async for chunk in content:
                # Convert string to bytes if needed
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")

                bytes_sent += len(chunk)
                chunks_sent += 1
                yield chunk

        except GeneratorExit:
            # Client disconnected
            disconnect = True
            if self._context:
                self._context.disconnect_reason = "client_disconnect"
            raise

        except Exception as e:
            error = e
            if self._context:
                self._context.set_error(e)
            raise

        finally:
            duration = time.monotonic() - start_time

            # Log completion
            self._log_completion(
                bytes_sent=bytes_sent,
                chunks_sent=chunks_sent,
                duration=duration,
                error=error,
                disconnect=disconnect,
            )

            # Record metrics
            record_stream_completion(bytes_sent, duration)

    def _log_completion(
        self,
        bytes_sent: int,
        chunks_sent: int,
        duration: float,
        error: Exception | None,
        disconnect: bool,
    ) -> None:
        """Log stream completion."""
        if disconnect:
            status = "client_disconnect"
            level = logging.WARNING
        elif error:
            status = "error"
            level = logging.ERROR
        else:
            status = "success"
            level = logging.INFO

        request_id = self._context.request_id if self._context else "-"
        path = self._context.path if self._context else "-"
        model = self._context.model if self._context else "-"

        log_data = {
            "event": "stream_completed",
            "request_id": request_id,
            "path": path,
            "model": model,
            "status": status,
            "bytes_sent": bytes_sent,
            "chunks_sent": chunks_sent,
            "duration_seconds": round(duration, 3),
        }

        if error:
            log_data["error"] = str(error)
            log_data["error_type"] = type(error).__name__

        logger.log(
            level,
            "[%s] stream_completed status=%s bytes=%d chunks=%d duration=%.3fs",
            request_id,
            status,
            bytes_sent,
            chunks_sent,
            duration,
            extra=log_data,
        )


async def wrap_stream_with_logging(
    content: AsyncIterator[bytes | str],
    context: RequestContext | None = None,
) -> AsyncIterator[bytes]:
    """Wrap a stream with logging on completion.

    Alternative to StreamingResponseWithLogging when you need to wrap
    a stream without creating a response object.

    Args:
        content: Async iterator of chunks
        context: Optional request context (uses current context if not provided)

    Yields:
        Chunks from the wrapped stream
    """
    if context is None:
        context = get_context()

    bytes_sent = 0
    chunks_sent = 0
    start_time = time.monotonic()
    error: Exception | None = None
    disconnect = False

    try:
        async for chunk in content:
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
            bytes_sent += len(chunk)
            chunks_sent += 1
            yield chunk

    except GeneratorExit:
        disconnect = True
        if context:
            context.disconnect_reason = "client_disconnect"
        raise

    except Exception as e:
        error = e
        if context:
            context.set_error(e)
        raise

    finally:
        duration = time.monotonic() - start_time

        status = "client_disconnect" if disconnect else ("error" if error else "success")
        request_id = context.request_id if context else "-"

        logger.info(
            "[%s] stream_completed status=%s bytes=%d duration=%.3fs",
            request_id,
            status,
            bytes_sent,
            duration,
        )

        record_stream_completion(bytes_sent, duration)
