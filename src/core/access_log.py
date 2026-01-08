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


# SQL schema for tool invocations table
TOOL_INVOCATIONS_SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS tool_invocations_id_seq;

CREATE TABLE IF NOT EXISTS tool_invocations (
    id INTEGER PRIMARY KEY DEFAULT nextval('tool_invocations_id_seq'),
    tool_use_id VARCHAR NOT NULL,
    session_id VARCHAR NOT NULL,
    request_id VARCHAR,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tool_name VARCHAR(64) NOT NULL,
    tool_category VARCHAR(16),
    subagent_type VARCHAR(128),
    skill_name VARCHAR(128),
    duration_seconds FLOAT,
    success BOOLEAN DEFAULT TRUE,
    error_type VARCHAR(128),
    parameters JSON
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tool_invocations_timestamp ON tool_invocations(timestamp);
CREATE INDEX IF NOT EXISTS idx_tool_invocations_tool_name ON tool_invocations(tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_invocations_session_id ON tool_invocations(session_id);
CREATE INDEX IF NOT EXISTS idx_tool_invocations_tool_use_id ON tool_invocations(tool_use_id);
CREATE INDEX IF NOT EXISTS idx_tool_invocations_subagent_type ON tool_invocations(subagent_type);
CREATE INDEX IF NOT EXISTS idx_tool_invocations_skill_name ON tool_invocations(skill_name);
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
        self._tool_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
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
            self._conn.execute(TOOL_INVOCATIONS_SCHEMA)
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
        await self._flush_tool_invocations()

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

    async def log_tool_invocation(
        self,
        tool_use_id: str,
        session_id: str,
        tool_name: str,
        tool_category: str,
        duration_seconds: float | None = None,
        subagent_type: str | None = None,
        skill_name: str | None = None,
        success: bool = True,
        error_type: str | None = None,
        parameters: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        """Log a tool invocation.

        Args:
            tool_use_id: Unique ID for this tool invocation
            session_id: Session identifier
            tool_name: Name of the tool invoked
            tool_category: Category (agent, skill, builtin)
            duration_seconds: Duration of invocation
            subagent_type: For Task tool, the subagent type
            skill_name: For Skill tool, the skill name
            success: Whether invocation succeeded
            error_type: Error type if failed
            parameters: Sanitized tool parameters (JSON)
            request_id: Optional request ID for correlation
        """
        if not self._running or not DUCKDB_AVAILABLE:
            return

        import json

        record = {
            "tool_use_id": tool_use_id,
            "session_id": session_id,
            "request_id": request_id,
            "timestamp": datetime.now(),
            "tool_name": tool_name,
            "tool_category": tool_category,
            "subagent_type": subagent_type,
            "skill_name": skill_name,
            "duration_seconds": duration_seconds,
            "success": success,
            "error_type": error_type,
            "parameters": json.dumps(parameters) if parameters else None,
        }

        await self._tool_queue.put(record)

        # Flush if batch is full
        if self._tool_queue.qsize() >= self._batch_size:
            await self._flush_tool_invocations()

    async def _flush_loop(self) -> None:
        """Background task to flush logs periodically."""
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush()
                await self._flush_tool_invocations()
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

    async def _flush_tool_invocations(self) -> None:
        """Flush queued tool invocation records to database."""
        if not self._conn or self._tool_queue.empty():
            return

        records = []
        try:
            while not self._tool_queue.empty():
                records.append(self._tool_queue.get_nowait())
        except asyncio.QueueEmpty:
            pass

        if not records:
            return

        try:
            # Batch insert tool invocations
            self._conn.executemany(
                """
                INSERT INTO tool_invocations (
                    tool_use_id, session_id, request_id, timestamp, tool_name,
                    tool_category, subagent_type, skill_name, duration_seconds,
                    success, error_type, parameters
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        r["tool_use_id"],
                        r["session_id"],
                        r["request_id"],
                        r["timestamp"],
                        r["tool_name"],
                        r["tool_category"],
                        r["subagent_type"],
                        r["skill_name"],
                        r["duration_seconds"],
                        r["success"],
                        r["error_type"],
                        r["parameters"],
                    )
                    for r in records
                ],
            )
            logger.debug("Flushed %d tool invocation records", len(records))
        except Exception as e:
            logger.error("Failed to write tool invocations: %s", e)

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

            # Get tool invocation stats
            tool_count = self._conn.execute("SELECT COUNT(*) FROM tool_invocations").fetchone()[0]

            tool_stats = self._conn.execute(
                """
                SELECT tool_name, COUNT(*) as count
                FROM tool_invocations
                GROUP BY tool_name
                ORDER BY count DESC
                LIMIT 10
                """
            ).fetchall()

            agent_stats = self._conn.execute(
                """
                SELECT subagent_type, COUNT(*) as count
                FROM tool_invocations
                WHERE subagent_type IS NOT NULL
                GROUP BY subagent_type
                ORDER BY count DESC
                LIMIT 5
                """
            ).fetchall()

            skill_stats = self._conn.execute(
                """
                SELECT skill_name, COUNT(*) as count
                FROM tool_invocations
                WHERE skill_name IS NOT NULL
                GROUP BY skill_name
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
                "tool_invocations": {
                    "total": tool_count,
                    "by_tool": [{"tool": t, "count": c} for t, c in tool_stats],
                    "by_agent": [{"agent": a, "count": c} for a, c in agent_stats],
                    "by_skill": [{"skill": s, "count": c} for s, c in skill_stats],
                    "queue_size": self._tool_queue.qsize(),
                },
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


async def log_tool_invocation(
    tool_use_id: str,
    session_id: str,
    tool_name: str,
    tool_category: str,
    duration_seconds: float | None = None,
    subagent_type: str | None = None,
    skill_name: str | None = None,
    success: bool = True,
    error_type: str | None = None,
    parameters: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> None:
    """Log a tool invocation to the access log.

    Convenience function that uses the global writer.

    Args:
        tool_use_id: Unique ID for this tool invocation
        session_id: Session identifier
        tool_name: Name of the tool invoked
        tool_category: Category (agent, skill, builtin)
        duration_seconds: Duration of invocation
        subagent_type: For Task tool, the subagent type
        skill_name: For Skill tool, the skill name
        success: Whether invocation succeeded
        error_type: Error type if failed
        parameters: Sanitized tool parameters (JSON)
        request_id: Optional request ID for correlation
    """
    if _writer:
        await _writer.log_tool_invocation(
            tool_use_id=tool_use_id,
            session_id=session_id,
            tool_name=tool_name,
            tool_category=tool_category,
            duration_seconds=duration_seconds,
            subagent_type=subagent_type,
            skill_name=skill_name,
            success=success,
            error_type=error_type,
            parameters=parameters,
            request_id=request_id,
        )
