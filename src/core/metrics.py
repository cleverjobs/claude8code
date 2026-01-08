"""Prometheus metrics for claude8code server.

This module provides instrumentation for monitoring the server's
performance and usage through Prometheus-compatible metrics.

Uses graceful degradation: server works even without prometheus_client installed.
"""

from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable

# Graceful degradation: provide no-op implementations if prometheus_client unavailable
try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

    # No-op implementations for when prometheus_client is not installed
    class _NoOpMetric:
        """No-op metric that accepts any arguments and does nothing."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def labels(self, **kwargs: Any) -> "_NoOpMetric":
            return self

        def inc(self, value: float = 1) -> None:
            pass

        def dec(self, value: float = 1) -> None:
            pass

        def set(self, value: float) -> None:
            pass

        def observe(self, value: float) -> None:
            pass

        def info(self, val: dict[str, str]) -> None:
            pass

    # Type aliases for graceful degradation
    Counter = _NoOpMetric  # type: ignore[misc,assignment]
    Histogram = _NoOpMetric  # type: ignore[misc,assignment]
    Gauge = _NoOpMetric  # type: ignore[misc,assignment]
    Info = _NoOpMetric  # type: ignore[misc,assignment]
    REGISTRY = None  # type: ignore[assignment]
    CONTENT_TYPE_LATEST = "text/plain; charset=utf-8"

    def generate_latest(registry: Any = None, escaping: str = "") -> bytes:  # type: ignore[misc]
        """No-op metrics generation."""
        return b"# Prometheus not installed. pip install 'claude8code[metrics]'\n"


# Application info
APP_INFO = Info("claude8code", "Information about the claude8code server")

# Request metrics
REQUESTS_TOTAL = Counter(
    "claude8code_requests_total",
    "Total number of requests processed",
    ["method", "endpoint", "status_code"],
)

REQUEST_DURATION = Histogram(
    "claude8code_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float("inf")),
)

REQUESTS_IN_PROGRESS = Gauge(
    "claude8code_requests_in_progress",
    "Number of requests currently being processed",
    ["method", "endpoint"],
)

# Error metrics
ERRORS_TOTAL = Counter("claude8code_errors_total", "Total number of errors", ["error_type"])

# Session metrics
ACTIVE_SESSIONS = Gauge("claude8code_active_sessions", "Number of active sessions")

# Claude API metrics
CLAUDE_API_CALLS_TOTAL = Counter(
    "claude8code_claude_api_calls_total",
    "Total number of calls to Claude API",
    ["model", "streaming"],
)

CLAUDE_API_DURATION = Histogram(
    "claude8code_claude_api_duration_seconds",
    "Duration of Claude API calls in seconds",
    ["model"],
    buckets=(1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, float("inf")),
)

TOKEN_USAGE = Counter(
    "claude8code_tokens_total",
    "Total tokens used",
    ["type"],  # "input" or "output"
)

# Stream metrics
STREAM_BYTES_TOTAL = Counter(
    "claude8code_stream_bytes_total", "Total bytes sent in streaming responses"
)

STREAM_DURATION = Histogram(
    "claude8code_stream_duration_seconds",
    "Duration of streaming responses in seconds",
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, float("inf")),
)

# Tool invocation metrics
TOOL_INVOCATIONS_TOTAL = Counter(
    "claude8code_tool_invocations_total",
    "Total tool invocations",
    ["tool_name", "tool_category"],  # tool_category: agent, skill, builtin
)

TOOL_INVOCATION_DURATION = Histogram(
    "claude8code_tool_invocation_duration_seconds",
    "Duration of tool invocations in seconds",
    ["tool_name", "tool_category"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float("inf")),
)

TOOL_INVOCATION_ERRORS = Counter(
    "claude8code_tool_invocation_errors_total",
    "Total tool invocation errors",
    ["tool_name", "tool_category", "error_type"],
)

# Agent-specific metrics (Task tool)
AGENT_SPAWNS_TOTAL = Counter(
    "claude8code_agent_spawns_total",
    "Total agent (subagent) spawns via Task tool",
    ["subagent_type"],
)

# Skill-specific metrics (Skill tool)
SKILL_INVOCATIONS_TOTAL = Counter(
    "claude8code_skill_invocations_total",
    "Total skill invocations via Skill tool",
    ["skill_name"],
)

# Command expansion metrics (slash commands)
COMMAND_EXPANSIONS_TOTAL = Counter(
    "claude8code_command_expansions_total",
    "Total command expansions (slash commands)",
    ["command_name"],
)


def init_app_info(version: str = "0.1.0") -> None:
    """Initialize application info metric."""
    APP_INFO.info(
        {
            "version": version,
            "name": "claude8code",
            "prometheus_available": str(PROMETHEUS_AVAILABLE).lower(),
        }
    )


def track_request(method: str, endpoint: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to track request metrics.

    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint path
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).inc()
            start_time = time.perf_counter()
            status_code = 200

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status_code = 500
                ERRORS_TOTAL.labels(error_type=type(e).__name__).inc()
                raise
            finally:
                duration = time.perf_counter() - start_time
                REQUESTS_IN_PROGRESS.labels(method=method, endpoint=endpoint).dec()
                REQUESTS_TOTAL.labels(
                    method=method, endpoint=endpoint, status_code=str(status_code)
                ).inc()
                REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

        return wrapper

    return decorator


def record_claude_api_call(model: str, streaming: bool, duration: float) -> None:
    """Record metrics for a Claude API call.

    Args:
        model: Model ID used
        streaming: Whether this was a streaming request
        duration: Duration of the API call in seconds
    """
    CLAUDE_API_CALLS_TOTAL.labels(model=model, streaming=str(streaming).lower()).inc()
    CLAUDE_API_DURATION.labels(model=model).observe(duration)


def record_token_usage(input_tokens: int, output_tokens: int) -> None:
    """Record token usage metrics.

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
    """
    TOKEN_USAGE.labels(type="input").inc(input_tokens)
    TOKEN_USAGE.labels(type="output").inc(output_tokens)


def record_stream_completion(bytes_sent: int, duration: float) -> None:
    """Record metrics for a completed stream.

    Args:
        bytes_sent: Total bytes sent
        duration: Duration of the stream in seconds
    """
    STREAM_BYTES_TOTAL.inc(bytes_sent)
    STREAM_DURATION.observe(duration)


def update_active_sessions(count: int) -> None:
    """Update the active sessions gauge.

    Args:
        count: Current number of active sessions
    """
    ACTIVE_SESSIONS.set(count)


def get_metrics() -> bytes:
    """Generate Prometheus metrics output.

    Returns:
        Prometheus metrics in text format
    """
    result: bytes = generate_latest(REGISTRY)
    return result


def get_metrics_content_type() -> str:
    """Get the content type for Prometheus metrics.

    Returns:
        Content type string
    """
    result: str = CONTENT_TYPE_LATEST
    return result


def is_prometheus_available() -> bool:
    """Check if Prometheus client is available.

    Returns:
        True if prometheus_client is installed
    """
    return PROMETHEUS_AVAILABLE


def categorize_tool(tool_name: str) -> str:
    """Categorize tool into agent, skill, or builtin.

    Args:
        tool_name: Name of the tool

    Returns:
        Category: "agent", "skill", or "builtin"
    """
    if tool_name == "Task":
        return "agent"
    elif tool_name == "Skill":
        return "skill"
    else:
        return "builtin"


def record_tool_invocation(
    tool_name: str,
    duration: float | None = None,
    error_type: str | None = None,
    subagent_type: str | None = None,
    skill_name: str | None = None,
) -> None:
    """Record metrics for a tool invocation.

    Args:
        tool_name: Name of the tool invoked
        duration: Duration of invocation in seconds (None for pre-hook)
        error_type: Type of error if invocation failed
        subagent_type: For Task tool, the subagent type
        skill_name: For Skill tool, the skill name
    """
    category = categorize_tool(tool_name)

    # Always increment invocation counter
    TOOL_INVOCATIONS_TOTAL.labels(tool_name=tool_name, tool_category=category).inc()

    # Record duration if provided (post-hook)
    if duration is not None:
        TOOL_INVOCATION_DURATION.labels(tool_name=tool_name, tool_category=category).observe(
            duration
        )

    # Record error if occurred
    if error_type:
        TOOL_INVOCATION_ERRORS.labels(
            tool_name=tool_name, tool_category=category, error_type=error_type
        ).inc()

    # Track specific agent/skill invocations
    if tool_name == "Task" and subagent_type:
        AGENT_SPAWNS_TOTAL.labels(subagent_type=subagent_type).inc()
    elif tool_name == "Skill" and skill_name:
        SKILL_INVOCATIONS_TOTAL.labels(skill_name=skill_name).inc()


def record_command_expansion(command_name: str) -> None:
    """Record metrics for a slash command expansion.

    Args:
        command_name: Name of the command that was expanded
    """
    COMMAND_EXPANSIONS_TOTAL.labels(command_name=command_name).inc()
