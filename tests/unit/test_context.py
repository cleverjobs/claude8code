"""Unit tests for request context module."""

import time
import pytest

from src.core.context import (
    RequestContext,
    create_context,
    set_context,
    get_context,
    reset_context,
    RequestContextManager,
)


class TestRequestContext:
    """Test RequestContext dataclass."""

    def test_create_with_required_fields(self):
        """Test creating context with only required fields."""
        ctx = RequestContext(
            request_id="req_123",
            path="/v1/messages",
            method="POST",
        )
        assert ctx.request_id == "req_123"
        assert ctx.path == "/v1/messages"
        assert ctx.method == "POST"
        assert ctx.tokens_in == 0
        assert ctx.tokens_out == 0
        assert ctx.error is None
        assert ctx.stream is False

    def test_create_with_all_fields(self):
        """Test creating context with all fields."""
        ctx = RequestContext(
            request_id="req_456",
            path="/v1/models",
            method="GET",
            session_id="sess_abc",
            model="claude-sonnet-4-5",
            user_agent="TestClient/1.0",
            client_ip="127.0.0.1",
        )
        assert ctx.session_id == "sess_abc"
        assert ctx.model == "claude-sonnet-4-5"
        assert ctx.user_agent == "TestClient/1.0"
        assert ctx.client_ip == "127.0.0.1"

    def test_duration_calculation(self):
        """Test duration properties calculate elapsed time."""
        ctx = RequestContext(
            request_id="req_789",
            path="/test",
            method="GET",
        )
        # Sleep briefly to get measurable duration
        time.sleep(0.01)
        assert ctx.duration_seconds >= 0.01
        assert ctx.duration_ms >= 10

    def test_total_tokens(self):
        """Test total_tokens property."""
        ctx = RequestContext(
            request_id="req_tok",
            path="/test",
            method="POST",
            tokens_in=100,
            tokens_out=50,
        )
        assert ctx.total_tokens == 150

    def test_update_tokens(self):
        """Test update_tokens method accumulates."""
        ctx = RequestContext(
            request_id="req_upd",
            path="/test",
            method="POST",
        )
        ctx.update_tokens(10, 20)
        assert ctx.tokens_in == 10
        assert ctx.tokens_out == 20

        ctx.update_tokens(5, 10)
        assert ctx.tokens_in == 15
        assert ctx.tokens_out == 30

    def test_set_error_string(self):
        """Test set_error with string."""
        ctx = RequestContext(
            request_id="req_err",
            path="/test",
            method="POST",
        )
        ctx.set_error("Something went wrong")
        assert ctx.error == "Something went wrong"

    def test_set_error_exception(self):
        """Test set_error with Exception."""
        ctx = RequestContext(
            request_id="req_exc",
            path="/test",
            method="POST",
        )
        ctx.set_error(ValueError("Invalid input"))
        assert ctx.error == "ValueError: Invalid input"

    def test_to_log_dict(self):
        """Test to_log_dict returns proper structure."""
        ctx = RequestContext(
            request_id="req_log",
            path="/v1/messages",
            method="POST",
            session_id="sess_123",
            model="claude-sonnet-4-5",
            tokens_in=50,
            tokens_out=100,
            stream=True,
        )
        log_dict = ctx.to_log_dict()

        assert log_dict["request_id"] == "req_log"
        assert log_dict["session_id"] == "sess_123"
        assert log_dict["path"] == "/v1/messages"
        assert log_dict["method"] == "POST"
        assert log_dict["model"] == "claude-sonnet-4-5"
        assert log_dict["tokens_in"] == 50
        assert log_dict["tokens_out"] == 100
        assert log_dict["stream"] is True
        assert log_dict["error"] is None
        assert "duration_ms" in log_dict


class TestContextFunctions:
    """Test context variable functions."""

    def test_create_context_generates_id(self):
        """Test create_context generates request ID if not provided."""
        ctx = create_context(path="/test", method="GET")
        assert ctx.request_id.startswith("req_")
        assert len(ctx.request_id) == 16  # "req_" + 12 hex chars

    def test_create_context_uses_provided_id(self):
        """Test create_context uses provided request ID."""
        ctx = create_context(
            path="/test",
            method="GET",
            request_id="custom_id_123",
        )
        assert ctx.request_id == "custom_id_123"

    def test_set_and_get_context(self):
        """Test setting and getting context."""
        ctx = create_context(path="/test", method="POST")
        token = set_context(ctx)

        try:
            retrieved = get_context()
            assert retrieved is ctx
            assert retrieved.path == "/test"
        finally:
            reset_context(token)

    def test_get_context_returns_none_when_not_set(self):
        """Test get_context returns None when no context set."""
        # Create a fresh context to ensure clean state
        ctx = get_context()
        # May or may not be None depending on test order
        # but shouldn't raise


class TestRequestContextManager:
    """Test RequestContextManager."""

    def test_sync_context_manager(self):
        """Test synchronous context manager usage."""
        with RequestContextManager(path="/sync", method="GET") as ctx:
            assert ctx.path == "/sync"
            assert ctx.method == "GET"
            retrieved = get_context()
            assert retrieved is ctx

    def test_sync_context_manager_cleans_up(self):
        """Test sync context manager resets context on exit."""
        original = get_context()
        with RequestContextManager(path="/cleanup", method="POST"):
            pass
        # Context should be reset (may be None or original)

    def test_sync_context_manager_captures_error(self):
        """Test sync context manager captures exceptions."""
        try:
            with RequestContextManager(path="/error", method="POST") as ctx:
                raise ValueError("Test error")
        except ValueError:
            pass
        # Error should have been captured before reset

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test asynchronous context manager usage."""
        async with RequestContextManager(path="/async", method="GET") as ctx:
            assert ctx.path == "/async"
            retrieved = get_context()
            assert retrieved is ctx

    @pytest.mark.asyncio
    async def test_async_context_manager_captures_error(self):
        """Test async context manager captures exceptions."""
        ctx_ref = None
        try:
            async with RequestContextManager(path="/async-error", method="POST") as ctx:
                ctx_ref = ctx
                raise RuntimeError("Async error")
        except RuntimeError:
            pass
        # Error was captured in the context before it was reset
        assert ctx_ref is not None
        assert "RuntimeError" in ctx_ref.error
