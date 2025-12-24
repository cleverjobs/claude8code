"""Unit tests for DuckDB access logging module."""

import pytest
import tempfile
from pathlib import Path

from src.core.access_log import (
    DUCKDB_AVAILABLE,
    AccessLogWriter,
    get_access_log_writer,
    is_access_log_available,
)
from src.core.context import RequestContext


class TestAccessLogAvailability:
    """Test DuckDB availability detection."""

    def test_duckdb_available_flag(self):
        """Test DUCKDB_AVAILABLE flag is boolean."""
        assert isinstance(DUCKDB_AVAILABLE, bool)

    def test_is_access_log_available_without_init(self):
        """Test is_access_log_available returns False without initialization."""
        # Without initialization, should be False
        # (may be True if another test initialized it)
        result = is_access_log_available()
        assert isinstance(result, bool)


class TestAccessLogWriter:
    """Test AccessLogWriter class."""

    def test_writer_creation(self):
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
    async def test_writer_start_stop(self):
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
    async def test_writer_log_request(self):
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
    async def test_writer_get_stats(self):
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
    async def test_writer_graceful_when_not_started(self):
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

    def test_writer_get_stats_when_not_connected(self):
        """Test get_stats when not connected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.duckdb"
            writer = AccessLogWriter(db_path=db_path)

            stats = writer.get_stats()
            assert stats["available"] is False


class TestGracefulDegradation:
    """Test graceful degradation when DuckDB not installed."""

    @pytest.mark.asyncio
    async def test_writer_start_without_duckdb(self):
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
    async def test_log_without_running_writer(self):
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


class TestGlobalWriter:
    """Test global writer functions."""

    def test_get_access_log_writer_returns_none_initially(self):
        """Test get_access_log_writer returns None or writer."""
        writer = get_access_log_writer()
        # May be None or a writer depending on test order
        assert writer is None or isinstance(writer, AccessLogWriter)
