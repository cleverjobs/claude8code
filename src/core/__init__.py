"""Core infrastructure for claude8code.

This package contains shared infrastructure components:
- config: Settings and configuration
- context: Request context propagation
- metrics: Prometheus metrics
- access_log: DuckDB access logging
"""

from .access_log import (
    AccessLogWriter,
    get_access_log_writer,
    init_access_log,
    is_access_log_available,
    log_request,
    shutdown_access_log,
)
from .config import (
    SDKMessageMode,
    Settings,
    SystemPromptMode,
    get_settings,
    reload_settings,
    settings,
)
from .context import (
    RequestContext,
    RequestContextManager,
    create_context,
    get_context,
    reset_context,
    set_context,
)
from .metrics import (
    ERRORS_TOTAL,
    REQUEST_DURATION,
    REQUESTS_IN_PROGRESS,
    REQUESTS_TOTAL,
    get_metrics,
    get_metrics_content_type,
    init_app_info,
    is_prometheus_available,
    record_claude_api_call,
    record_stream_completion,
    record_token_usage,
    update_active_sessions,
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
