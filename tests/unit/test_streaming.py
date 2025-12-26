"""Unit tests for streaming response utilities."""

import logging
from typing import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest

from src.api.streaming import StreamingResponseWithLogging, wrap_stream_with_logging
from src.core.context import RequestContext


class TestStreamingResponseWithLogging:
    """Test StreamingResponseWithLogging class."""

    def test_init_with_context(self) -> None:
        """Test initialization with explicit context."""

        async def dummy_stream() -> AsyncIterator[bytes]:
            yield b"test"

        ctx = RequestContext(request_id="req_123", path="/test", method="POST")
        response = StreamingResponseWithLogging(content=dummy_stream(), context=ctx)

        assert response._context is ctx
        assert response.status_code == 200
        assert response.media_type == "text/event-stream"

    def test_init_without_context(self) -> None:
        """Test initialization without context uses get_context."""

        async def dummy_stream() -> AsyncIterator[bytes]:
            yield b"test"

        with patch("src.api.streaming.get_context") as mock_get:
            mock_ctx = MagicMock(spec=RequestContext)
            mock_get.return_value = mock_ctx

            response = StreamingResponseWithLogging(content=dummy_stream())
            assert response._context is mock_ctx

    def test_init_custom_status_and_headers(self) -> None:
        """Test initialization with custom status code and headers."""

        async def dummy_stream() -> AsyncIterator[bytes]:
            yield b"test"

        ctx = RequestContext(request_id="req_123", path="/test", method="POST")
        response = StreamingResponseWithLogging(
            content=dummy_stream(),
            context=ctx,
            status_code=201,
            headers={"X-Custom": "value"},
            media_type="application/json",
        )

        assert response.status_code == 201
        assert response.media_type == "application/json"

    @pytest.mark.asyncio
    async def test_wrap_with_logging_yields_chunks(self) -> None:
        """Test that wrapped stream yields all chunks."""

        async def test_stream() -> AsyncIterator[bytes]:
            yield b"chunk1"
            yield b"chunk2"
            yield b"chunk3"

        ctx = RequestContext(request_id="req_123", path="/test", method="POST")
        response = StreamingResponseWithLogging(content=test_stream(), context=ctx)

        chunks = []
        async for chunk in response._wrapped_content:
            chunks.append(chunk)

        assert chunks == [b"chunk1", b"chunk2", b"chunk3"]

    @pytest.mark.asyncio
    async def test_wrap_with_logging_converts_strings(self) -> None:
        """Test that string chunks are converted to bytes."""

        async def test_stream() -> AsyncIterator[str]:
            yield "hello"
            yield "world"

        ctx = RequestContext(request_id="req_123", path="/test", method="POST")
        response = StreamingResponseWithLogging(content=test_stream(), context=ctx)

        chunks = []
        async for chunk in response._wrapped_content:
            chunks.append(chunk)

        assert chunks == [b"hello", b"world"]

    @pytest.mark.asyncio
    async def test_wrap_with_logging_records_metrics(self) -> None:
        """Test that stream completion records metrics."""

        async def test_stream() -> AsyncIterator[bytes]:
            yield b"data"

        ctx = RequestContext(request_id="req_123", path="/test", method="POST")

        with patch("src.api.streaming.record_stream_completion") as mock_record:
            response = StreamingResponseWithLogging(content=test_stream(), context=ctx)

            async for _ in response._wrapped_content:
                pass

            mock_record.assert_called_once()
            args = mock_record.call_args[0]
            assert args[0] == 4  # bytes_sent
            assert args[1] > 0  # duration > 0

    @pytest.mark.asyncio
    async def test_wrap_with_logging_handles_error(self) -> None:
        """Test that errors are captured and re-raised."""

        async def error_stream() -> AsyncIterator[bytes]:
            yield b"start"
            raise ValueError("Test error")

        ctx = RequestContext(request_id="req_123", path="/test", method="POST")
        response = StreamingResponseWithLogging(content=error_stream(), context=ctx)

        with pytest.raises(ValueError, match="Test error"):
            async for _ in response._wrapped_content:
                pass

        assert ctx.error is not None
        assert "ValueError" in ctx.error

    @pytest.mark.asyncio
    async def test_wrap_with_logging_handles_disconnect(self) -> None:
        """Test that client disconnect is handled."""

        async def disconnect_stream() -> AsyncIterator[bytes]:
            yield b"data"
            raise GeneratorExit()

        ctx = RequestContext(request_id="req_123", path="/test", method="POST")
        response = StreamingResponseWithLogging(content=disconnect_stream(), context=ctx)

        with pytest.raises(GeneratorExit):
            async for _ in response._wrapped_content:
                pass

        assert ctx.disconnect_reason == "client_disconnect"

    def test_log_completion_success(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test logging on successful completion."""
        ctx = RequestContext(
            request_id="req_123", path="/v1/messages", method="POST", model="claude-3"
        )

        async def dummy() -> AsyncIterator[bytes]:
            yield b""

        response = StreamingResponseWithLogging(content=dummy(), context=ctx)

        with caplog.at_level(logging.INFO):
            response._log_completion(
                bytes_sent=100, chunks_sent=5, duration=0.5, error=None, disconnect=False
            )

        assert "stream_completed" in caplog.text
        assert "status=success" in caplog.text
        assert "bytes=100" in caplog.text

    def test_log_completion_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test logging on error."""
        ctx = RequestContext(request_id="req_456", path="/test", method="POST")

        async def dummy() -> AsyncIterator[bytes]:
            yield b""

        response = StreamingResponseWithLogging(content=dummy(), context=ctx)

        with caplog.at_level(logging.ERROR):
            response._log_completion(
                bytes_sent=50,
                chunks_sent=2,
                duration=0.3,
                error=RuntimeError("Failed"),
                disconnect=False,
            )

        assert "status=error" in caplog.text

    def test_log_completion_disconnect(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test logging on client disconnect."""
        ctx = RequestContext(request_id="req_789", path="/test", method="POST")

        async def dummy() -> AsyncIterator[bytes]:
            yield b""

        response = StreamingResponseWithLogging(content=dummy(), context=ctx)

        with caplog.at_level(logging.WARNING):
            response._log_completion(
                bytes_sent=25, chunks_sent=1, duration=0.1, error=None, disconnect=True
            )

        assert "status=client_disconnect" in caplog.text

    def test_log_completion_no_context(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test logging when context is None."""

        async def dummy() -> AsyncIterator[bytes]:
            yield b""

        with patch("src.api.streaming.get_context", return_value=None):
            response = StreamingResponseWithLogging(content=dummy())

        with caplog.at_level(logging.INFO):
            response._log_completion(
                bytes_sent=10, chunks_sent=1, duration=0.1, error=None, disconnect=False
            )

        # Should use "-" for missing context values
        assert "[-]" in caplog.text


class TestWrapStreamWithLogging:
    """Test wrap_stream_with_logging function."""

    @pytest.mark.asyncio
    async def test_yields_all_chunks(self) -> None:
        """Test that all chunks are yielded."""

        async def test_stream() -> AsyncIterator[bytes]:
            yield b"a"
            yield b"b"
            yield b"c"

        ctx = RequestContext(request_id="req_123", path="/test", method="POST")

        chunks = []
        async for chunk in wrap_stream_with_logging(test_stream(), context=ctx):
            chunks.append(chunk)

        assert chunks == [b"a", b"b", b"c"]

    @pytest.mark.asyncio
    async def test_converts_strings_to_bytes(self) -> None:
        """Test that strings are converted to bytes."""

        async def test_stream() -> AsyncIterator[str]:
            yield "hello"

        ctx = RequestContext(request_id="req_123", path="/test", method="POST")

        chunks = []
        async for chunk in wrap_stream_with_logging(test_stream(), context=ctx):
            chunks.append(chunk)

        assert chunks == [b"hello"]

    @pytest.mark.asyncio
    async def test_uses_get_context_when_none(self) -> None:
        """Test that get_context is used when context is None."""

        async def test_stream() -> AsyncIterator[bytes]:
            yield b"data"

        mock_ctx = MagicMock(spec=RequestContext)
        mock_ctx.request_id = "req_auto"

        with patch("src.api.streaming.get_context", return_value=mock_ctx):
            with patch("src.api.streaming.record_stream_completion"):
                async for _ in wrap_stream_with_logging(test_stream()):
                    pass

    @pytest.mark.asyncio
    async def test_handles_error(self) -> None:
        """Test error handling."""

        async def error_stream() -> AsyncIterator[bytes]:
            raise RuntimeError("Stream error")
            yield b""  # Never reached

        ctx = RequestContext(request_id="req_123", path="/test", method="POST")

        with pytest.raises(RuntimeError, match="Stream error"):
            async for _ in wrap_stream_with_logging(error_stream(), context=ctx):
                pass

        assert ctx.error is not None

    @pytest.mark.asyncio
    async def test_handles_generator_exit(self) -> None:
        """Test GeneratorExit handling."""

        async def disconnect_stream() -> AsyncIterator[bytes]:
            yield b"start"
            raise GeneratorExit()

        ctx = RequestContext(request_id="req_123", path="/test", method="POST")

        with pytest.raises(GeneratorExit):
            async for _ in wrap_stream_with_logging(disconnect_stream(), context=ctx):
                pass

        assert ctx.disconnect_reason == "client_disconnect"

    @pytest.mark.asyncio
    async def test_records_metrics(self) -> None:
        """Test that metrics are recorded on completion."""

        async def test_stream() -> AsyncIterator[bytes]:
            yield b"12345"

        ctx = RequestContext(request_id="req_123", path="/test", method="POST")

        with patch("src.api.streaming.record_stream_completion") as mock_record:
            async for _ in wrap_stream_with_logging(test_stream(), context=ctx):
                pass

            mock_record.assert_called_once()
            args = mock_record.call_args[0]
            assert args[0] == 5  # bytes_sent

    @pytest.mark.asyncio
    async def test_logs_completion(self, caplog: pytest.LogCaptureFixture) -> None:
        """Test that completion is logged."""

        async def test_stream() -> AsyncIterator[bytes]:
            yield b"data"

        ctx = RequestContext(request_id="req_log", path="/test", method="POST")

        with patch("src.api.streaming.record_stream_completion"):
            with caplog.at_level(logging.INFO):
                async for _ in wrap_stream_with_logging(test_stream(), context=ctx):
                    pass

        assert "stream_completed" in caplog.text
        assert "req_log" in caplog.text
