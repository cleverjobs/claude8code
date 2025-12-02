"""Prometheus metrics for claude8code server.

This module provides instrumentation for monitoring the server's
performance and usage through Prometheus-compatible metrics.
"""

from __future__ import annotations

import time
from functools import wraps
from typing import Callable, Any

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
)


# Application info
APP_INFO = Info(
    "claude8code",
    "Information about the claude8code server"
)

# Request metrics
REQUESTS_TOTAL = Counter(
    "claude8code_requests_total",
    "Total number of requests processed",
    ["method", "endpoint", "status_code"]
)

REQUEST_DURATION = Histogram(
    "claude8code_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, float("inf"))
)

REQUESTS_IN_PROGRESS = Gauge(
    "claude8code_requests_in_progress",
    "Number of requests currently being processed",
    ["method", "endpoint"]
)

# Error metrics
ERRORS_TOTAL = Counter(
    "claude8code_errors_total",
    "Total number of errors",
    ["error_type"]
)

# Session metrics
ACTIVE_SESSIONS = Gauge(
    "claude8code_active_sessions",
    "Number of active sessions"
)

# Claude API metrics
CLAUDE_API_CALLS_TOTAL = Counter(
    "claude8code_claude_api_calls_total",
    "Total number of calls to Claude API",
    ["model", "streaming"]
)

CLAUDE_API_DURATION = Histogram(
    "claude8code_claude_api_duration_seconds",
    "Duration of Claude API calls in seconds",
    ["model"],
    buckets=(1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, float("inf"))
)

TOKEN_USAGE = Counter(
    "claude8code_tokens_total",
    "Total tokens used",
    ["type"]  # "input" or "output"
)


def init_app_info(version: str = "0.1.0") -> None:
    """Initialize application info metric."""
    APP_INFO.info({
        "version": version,
        "name": "claude8code",
    })


def track_request(method: str, endpoint: str):
    """Decorator to track request metrics.

    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: API endpoint path
    """
    def decorator(func: Callable) -> Callable:
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
                    method=method,
                    endpoint=endpoint,
                    status_code=str(status_code)
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
    CLAUDE_API_CALLS_TOTAL.labels(
        model=model,
        streaming=str(streaming).lower()
    ).inc()
    CLAUDE_API_DURATION.labels(model=model).observe(duration)


def record_token_usage(input_tokens: int, output_tokens: int) -> None:
    """Record token usage metrics.

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
    """
    TOKEN_USAGE.labels(type="input").inc(input_tokens)
    TOKEN_USAGE.labels(type="output").inc(output_tokens)


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
    return generate_latest(REGISTRY)


def get_metrics_content_type() -> str:
    """Get the content type for Prometheus metrics.

    Returns:
        Content type string
    """
    return CONTENT_TYPE_LATEST
