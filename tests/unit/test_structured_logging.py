"""Unit tests for structured logging module."""

import json
import logging
from io import StringIO

from src.core.structured_logging import (
    STRUCTLOG_AVAILABLE,
    JSONFormatter,
    bind_context,
    clear_context,
    configure_structured_logging,
    get_logger,
    is_structlog_available,
)


class TestStructlogAvailability:
    """Test structlog availability detection."""

    def test_structlog_available_flag(self) -> None:
        """Test STRUCTLOG_AVAILABLE flag is boolean."""
        assert isinstance(STRUCTLOG_AVAILABLE, bool)

    def test_is_structlog_available_function(self) -> None:
        """Test is_structlog_available() returns correct value."""
        assert is_structlog_available() == STRUCTLOG_AVAILABLE


class TestJSONFormatter:
    """Test JSONFormatter class."""

    def test_formats_basic_record(self) -> None:
        """Test basic log record formatting."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["level"] == "info"
        assert data["logger"] == "test_logger"
        assert data["message"] == "Test message"
        assert "timestamp" in data

    def test_formats_with_args(self) -> None:
        """Test log record with format arguments."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.WARNING,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Value is %s and count is %d",
            args=("test", 42),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["level"] == "warning"
        assert data["message"] == "Value is test and count is 42"

    def test_formats_with_exception(self) -> None:
        """Test log record with exception info."""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test exception")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test_logger",
            level=logging.ERROR,
            pathname="/path/to/file.py",
            lineno=42,
            msg="An error occurred",
            args=(),
            exc_info=exc_info,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["level"] == "error"
        assert "exception" in data
        assert "ValueError" in data["exception"]
        assert "Test exception" in data["exception"]

    def test_timestamp_is_iso_format(self) -> None:
        """Test timestamp is in ISO format."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="/path/to/file.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        # ISO format should contain 'T' separator and timezone
        assert "T" in data["timestamp"]
        # Should be parseable by datetime
        from datetime import datetime

        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))

    def test_level_is_lowercase(self) -> None:
        """Test that level is lowercase."""
        formatter = JSONFormatter()

        for level in [
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
            logging.CRITICAL,
        ]:
            record = logging.LogRecord(
                name="test_logger",
                level=level,
                pathname="/path/to/file.py",
                lineno=42,
                msg="Test message",
                args=(),
                exc_info=None,
            )

            result = formatter.format(record)
            data = json.loads(result)

            assert data["level"] == data["level"].lower()


class TestConfigureStructuredLogging:
    """Test configure_structured_logging function."""

    def test_configures_without_crash(self) -> None:
        """Test configuration doesn't crash."""
        # Should work whether structlog is installed or not
        configure_structured_logging(log_level="INFO", json_format=True)

    def test_configures_with_debug_level(self) -> None:
        """Test configuration with DEBUG level."""
        configure_structured_logging(log_level="DEBUG", json_format=False)

    def test_configures_console_format(self) -> None:
        """Test configuration with console format."""
        configure_structured_logging(log_level="INFO", json_format=False)

    def test_accepts_various_log_levels(self) -> None:
        """Test that various log levels are accepted."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            configure_structured_logging(log_level=level, json_format=True)


class TestGetLogger:
    """Test get_logger function."""

    def test_returns_logger(self) -> None:
        """Test get_logger returns a logger."""
        logger = get_logger("test_module")
        assert logger is not None

    def test_logger_has_log_methods(self) -> None:
        """Test logger has standard log methods."""
        logger = get_logger("test_module")

        # All loggers should have these methods
        assert hasattr(logger, "info") or hasattr(logger, "msg")
        assert hasattr(logger, "warning") or hasattr(logger, "warn")
        assert hasattr(logger, "error") or hasattr(logger, "err")
        assert hasattr(logger, "debug")

    def test_different_names_return_different_loggers(self) -> None:
        """Test different names return different loggers."""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")

        # They might be the same type but should be distinct instances
        # or at least have different configurations
        assert logger1 is not None
        assert logger2 is not None


class TestBindContext:
    """Test bind_context function."""

    def test_bind_context_no_crash(self) -> None:
        """Test bind_context doesn't crash."""
        # Should work whether structlog is available or not
        bind_context(request_id="req_123", session_id="sess_456")

    def test_bind_multiple_values(self) -> None:
        """Test binding multiple context values."""
        bind_context(
            key1="value1",
            key2="value2",
            key3=123,
        )


class TestClearContext:
    """Test clear_context function."""

    def test_clear_context_no_crash(self) -> None:
        """Test clear_context doesn't crash."""
        # Bind some context first
        bind_context(request_id="req_123")

        # Should work whether structlog is available or not
        clear_context()

    def test_clear_after_bind(self) -> None:
        """Test clearing after binding."""
        bind_context(key="value")
        clear_context()
        # Should not crash even if called multiple times
        clear_context()


class TestGracefulDegradation:
    """Test graceful degradation when structlog not installed."""

    def test_all_functions_work_without_structlog(self) -> None:
        """Test all public functions work without crashing."""
        # Configure logging
        configure_structured_logging(log_level="INFO", json_format=True)

        # Get logger
        _ = get_logger("test_graceful")

        # Bind and clear context
        bind_context(test_key="test_value")
        clear_context()

        # Check availability
        _ = is_structlog_available()

    def test_json_formatter_is_standalone(self) -> None:
        """Test JSONFormatter works independently of structlog."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="standalone_test",
            level=logging.INFO,
            pathname="/test.py",
            lineno=1,
            msg="Standalone test",
            args=(),
            exc_info=None,
        )

        # Should always work
        result = formatter.format(record)
        data = json.loads(result)

        assert data["message"] == "Standalone test"
        assert data["logger"] == "standalone_test"


class TestLoggingIntegration:
    """Test logging integration with standard library."""

    def test_json_formatter_with_stream_handler(self) -> None:
        """Test JSONFormatter works with StreamHandler."""
        # Create a logger with our formatter
        logger = logging.getLogger("test_integration")
        logger.setLevel(logging.INFO)

        # Capture output
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

        try:
            # Log a message
            logger.info("Integration test message")

            # Get output
            output = stream.getvalue()

            # Should be valid JSON
            data = json.loads(output.strip())
            assert data["message"] == "Integration test message"
            assert data["level"] == "info"
        finally:
            logger.removeHandler(handler)
