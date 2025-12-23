"""Core infrastructure for claude8code.

This package contains shared infrastructure components:
- config: Settings and configuration
- context: Request context propagation
- metrics: Prometheus metrics
- access_log: DuckDB access logging
"""

from .config import (
    Settings,
    settings,
    get_settings,
    reload_settings,
    SDKMessageMode,
    SystemPromptMode,
)

from .context import (
    RequestContext,
    get_context,
    set_context,
    reset_context,
    create_context,
    RequestContextManager,
)

from .metrics import (
    init_app_info,
    get_metrics,
    get_metrics_content_type,
    record_token_usage,
    record_claude_api_call,
    record_stream_completion,
    update_active_sessions,
    is_prometheus_available,
    REQUESTS_TOTAL,
    REQUEST_DURATION,
    REQUESTS_IN_PROGRESS,
    ERRORS_TOTAL,
)

from .access_log import (
    AccessLogWriter,
    get_access_log_writer,
    init_access_log,
    shutdown_access_log,
    log_request,
    is_access_log_available,
)

__all__ = [
    # Config
    "Settings",
    "settings",
    "get_settings",
    "reload_settings",
    "SDKMessageMode",
    "SystemPromptMode",
    # Context
    "RequestContext",
    "get_context",
    "set_context",
    "reset_context",
    "create_context",
    "RequestContextManager",
    # Metrics
    "init_app_info",
    "get_metrics",
    "get_metrics_content_type",
    "record_token_usage",
    "record_claude_api_call",
    "record_stream_completion",
    "update_active_sessions",
    "is_prometheus_available",
    "REQUESTS_TOTAL",
    "REQUEST_DURATION",
    "REQUESTS_IN_PROGRESS",
    "ERRORS_TOTAL",
    # Access Log
    "AccessLogWriter",
    "get_access_log_writer",
    "init_access_log",
    "shutdown_access_log",
    "log_request",
    "is_access_log_available",
]
