"""Unit tests for Prometheus metrics module."""

import pytest

from src.core.metrics import (
    ACTIVE_SESSIONS,
    AGENT_SPAWNS_TOTAL,
    CLAUDE_API_CALLS_TOTAL,
    COMMAND_EXPANSIONS_TOTAL,
    ERRORS_TOTAL,
    PROMETHEUS_AVAILABLE,
    REQUEST_DURATION,
    REQUESTS_IN_PROGRESS,
    REQUESTS_TOTAL,
    SKILL_INVOCATIONS_TOTAL,
    TOKEN_USAGE,
    TOOL_INVOCATION_DURATION,
    TOOL_INVOCATION_ERRORS,
    TOOL_INVOCATIONS_TOTAL,
    categorize_tool,
    get_metrics,
    get_metrics_content_type,
    init_app_info,
    is_prometheus_available,
    record_claude_api_call,
    record_command_expansion,
    record_stream_completion,
    record_token_usage,
    record_tool_invocation,
    update_active_sessions,
)


class TestMetricsAvailability:
    """Test Prometheus availability detection."""

    def test_prometheus_available_flag(self) -> None:
        """Test PROMETHEUS_AVAILABLE flag is boolean."""
        assert isinstance(PROMETHEUS_AVAILABLE, bool)

    def test_is_prometheus_available_function(self) -> None:
        """Test is_prometheus_available() returns correct value."""
        assert is_prometheus_available() == PROMETHEUS_AVAILABLE


class TestMetricsGeneration:
    """Test metrics generation functions."""

    def test_get_metrics_returns_bytes(self) -> None:
        """Test get_metrics returns bytes."""
        result = get_metrics()
        assert isinstance(result, bytes)

    def test_get_metrics_content_type(self) -> None:
        """Test get_metrics_content_type returns string."""
        content_type = get_metrics_content_type()
        assert isinstance(content_type, str)
        assert "text/" in content_type

    @pytest.mark.skipif(not PROMETHEUS_AVAILABLE, reason="Prometheus not installed")
    def test_metrics_output_has_content(self) -> None:
        """Test metrics output contains metric data when prometheus available."""
        result = get_metrics()
        # Should have actual metric data, not just the fallback message
        assert b"claude8code" in result or len(result) > 100


class TestMetricsRecording:
    """Test metric recording functions."""

    def test_init_app_info(self) -> None:
        """Test init_app_info doesn't raise."""
        # Should work whether prometheus is installed or not
        init_app_info(version="0.1.0")

    def test_record_claude_api_call(self) -> None:
        """Test record_claude_api_call doesn't raise."""
        record_claude_api_call(
            model="claude-sonnet-4-5",
            streaming=False,
            duration=1.5,
        )

    def test_record_claude_api_call_streaming(self) -> None:
        """Test record_claude_api_call with streaming."""
        record_claude_api_call(
            model="claude-opus-4",
            streaming=True,
            duration=5.0,
        )

    def test_record_token_usage(self) -> None:
        """Test record_token_usage doesn't raise."""
        record_token_usage(input_tokens=100, output_tokens=50)

    def test_record_stream_completion(self) -> None:
        """Test record_stream_completion doesn't raise."""
        record_stream_completion(bytes_sent=1024, duration=2.5)

    def test_update_active_sessions(self) -> None:
        """Test update_active_sessions doesn't raise."""
        update_active_sessions(count=10)
        update_active_sessions(count=0)


class TestMetricObjects:
    """Test metric objects have expected interfaces."""

    def test_counter_interface(self) -> None:
        """Test Counter-like metrics have expected methods."""
        # All should have labels() method that returns self-like object
        labeled = REQUESTS_TOTAL.labels(method="POST", endpoint="/test", status_code="200")
        assert hasattr(labeled, "inc")

    def test_histogram_interface(self) -> None:
        """Test Histogram-like metrics have expected methods."""
        labeled = REQUEST_DURATION.labels(method="POST", endpoint="/test")
        assert hasattr(labeled, "observe")

    def test_gauge_interface(self) -> None:
        """Test Gauge-like metrics have expected methods."""
        labeled = REQUESTS_IN_PROGRESS.labels(method="POST", endpoint="/test")
        assert hasattr(labeled, "inc")
        assert hasattr(labeled, "dec")
        assert hasattr(ACTIVE_SESSIONS, "set")


