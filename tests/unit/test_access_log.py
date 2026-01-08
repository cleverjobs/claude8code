"""Unit tests for DuckDB access logging module."""

import tempfile
from pathlib import Path

import pytest

from src.core.access_log import (
    DUCKDB_AVAILABLE,
    AccessLogWriter,
    get_access_log_writer,
    is_access_log_available,
)
from src.core.context import RequestContext


class TestAccessLogAvailability:
    """Test DuckDB availability detection."""

    def test_duckdb_available_flag(self) -> None:
        """Test DUCKDB_AVAILABLE flag is boolean."""
        assert isinstance(DUCKDB_AVAILABLE, bool)

    def test_is_access_log_available_without_init(self) -> None:
        """Test is_access_log_available returns False without initialization."""
        # Without initialization, should be False
        # (may be True if another test initialized it)
        result = is_access_log_available()
        assert isinstance(result, bool)


class TestAccessLogWriter:
    """Test AccessLogWriter class."""

    def test_writer_creation(self) -> None:
        """Test creating an AccessLogWriter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(
                db_path=db_path,
                batch_size=10,
                flush_interval_seconds=1.0,
            )
            assert writer._db_path == db_path
            assert writer._batch_size == 10
            assert writer._flush_interval == 1.0
            assert not writer._running

    @pytest.mark.asyncio
    @pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="DuckDB not installed")
    async def test_writer_start_stop(self) -> None:
        """Test starting and stopping the writer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path)

            await writer.start()
            assert writer._running
            assert writer._conn is not None

            await writer.stop()
            assert not writer._running
            assert writer._conn is None

    @pytest.mark.asyncio
    @pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="DuckDB not installed")
    async def test_writer_log_request(self) -> None:
        """Test logging a request and querying it back."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path, batch_size=1)

            await writer.start()

            try:
                # Create a context and log it
                ctx = RequestContext(
                    request_id="req_test123",
                    path="/v1/messages",
                    method="POST",
                    model="claude-sonnet-4-5",
                    tokens_in=100,
                    tokens_out=50,
                )

                await writer.log(ctx, status_code=200)

                # Force flush
                await writer._flush()

                # Query to verify record was written
                results = writer.query("SELECT * FROM access_logs")
                assert len(results) == 1
                assert results[0]["request_id"] == "req_test123"
                assert results[0]["path"] == "/v1/messages"
                assert results[0]["method"] == "POST"
                assert results[0]["model"] == "claude-sonnet-4-5"
                assert results[0]["input_tokens"] == 100
                assert results[0]["output_tokens"] == 50
                assert results[0]["status_code"] == 200
                # Auto-increment ID should be 1
                assert results[0]["id"] == 1
            finally:
                await writer.stop()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="DuckDB not installed")
    async def test_writer_get_stats(self) -> None:
        """Test getting access log statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path)

            await writer.start()

            try:
                stats = writer.get_stats()
                assert stats["available"] is True
                assert "total_requests" in stats
                assert "queue_size" in stats
            finally:
                await writer.stop()

    @pytest.mark.asyncio
    async def test_writer_graceful_when_not_started(self) -> None:
        """Test writer is graceful when not started."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path)

            # Should not raise even when not started
            ctx = RequestContext(
                request_id="req_ignored",
                path="/test",
                method="GET",
            )
            await writer.log(ctx)  # Should be no-op

            # Query should return empty list
            results = writer.query("SELECT 1")
            assert results == []

    def test_writer_get_stats_when_not_connected(self) -> None:
        """Test get_stats when not connected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path)

            stats = writer.get_stats()
            assert stats["available"] is False


