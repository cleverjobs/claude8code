"""DuckDB access logging for claude8code.

Provides embedded analytics database for request logging and querying.
Uses graceful degradation - if DuckDB is not installed, logging is silently skipped.

Example queries:
    # Total requests by model
    SELECT model, COUNT(*) as count FROM access_logs GROUP BY model;

    # Average duration by endpoint
    SELECT path, AVG(duration_ms) as avg_ms FROM access_logs GROUP BY path;

    # Error rate
    SELECT
        COUNT(*) FILTER (WHERE error IS NOT NULL) * 100.0 / COUNT(*) as error_rate
    FROM access_logs;

    # Token usage by hour
    SELECT
        DATE_TRUNC('hour', timestamp) as hour,
        SUM(input_tokens) as input_tokens,
        SUM(output_tokens) as output_tokens
    FROM access_logs
    GROUP BY 1 ORDER BY 1;
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .context import RequestContext

logger = logging.getLogger(__name__)


# Graceful degradation: check if DuckDB is available
try:
    import duckdb

    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None  # type: ignore[assignment]
    logger.debug("DuckDB not installed, access logging disabled")


# SQL schema for access logs table
# DuckDB requires SEQUENCE + DEFAULT nextval() for auto-increment IDs
ACCESS_LOGS_SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS access_logs_id_seq;

CREATE TABLE IF NOT EXISTS access_logs (
    id INTEGER PRIMARY KEY DEFAULT nextval('access_logs_id_seq'),
    request_id VARCHAR NOT NULL,
    session_id VARCHAR,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    method VARCHAR(10),
    path VARCHAR(512),
    model VARCHAR(128),
    client_ip VARCHAR(45),
    user_agent VARCHAR(512),
    status_code INTEGER,
    duration_ms FLOAT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    stream BOOLEAN DEFAULT FALSE,
    error VARCHAR(1024),
    disconnect_reason VARCHAR(64)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_access_logs_timestamp ON access_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_access_logs_model ON access_logs(model);
CREATE INDEX IF NOT EXISTS idx_access_logs_path ON access_logs(path);
CREATE INDEX IF NOT EXISTS idx_access_logs_request_id ON access_logs(request_id);
"""


