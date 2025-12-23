"""Unit tests for Prometheus metrics module."""

import pytest

from src.core.metrics import (
    PROMETHEUS_AVAILABLE,
    is_prometheus_available,
    get_metrics,
    get_metrics_content_type,
    init_app_info,
    record_claude_api_call,
    record_token_usage,
    record_stream_completion,
    update_active_sessions,
    REQUESTS_TOTAL,
    REQUEST_DURATION,
    REQUESTS_IN_PROGRESS,
    ERRORS_TOTAL,
    ACTIVE_SESSIONS,
    CLAUDE_API_CALLS_TOTAL,
    TOKEN_USAGE,
)


class TestMetricsAvailability:
    """Test Prometheus availability detection."""

    def test_prometheus_available_flag(self):
        """Test PROMETHEUS_AVAILABLE flag is boolean."""
        assert isinstance(PROMETHEUS_AVAILABLE, bool)

    def test_is_prometheus_available_function(self):
        """Test is_prometheus_available() returns correct value."""
        assert is_prometheus_available() == PROMETHEUS_AVAILABLE


class TestMetricsGeneration:
    """Test metrics generation functions."""

    def test_get_metrics_returns_bytes(self):
        """Test get_metrics returns bytes."""
        result = get_metrics()
        assert isinstance(result, bytes)

    def test_get_metrics_content_type(self):
        """Test get_metrics_content_type returns string."""
        content_type = get_metrics_content_type()
        assert isinstance(content_type, str)
        assert "text/" in content_type

    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus not installed")
    def test_metrics_output_has_content(self):
        """Test metrics output contains metric data when prometheus available."""
        result = get_metrics()
        # Should have actual metric data, not just the fallback message
        assert b"claude8code" in result or len(result) > 100


class TestMetricsRecording:
    """Test metric recording functions."""

    def test_init_app_info(self):
        """Test init_app_info doesn't raise."""
        # Should work whether prometheus is installed or not
        init_app_info(version="0.1.0")

    def test_record_claude_api_call(self):
        """Test record_claude_api_call doesn't raise."""
        record_claude_api_call(
            model="claude-sonnet-4-5",
            streaming=False,
            duration=1.5,
        )

    def test_record_claude_api_call_streaming(self):
        """Test record_claude_api_call with streaming."""
        record_claude_api_call(
            model="claude-opus-4",
            streaming=True,
            duration=5.0,
        )

    def test_record_token_usage(self):
        """Test record_token_usage doesn't raise."""
        record_token_usage(input_tokens=100, output_tokens=50)

    def test_record_stream_completion(self):
        """Test record_stream_completion doesn't raise."""
        record_stream_completion(bytes_sent=1024, duration=2.5)

    def test_update_active_sessions(self):
        """Test update_active_sessions doesn't raise."""
        update_active_sessions(count=10)
        update_active_sessions(count=0)


class TestMetricObjects:
    """Test metric objects have expected interfaces."""

    def test_counter_interface(self):
        """Test Counter-like metrics have expected methods."""
        # All should have labels() method that returns self-like object
        labeled = REQUESTS_TOTAL.labels(method="POST", endpoint="/test", status_code="200")
        assert hasattr(labeled, "inc")

    def test_histogram_interface(self):
        """Test Histogram-like metrics have expected methods."""
        labeled = REQUEST_DURATION.labels(method="POST", endpoint="/test")
        assert hasattr(labeled, "observe")

    def test_gauge_interface(self):
        """Test Gauge-like metrics have expected methods."""
        labeled = REQUESTS_IN_PROGRESS.labels(method="POST", endpoint="/test")
        assert hasattr(labeled, "inc")
        assert hasattr(labeled, "dec")
        assert hasattr(ACTIVE_SESSIONS, "set")


class TestGracefulDegradation:
    """Test graceful degradation when prometheus_client not installed."""

    def test_metrics_work_without_crashing(self):
        """Test all metric operations work without crashing."""
        # This test passes if no exceptions are raised
        REQUESTS_TOTAL.labels(method="GET", endpoint="/test", status_code="200").inc()
        REQUEST_DURATION.labels(method="GET", endpoint="/test").observe(0.5)
        REQUESTS_IN_PROGRESS.labels(method="GET", endpoint="/test").inc()
        REQUESTS_IN_PROGRESS.labels(method="GET", endpoint="/test").dec()
        ERRORS_TOTAL.labels(error_type="ValueError").inc()
        ACTIVE_SESSIONS.set(5)
        CLAUDE_API_CALLS_TOTAL.labels(model="test", streaming="false").inc()
        TOKEN_USAGE.labels(type="input").inc(100)
        TOKEN_USAGE.labels(type="output").inc(50)

    def test_chained_calls_work(self):
        """Test chained label calls work."""
        REQUESTS_TOTAL.labels(method="POST", endpoint="/v1/messages", status_code="200").inc()
        REQUESTS_TOTAL.labels(method="POST", endpoint="/v1/messages", status_code="500").inc()