class TestGracefulDegradation:
    """Test graceful degradation when prometheus_client not installed."""

    def test_metrics_work_without_crashing(self) -> None:
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

    def test_chained_calls_work(self) -> None:
        """Test chained label calls work."""
        REQUESTS_TOTAL.labels(method="POST", endpoint="/v1/messages", status_code="200").inc()
        REQUESTS_TOTAL.labels(method="POST", endpoint="/v1/messages", status_code="500").inc()


class TestTrackRequestDecorator:
    """Test the track_request decorator."""

    @pytest.mark.asyncio
    async def test_decorator_tracks_successful_request(self) -> None:
        """Test decorator tracks successful request."""
        from src.core.metrics import track_request

        @track_request(method="GET", endpoint="/test")
        async def sample_handler() -> str:
            return "success"

        result = await sample_handler()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_decorator_tracks_failed_request(self) -> None:
        """Test decorator tracks failed request and re-raises exception."""
        from src.core.metrics import track_request

        @track_request(method="POST", endpoint="/test")
        async def failing_handler() -> str:
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            await failing_handler()

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_metadata(self) -> None:
        """Test decorator preserves function metadata."""
        from src.core.metrics import track_request

        @track_request(method="GET", endpoint="/test")
        async def documented_handler() -> str:
            """Handler with docstring."""
            return "success"

        assert documented_handler.__name__ == "documented_handler"
        assert documented_handler.__doc__ == "Handler with docstring."

    @pytest.mark.asyncio
    async def test_decorator_with_args_and_kwargs(self) -> None:
        """Test decorator works with function args and kwargs."""
        from src.core.metrics import track_request

        @track_request(method="POST", endpoint="/test")
        async def handler_with_args(a: int, b: str, c: bool = False) -> dict[str, object]:
            return {"a": a, "b": b, "c": c}

        result = await handler_with_args(1, "test", c=True)
        assert result == {"a": 1, "b": "test", "c": True}


class TestNoOpMetric:
    """Test the _NoOpMetric fallback class."""

    def test_noop_labels_returns_self(self) -> None:
        """Test that labels() returns a chainable object."""
        if PROMETHEUS_AVAILABLE:
            pytest.skip("Testing no-op only when prometheus not available")

        from src.core.metrics import _NoOpMetric

        metric = _NoOpMetric("test", "description")
        result = metric.labels(key="value")
        assert hasattr(result, "inc")
        assert hasattr(result, "dec")
        assert hasattr(result, "set")
        assert hasattr(result, "observe")

    def test_noop_methods_dont_raise(self) -> None:
        """Test that all no-op methods work without raising."""
        if PROMETHEUS_AVAILABLE:
            pytest.skip("Testing no-op only when prometheus not available")

        from src.core.metrics import _NoOpMetric

        metric = _NoOpMetric("test", "description", ["label"])
        labeled = metric.labels(label="value")
        labeled.inc()
        labeled.inc(5)
        labeled.dec()
        labeled.dec(3)
        labeled.set(10)
        labeled.observe(1.5)
        metric.info({"key": "value"})


class TestCategorizeTool:
    """Test categorize_tool function."""

    def test_task_is_agent(self) -> None:
        """Test Task tool is categorized as agent."""
        assert categorize_tool("Task") == "agent"

    def test_skill_is_skill(self) -> None:
        """Test Skill tool is categorized as skill."""
        assert categorize_tool("Skill") == "skill"

    def test_builtin_tools(self) -> None:
        """Test built-in tools are categorized as builtin."""
        builtin_tools = [
            "Bash",
            "Read",
            "Write",
            "Edit",
            "WebFetch",
            "WebSearch",
            "Glob",
            "Grep",
            "NotebookEdit",
            "TodoWrite",
            "AskUserQuestion",
        ]
        for tool in builtin_tools:
            assert categorize_tool(tool) == "builtin", f"Expected {tool} to be builtin"

    def test_unknown_tool_is_builtin(self) -> None:
        """Test unknown tools default to builtin."""
        assert categorize_tool("UnknownTool") == "builtin"


