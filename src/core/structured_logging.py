"""Structured logging setup for Loki integration.

Uses structlog for JSON-formatted logs that can be scraped by Loki/Promtail.
Falls back to standard logging with JSON-like format if structlog is not installed.

This module provides graceful degradation - the server works without structlog.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# Graceful degradation for structlog
try:
    import structlog
    from structlog.processors import JSONRenderer
    from structlog.stdlib import BoundLogger

    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False
    structlog = None  # type: ignore[assignment]


class JSONFormatter(logging.Formatter):
    """JSON formatter for standard logging (fallback when structlog unavailable).

    Outputs logs in JSON format compatible with Loki/Promtail parsing.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "extra") and record.extra:
            log_data.update(record.extra)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


def configure_structured_logging(
    log_level: str = "INFO",
    json_format: bool = True,
) -> None:
    """Configure structured logging for the application.

    Should be called once at application startup.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        json_format: If True, output JSON logs (for Loki). If False, human-readable.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    if STRUCTLOG_AVAILABLE and structlog is not None:
        # Configure structlog processors
        shared_processors: list[Any] = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_logger_name,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
        ]

        if json_format:
            # JSON output for Loki
            shared_processors.append(
                structlog.processors.format_exc_info,
            )
            renderer: Any = JSONRenderer()
        else:
            # Human-readable output for development
            renderer = structlog.dev.ConsoleRenderer()

        structlog.configure(
            processors=shared_processors + [renderer],
            wrapper_class=BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Configure standard logging to use structlog
        logging.basicConfig(
            format="%(message)s",
            level=level,
            handlers=[logging.StreamHandler(sys.stdout)],
        )
    else:
        # Fallback to standard logging with JSON format
        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Add JSON-formatted handler
        handler = logging.StreamHandler(sys.stdout)

        if json_format:
            handler.setFormatter(JSONFormatter())
        else:
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                    datefmt="%Y-%m-%dT%H:%M:%S",
                )
            )

        root_logger.addHandler(handler)


def get_logger(name: str) -> Any:
    """Get a logger instance.

    Returns structlog logger if available, standard logger otherwise.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Logger instance
    """
    if STRUCTLOG_AVAILABLE and structlog is not None:
        return structlog.get_logger(name)
    return logging.getLogger(name)


def bind_context(**kwargs: Any) -> None:
    """Bind context variables to all subsequent log messages.

    Only works with structlog. No-op if structlog unavailable.

    Args:
        **kwargs: Context variables to bind
    """
    if STRUCTLOG_AVAILABLE and structlog is not None:
        structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear bound context variables.

    Only works with structlog. No-op if structlog unavailable.
    """
    if STRUCTLOG_AVAILABLE and structlog is not None:
        structlog.contextvars.clear_contextvars()


def is_structlog_available() -> bool:
    """Check if structlog is available.

    Returns:
        True if structlog is installed
    """
    return STRUCTLOG_AVAILABLE