class AccessLogWriter:
    """Writes access logs to DuckDB.

    Thread-safe writer that batches writes for performance.

    Usage:
        writer = AccessLogWriter("data/access_logs.duckdb")
        await writer.start()

        # Log a request
        await writer.log(context)

        await writer.stop()
    """

    def __init__(
        self,
        db_path: str | Path,
        batch_size: int = 100,
        flush_interval_seconds: float = 5.0,
    ):
        """Initialize access log writer.

        Args:
            db_path: Path to DuckDB database file
            batch_size: Number of records to batch before writing
            flush_interval_seconds: Maximum time between flushes
        """
        self._db_path = Path(db_path)
        self._batch_size = batch_size
        self._flush_interval = flush_interval_seconds

        self._conn: Any = None
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._flush_task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        """Start the access log writer."""
        if not DUCKDB_AVAILABLE:
            logger.info("DuckDB not available, access logging disabled")
            return

        if self._running:
            return

        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        # Connect to DuckDB
        try:
            self._conn = duckdb.connect(str(self._db_path))
            self._conn.execute(ACCESS_LOGS_SCHEMA)
            logger.info("Access log database initialized: %s", self._db_path)
        except Exception as e:
            logger.error("Failed to initialize access log database: %s", e)
            self._conn = None
            return

        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        """Stop the writer and flush remaining logs."""
        if not self._running:
            return

        self._running = False

        # Cancel flush task
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        # Flush remaining logs
        await self._flush()

        # Close connection
        if self._conn:
            self._conn.close()
            self._conn = None

        logger.info("Access log writer stopped")

    async def log(self, context: RequestContext, status_code: int = 200) -> None:
        """Log a request from context.

        Args:
            context: Request context with timing and metadata
            status_code: HTTP response status code
        """
        if not self._running or not DUCKDB_AVAILABLE:
            return

        record = {
            "request_id": context.request_id,
            "session_id": context.session_id,
            "timestamp": datetime.now(),
            "method": context.method,
            "path": context.path,
            "model": context.model,
            "client_ip": context.client_ip,
            "user_agent": context.user_agent,
            "status_code": status_code,
            "duration_ms": context.duration_ms,
            "input_tokens": context.tokens_in,
            "output_tokens": context.tokens_out,
            "stream": context.stream,
            "error": context.error,
            "disconnect_reason": context.disconnect_reason,
        }

        await self._queue.put(record)

        # Flush if batch is full
        if self._queue.qsize() >= self._batch_size:
            await self._flush()

    async def _flush_loop(self) -> None:
        """Background task to flush logs periodically."""
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Error in access log flush loop: %s", e)

    async def _flush(self) -> None:
        """Flush queued records to database."""
        if not self._conn or self._queue.empty():
            return

        records = []
        try:
            while not self._queue.empty():
                records.append(self._queue.get_nowait())
        except asyncio.QueueEmpty:
            pass

        if not records:
            return

        try:
            # Batch insert using prepared statement
            self._conn.executemany(
                """
                INSERT INTO access_logs (
                    request_id, session_id, timestamp, method, path,
                    model, client_ip, user_agent, status_code, duration_ms,
                    input_tokens, output_tokens, stream, error, disconnect_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        r["request_id"],
                        r["session_id"],
                        r["timestamp"],
                        r["method"],
                        r["path"],
                        r["model"],
                        r["client_ip"],
                        r["user_agent"],
                        r["status_code"],
                        r["duration_ms"],
                        r["input_tokens"],
                        r["output_tokens"],
                        r["stream"],
                        r["error"],
                        r["disconnect_reason"],
                    )
                    for r in records
                ],
            )
            logger.debug("Flushed %d access log records", len(records))
        except Exception as e:
            logger.error("Failed to write access logs: %s", e)

    def query(self, sql: str) -> list[dict[str, Any]]:
        """Execute a query and return results as list of dicts.

        Args:
            sql: SQL query to execute

        Returns:
            List of result rows as dictionaries
        """
        if not self._conn:
            return []

        try:
            result = self._conn.execute(sql).fetchall()
            columns = [desc[0] for desc in self._conn.description]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error("Query error: %s", e)
            return []

    def get_stats(self) -> dict[str, Any]:
        """Get access log statistics.

        Returns:
            Dictionary with stats about the access log database
        """
        if not self._conn:
            return {"available": False, "reason": "DuckDB not connected"}

        try:
            # Get basic stats
            row_count = self._conn.execute("SELECT COUNT(*) FROM access_logs").fetchone()[0]

            date_range = self._conn.execute(
                "SELECT MIN(timestamp), MAX(timestamp) FROM access_logs"
            ).fetchone()

            model_stats = self._conn.execute(
                """
                SELECT model, COUNT(*) as count
                FROM access_logs
                WHERE model IS NOT NULL
                GROUP BY model
                ORDER BY count DESC
                LIMIT 5
                """
            ).fetchall()

            return {
                "available": True,
                "db_path": str(self._db_path),
                "total_requests": row_count,
                "date_range": {
                    "from": date_range[0].isoformat() if date_range[0] else None,
                    "to": date_range[1].isoformat() if date_range[1] else None,
                },
                "top_models": [{"model": m, "count": c} for m, c in model_stats],
                "queue_size": self._queue.qsize(),
            }
        except Exception as e:
            return {"available": False, "reason": str(e)}


# Global access log writer instance
_writer: AccessLogWriter | None = None


def get_access_log_writer() -> AccessLogWriter | None:
    """Get the global access log writer instance.

    Returns:
        AccessLogWriter or None if not initialized
    """
    return _writer


async def init_access_log(db_path: str | Path | None = None) -> AccessLogWriter | None:
    """Initialize the global access log writer.

    Args:
        db_path: Path to database file (uses settings default if None)

    Returns:
        AccessLogWriter or None if DuckDB not available
    """
    global _writer

    if not DUCKDB_AVAILABLE:
        logger.info("DuckDB not installed, skipping access log initialization")
        return None

    if _writer is not None:
        return _writer

    # Get path from settings if not provided
    if db_path is None:
        from settings import settings

        db_path = settings().observability.access_logs_path

    _writer = AccessLogWriter(db_path)
    await _writer.start()
    return _writer


async def shutdown_access_log() -> None:
    """Shutdown the global access log writer."""
    global _writer

    if _writer:
        await _writer.stop()
        _writer = None


async def log_request(context: RequestContext, status_code: int = 200) -> None:
    """Log a request to the access log.

    Convenience function that uses the global writer.

    Args:
        context: Request context
        status_code: HTTP status code
    """
    if _writer:
        await _writer.log(context, status_code)


def is_access_log_available() -> bool:
    """Check if access logging is available and enabled."""
    return DUCKDB_AVAILABLE and _writer is not None