class TestRecordToolInvocation:
    """Test record_tool_invocation function."""

    def test_records_without_crash(self) -> None:
        """Test recording doesn't crash."""
        record_tool_invocation(tool_name="Read")

    def test_records_with_duration(self) -> None:
        """Test recording with duration."""
        record_tool_invocation(tool_name="Bash", duration=1.5)

    def test_records_with_error(self) -> None:
        """Test recording with error type."""
        record_tool_invocation(
            tool_name="Write",
            error_type="PermissionError",
        )

    def test_records_task_with_subagent(self) -> None:
        """Test recording Task tool with subagent_type."""
        record_tool_invocation(
            tool_name="Task",
            duration=5.0,
            subagent_type="Explore",
        )

    def test_records_skill_with_skill_name(self) -> None:
        """Test recording Skill tool with skill_name."""
        record_tool_invocation(
            tool_name="Skill",
            duration=2.0,
            skill_name="commit",
        )

    def test_records_all_parameters(self) -> None:
        """Test recording with all parameters."""
        record_tool_invocation(
            tool_name="Task",
            duration=10.0,
            error_type=None,
            subagent_type="Plan",
            skill_name=None,
        )


class TestRecordCommandExpansion:
    """Test record_command_expansion function."""

    def test_records_without_crash(self) -> None:
        """Test recording doesn't crash."""
        record_command_expansion("commit")

    def test_records_various_commands(self) -> None:
        """Test recording various command names."""
        commands = ["commit", "help", "review-pr", "custom-command"]
        for cmd in commands:
            record_command_expansion(cmd)


class TestToolInvocationMetricObjects:
    """Test tool invocation metric objects have expected interfaces."""

    def test_tool_invocations_total_interface(self) -> None:
        """Test TOOL_INVOCATIONS_TOTAL has expected interface."""
        labeled = TOOL_INVOCATIONS_TOTAL.labels(tool_name="Read", tool_category="builtin")
        assert hasattr(labeled, "inc")

    def test_tool_invocation_duration_interface(self) -> None:
        """Test TOOL_INVOCATION_DURATION has expected interface."""
        labeled = TOOL_INVOCATION_DURATION.labels(tool_name="Bash", tool_category="builtin")
        assert hasattr(labeled, "observe")

    def test_tool_invocation_errors_interface(self) -> None:
        """Test TOOL_INVOCATION_ERRORS has expected interface."""
        labeled = TOOL_INVOCATION_ERRORS.labels(
            tool_name="Write", tool_category="builtin", error_type="IOError"
        )
        assert hasattr(labeled, "inc")

    def test_agent_spawns_total_interface(self) -> None:
        """Test AGENT_SPAWNS_TOTAL has expected interface."""
        labeled = AGENT_SPAWNS_TOTAL.labels(subagent_type="Explore")
        assert hasattr(labeled, "inc")

    def test_skill_invocations_total_interface(self) -> None:
        """Test SKILL_INVOCATIONS_TOTAL has expected interface."""
        labeled = SKILL_INVOCATIONS_TOTAL.labels(skill_name="commit")
        assert hasattr(labeled, "inc")

    def test_command_expansions_total_interface(self) -> None:
        """Test COMMAND_EXPANSIONS_TOTAL has expected interface."""
        labeled = COMMAND_EXPANSIONS_TOTAL.labels(command_name="help")
        assert hasattr(labeled, "inc")


class TestToolMetricsGracefulDegradation:
    """Test graceful degradation for tool metrics."""

    def test_tool_metrics_work_without_crashing(self) -> None:
        """Test all tool metric operations work without crashing."""
        # This test passes if no exceptions are raised
        TOOL_INVOCATIONS_TOTAL.labels(tool_name="Test", tool_category="builtin").inc()
        TOOL_INVOCATION_DURATION.labels(tool_name="Test", tool_category="builtin").observe(0.5)
        TOOL_INVOCATION_ERRORS.labels(
            tool_name="Test", tool_category="builtin", error_type="TestError"
        ).inc()
        AGENT_SPAWNS_TOTAL.labels(subagent_type="TestAgent").inc()
        SKILL_INVOCATIONS_TOTAL.labels(skill_name="test-skill").inc()
        COMMAND_EXPANSIONS_TOTAL.labels(command_name="test-cmd").inc()