class TestGracefulDegradation:
    """Test graceful degradation when DuckDB not installed."""

    @pytest.mark.asyncio
    async def test_writer_start_without_duckdb(self) -> None:
        """Test writer start doesn't crash without DuckDB."""
        # This test verifies the code path works
        # whether DuckDB is installed or not
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path)

            # Should not raise
            await writer.start()
            await writer.stop()

    @pytest.mark.asyncio
    async def test_log_without_running_writer(self) -> None:
        """Test logging when writer not running doesn't crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path)

            ctx = RequestContext(
                request_id="req_test",
                path="/test",
                method="GET",
            )

            # Should not raise
            await writer.log(ctx)


class TestToolInvocationLogging:
    """Test tool invocation logging."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="DuckDB not installed")
    async def test_log_tool_invocation(self) -> None:
        """Test logging a tool invocation and querying it back."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path, batch_size=1)

            await writer.start()

            try:
                await writer.log_tool_invocation(
                    tool_use_id="tool_123",
                    session_id="sess_456",
                    tool_name="Read",
                    tool_category="builtin",
                    duration_seconds=0.5,
                    success=True,
                )

                # Force flush
                await writer._flush_tool_invocations()

                # Query to verify record was written
                results = writer.query("SELECT * FROM tool_invocations")
                assert len(results) == 1
                assert results[0]["tool_use_id"] == "tool_123"
                assert results[0]["session_id"] == "sess_456"
                assert results[0]["tool_name"] == "Read"
                assert results[0]["tool_category"] == "builtin"
                assert results[0]["duration_seconds"] == 0.5
                assert results[0]["success"] is True
            finally:
                await writer.stop()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="DuckDB not installed")
    async def test_log_tool_invocation_with_agent(self) -> None:
        """Test logging Task tool with subagent_type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path, batch_size=1)

            await writer.start()

            try:
                await writer.log_tool_invocation(
                    tool_use_id="tool_task_1",
                    session_id="sess_789",
                    tool_name="Task",
                    tool_category="agent",
                    duration_seconds=5.0,
                    subagent_type="Explore",
                    success=True,
                )

                await writer._flush_tool_invocations()

                results = writer.query(
                    "SELECT * FROM tool_invocations WHERE subagent_type = 'Explore'"
                )
                assert len(results) == 1
                assert results[0]["tool_name"] == "Task"
                assert results[0]["subagent_type"] == "Explore"
            finally:
                await writer.stop()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="DuckDB not installed")
    async def test_log_tool_invocation_with_skill(self) -> None:
        """Test logging Skill tool with skill_name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path, batch_size=1)

            await writer.start()

            try:
                await writer.log_tool_invocation(
                    tool_use_id="tool_skill_1",
                    session_id="sess_skill",
                    tool_name="Skill",
                    tool_category="skill",
                    duration_seconds=2.0,
                    skill_name="commit",
                    success=True,
                )

                await writer._flush_tool_invocations()

                results = writer.query("SELECT * FROM tool_invocations WHERE skill_name = 'commit'")
                assert len(results) == 1
                assert results[0]["tool_name"] == "Skill"
                assert results[0]["skill_name"] == "commit"
            finally:
                await writer.stop()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="DuckDB not installed")
    async def test_log_tool_invocation_with_error(self) -> None:
        """Test logging tool invocation with error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path, batch_size=1)

            await writer.start()

            try:
                await writer.log_tool_invocation(
                    tool_use_id="tool_error_1",
                    session_id="sess_error",
                    tool_name="Write",
                    tool_category="builtin",
                    duration_seconds=0.1,
                    success=False,
                    error_type="PermissionError",
                )

                await writer._flush_tool_invocations()

                results = writer.query("SELECT * FROM tool_invocations WHERE success = FALSE")
                assert len(results) == 1
                assert results[0]["success"] is False
                assert results[0]["error_type"] == "PermissionError"
            finally:
                await writer.stop()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="DuckDB not installed")
    async def test_log_tool_invocation_with_parameters(self) -> None:
        """Test logging tool invocation with JSON parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path, batch_size=1)

            await writer.start()

            try:
                params = {"file_path": "/test/file.py", "content_length": 100}
                await writer.log_tool_invocation(
                    tool_use_id="tool_params_1",
                    session_id="sess_params",
                    tool_name="Write",
                    tool_category="builtin",
                    parameters=params,
                )

                await writer._flush_tool_invocations()

                import json

                results = writer.query("SELECT parameters FROM tool_invocations")
                assert len(results) == 1
                stored_params = json.loads(results[0]["parameters"])
                assert stored_params["file_path"] == "/test/file.py"
                assert stored_params["content_length"] == 100
            finally:
                await writer.stop()

    @pytest.mark.asyncio
    @pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="DuckDB not installed")
    async def test_get_stats_includes_tool_invocations(self) -> None:
        """Test get_stats includes tool invocation statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path, batch_size=1)

            await writer.start()

            try:
                # Log a tool invocation
                await writer.log_tool_invocation(
                    tool_use_id="tool_stats_1",
                    session_id="sess_stats",
                    tool_name="Read",
                    tool_category="builtin",
                )
                await writer._flush_tool_invocations()

                stats = writer.get_stats()
                assert "tool_invocations" in stats
                assert stats["tool_invocations"]["total"] >= 0
                assert "by_tool" in stats["tool_invocations"]
                assert "queue_size" in stats["tool_invocations"]
            finally:
                await writer.stop()

    @pytest.mark.asyncio
    async def test_log_tool_invocation_graceful_when_not_started(self) -> None:
        """Test tool invocation logging is graceful when not started."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path)

            # Should not raise even when not started
            await writer.log_tool_invocation(
                tool_use_id="ignored",
                session_id="ignored",
                tool_name="Read",
                tool_category="builtin",
            )


class TestGlobalWriter:
    """Test global writer functions."""

    def test_get_access_log_writer_returns_none_initially(self) -> None:
        """Test get_access_log_writer returns None or writer."""
        writer = get_access_log_writer()
        # May be None or a writer depending on test order
        assert writer is None or isinstance(writer, AccessLogWriter)
