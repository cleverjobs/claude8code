# Claude8Code Enhancement Features

Features adopted from ccproxy-api analysis for claude8code.

**Scope:** Anthropic ecosystem only (no OpenAI compatibility)

---

## Overview

| Feature | Purpose | Priority |
|---------|---------|----------|
| Graceful Degradation | Server works without optional deps | 1 |
| TOML Configuration | `settings/settings.toml` + `.env` for secrets | 2 |
| Request Context | Correlation IDs for debugging | 3 |
| Streaming Wrapper | Auto-logging on completion | 4 |
| SDK Message Modes | forward/formatted/ignore | 5 |
| Session Pooling | Pool with mandatory clear | 6 |
| DuckDB Access Logs | Usage analytics | 7 |

---

## 1. Graceful Degradation

Server functions even without optional dependencies by providing no-op fallbacks.

**Pattern:**
```python
try:
    from prometheus_client import Counter, Histogram
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    class _NoOpMetric:
        def __init__(self, *args, **kwargs): pass
        def labels(self, **kwargs): return self
        def inc(self, value=1): pass
        def observe(self, value): pass
    Counter = Histogram = _NoOpMetric
```

**Applies to:**
- `prometheus_client` - Metrics
- `duckdb` - Access logs
- `structlog` - Structured logging

**Installation options:**
```bash
pip install claude8code                    # Minimal
pip install "claude8code[metrics]"         # With Prometheus
pip install "claude8code[analytics]"       # With DuckDB
pip install "claude8code[all]"             # Everything
```

---

## 2. TOML Configuration

Configuration split between TOML (non-secrets) and `.env` (secrets).

**Structure:**
```
project/
├── settings/
│   ├── __init__.py       # Parser
│   └── settings.toml     # Config (committed)
├── .env                  # Secrets (gitignored)
└── .env.example          # Template (committed)
```

**settings/settings.toml:**
```toml
# Claude8Code Configuration
# Secrets go in .env, not here!

[server]
host = "0.0.0.0"
port = 8787
debug = false
log_level = "info"

[claude]
default_model = "claude-sonnet-4-5-20250514"
max_turns = 10
permission_mode = "acceptEdits"
sdk_message_mode = "forward"  # forward | formatted | ignore

[claude.system_prompt]
mode = "claude_code"

[claude.tools]
allowed = ["Read", "Write", "Bash", "Glob", "Grep"]

[security]
cors_origins = ["*"]

[session]
max_sessions = 100
ttl_seconds = 3600
cleanup_interval_seconds = 60
clear_on_release = true

[observability]
metrics_enabled = true
access_logs_enabled = true
access_logs_path = "data/access_logs.duckdb"
```

**.env.example:**
```bash
# Copy to .env and fill in values
# .env is gitignored - never commit secrets!

CLAUDE8CODE_AUTH_KEY=
# CLAUDE_CODE_OAUTH_TOKEN=
```

---

## 3. Request Context Propagation

Correlation IDs follow requests through async call chains for debugging.

**Context Object:**
```python
@dataclass
class RequestContext:
    request_id: str              # Unique per-request ID
    session_id: str | None
    path: str
    method: str
    model: str | None
    start_time: float
    tokens_in: int = 0
    tokens_out: int = 0
    error: str | None = None
```

**Usage via contextvars:**
```python
from claude8code.context import get_context

async def some_function():
    ctx = get_context()
    logger.info(f"[{ctx.request_id}] Processing...")
```

**Log correlation:**
```
[INFO] [req_abc123] Processing request
[ERROR] [req_abc123] Claude API failed
[INFO] [req_abc123] Request completed
```

---

## 4. StreamingResponseWithLogging

Automatic logging when streams complete (success, error, or client disconnect).

**Usage:**
```python
@app.post("/v1/messages")
async def create_message(request: MessagesRequest):
    stream = bridge.process_streaming(request)
    return StreamingResponseWithLogging(content=stream, context=get_context())
```

**Logs on completion:**
```json
{
  "event": "stream_completed",
  "request_id": "req_abc123",
  "status": "success",
  "bytes_sent": 15420,
  "chunks_sent": 142,
  "duration_seconds": 3.45
}
```

---

## 5. SDK Message Modes

Control how Claude SDK internal messages appear in responses.

**Modes:**

| Mode | Output |
|------|--------|
| `forward` | Raw SDK blocks (tool_use, tool_result) |
| `formatted` | XML-tagged text format |
| `ignore` | Only final text |

**forward (default):**
```json
{
  "content": [
    {"type": "text", "text": "Let me check..."},
    {"type": "tool_use", "id": "t1", "name": "Read", "input": {"path": "/foo"}},
    {"type": "tool_result", "tool_use_id": "t1", "content": "..."},
    {"type": "text", "text": "Based on the file..."}
  ]
}
```

**ignore:**
```json
{
  "content": [
    {"type": "text", "text": "Based on the file..."}
  ]
}
```

**Configuration:**
```toml
[claude]
sdk_message_mode = "forward"
```

**Per-request override:**
```bash
curl -H "x-sdk-message-mode: ignore" ...
```

---

## 6. Session Pooling with Clear

Session pool that **always clears context** between requests to prevent leakage.

**Lifecycle:**
```
Request → Acquire Session → Process → CLEAR → Return to Pool
```

**Clear guarantee:**
```python
async def release(self, session: PooledSession):
    # Equivalent to /clear - no context leakage!
    await session.claude_session.clear()
    session.is_active = False
```

**Configuration:**
```toml
[session]
max_sessions = 100
ttl_seconds = 3600
cleanup_interval_seconds = 60
clear_on_release = true  # Safety guarantee
```

**Benefits:**
- Reduced latency (session reuse)
- Memory management (TTL cleanup)
- Isolation guarantee (mandatory clear)

---

## 7. DuckDB Access Logs

Embedded analytics database for request/response logging.

**Schema:**
```sql
CREATE TABLE access_logs (
    request_id VARCHAR,
    session_id VARCHAR,
    timestamp TIMESTAMP,
    method VARCHAR,
    path VARCHAR,
    model VARCHAR,
    status_code INTEGER,
    duration_ms FLOAT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    stream BOOLEAN,
    error VARCHAR
);
```

**Query examples:**
```sql
-- Token usage by model (last 24h)
SELECT model, COUNT(*), SUM(input_tokens + output_tokens) as tokens
FROM access_logs
WHERE timestamp > NOW() - INTERVAL 1 DAY
GROUP BY model;

-- Error rate by hour
SELECT DATE_TRUNC('hour', timestamp),
       COUNT(*) as total,
       COUNT(CASE WHEN error IS NOT NULL THEN 1 END) as errors
FROM access_logs
GROUP BY 1;
```

**Uses graceful degradation:**
```python
try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False  # Logs to stdout only
```

---

## File Changes Summary

**New:**
```
settings/__init__.py
settings/settings.toml
.env.example
src/claude8code/context.py
src/claude8code/middleware.py
src/claude8code/streaming.py
src/claude8code/session_pool.py
src/claude8code/access_log.py
data/.gitkeep
```

**Modified:**
```
src/claude8code/config.py
src/claude8code/server.py
src/claude8code/bridge.py
src/claude8code/session.py
src/claude8code/models.py
src/claude8code/observability.py
pyproject.toml
.gitignore
README.md
```
