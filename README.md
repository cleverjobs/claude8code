# claude8code

[![Tests](https://github.com/krisjobs/claude8code/actions/workflows/test.yml/badge.svg)](https://github.com/krisjobs/claude8code/actions/workflows/test.yml)
[![Docker](https://github.com/krisjobs/claude8code/actions/workflows/docker.yml/badge.svg)](https://github.com/krisjobs/claude8code/actions/workflows/docker.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker Hub](https://img.shields.io/docker/v/krisjobs/claude8code?label=docker)](https://hub.docker.com/r/krisjobs/claude8code)

**Anthropic-compatible API server powered by Claude Agent SDK** - Use your Claude Max/Pro subscription with n8n's native Anthropic node.

Unlike other proxy solutions that simply forward API calls, claude8code uses the **Claude Agent SDK** directly, giving you access to all Claude Code features:

- 🤖 **Subagents** - Spawn child agents for complex tasks
- 🛠️ **Skills** - Use built-in coding skills (Read, Write, Bash, etc.)
- 🔌 **MCP Tools** - Connect external tools via Model Context Protocol
- 📁 **File Operations** - Read/write files with proper permissions
- 🔄 **Multi-turn Sessions** - Maintain conversation context

## Why claude8code?

| Feature | Pure API Proxy | **claude8code** |
|---------|---------------|-----------------|
| Streaming | ✅ | ✅ |
| Tool calling | ✅ | ✅ |
| Claude Code skills | ❌ | ✅ |
| Subagents | ❌ | ✅ |
| MCP integration | ❌ | ✅ |
| File operations | ❌ | ✅ |
| Custom hooks | ❌ | ✅ |
| Session persistence | ❌ | ✅ |

## Prerequisites

1. **Node.js 18+** - Required for Claude Code CLI
2. **Python 3.10+** - For running claude8code
3. **Claude Pro/Max subscription** - Authenticated via Claude Code CLI

```bash
# Install Claude Code CLI
npm install -g @anthropic-ai/claude-code

# Authenticate (opens browser)
claude /login
```

## Installation

```bash
# Minimal installation
pip install claude8code

# With Prometheus metrics
pip install "claude8code[metrics]"

# With DuckDB access logs
pip install "claude8code[analytics]"

# With all optional features
pip install "claude8code[all]"

# From source
git clone https://github.com/krisjobs/claude8code.git
cd claude8code
pip install -e ".[all]"
```

**Optional dependencies:**
- `metrics` - Prometheus metrics export (`prometheus-client`)
- `analytics` - DuckDB access logs (`duckdb`)
- `logging` - Structured logging (`structlog`)
- `tokenizer` - Token counting (`tiktoken`)
- `all` - All optional features

## Quick Start

### 1. Start claude8code

```bash
claude8code --port 8787
```

### 2. Configure n8n

```bash
# Option A: Environment variable
ANTHROPIC_BASE_URL=http://localhost:8787 n8n start

# Option B: Docker
docker run -e ANTHROPIC_BASE_URL=http://localhost:8787 n8nio/n8n
```

### 3. Use n8n's Anthropic Node

1. Add **Anthropic Chat Model** node to your workflow
2. Create credentials with any API key (e.g., `sk-dummy`)
3. Select your model (claude-sonnet-4-5, claude-opus-4, etc.)
4. It just works!

## Using with Claude Agent SDK

claude8code can also be used as a local endpoint for the **Python Claude Agent SDK**.

### Setup

```bash
# Start claude8code
python -m claude8code

# Configure Agent SDK environment
export ANTHROPIC_BASE_URL="http://localhost:8787/sdk"
export ANTHROPIC_API_KEY="dummy-key"  # Required by SDK, ignored by claude8code
```

### Python Example

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def main():
    options = ClaudeAgentOptions(
        system_prompt="You are a helpful coding assistant.",
        max_turns=5,
        allowed_tools=["Read", "Write", "Bash"]
    )

    async for message in query(prompt="List files in current directory", options=options):
        if hasattr(message, 'content'):
            print(message.content)

if __name__ == "__main__":
    asyncio.run(main())
```

### URL Patterns

Both URL patterns are supported:

| Base URL | Use Case |
|----------|----------|
| `http://localhost:8787` | Direct Anthropic compatibility |
| `http://localhost:8787/sdk` | ccproxy-style SDK prefix |

See [docs/agent-sdk-usage.md](docs/agent-sdk-usage.md) for detailed documentation.

## Configuration

claude8code uses **TOML for non-secret settings** and **`.env` for secrets**.

```
project/
├── settings/
│   ├── __init__.py          # Settings parser
│   └── settings.toml        # Configuration (committed)
├── .env                     # Secrets (gitignored)
└── .env.example             # Template (committed)
```

### settings/settings.toml

```toml
# Claude8Code Configuration
# Secrets (API keys, tokens) go in .env, not here!

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
mode = "claude_code"  # claude_code | custom

[claude.tools]
allowed = []  # Empty = all tools, or specify: ["Read", "Write", "Bash"]

[security]
cors_origins = ["*"]

[session]
max_sessions = 100
ttl_seconds = 3600
cleanup_interval_seconds = 60
clear_on_release = true  # Always clear context between requests (safety)

[observability]
metrics_enabled = true
access_logs_enabled = true
access_logs_path = "data/access_logs.duckdb"
```

### .env (Secrets Only)

```bash
# Copy .env.example to .env and fill in values
CLAUDE8CODE_AUTH_KEY=your-secret-api-key  # Optional API authentication
```

### Environment Variable Override

Settings can also be overridden via environment variables:

```bash
CLAUDE8CODE_HOST=0.0.0.0
CLAUDE8CODE_PORT=8787
CLAUDE8CODE_AUTH_KEY=secret
```

## API Endpoints

### Anthropic-Compatible (for n8n)

| Endpoint | SDK Prefix Equivalent | Description |
|----------|----------------------|-------------|
| `POST /v1/messages` | `POST /sdk/v1/messages` | Create message (streaming & non-streaming) |
| `POST /v1/messages/count_tokens` | `POST /sdk/v1/messages/count_tokens` | Count tokens before sending |
| `GET /v1/models` | `GET /sdk/v1/models` | List available models |
| `GET /health` | `GET /sdk/health` | Health check |

### Extended API

| Endpoint | Description |
|----------|-------------|
| `POST /v1/sessions` | Create persistent session |
| `DELETE /v1/sessions/{id}` | Close session |
| `GET /v1/config` | View current configuration |
| `GET /v1/pool/stats` | Session pool statistics |
| `GET /v1/logs/stats` | Access log statistics (DuckDB) |
| `GET /health` | Health check |
| `GET /metrics` | Prometheus metrics |

### Files API (Beta)

| Endpoint | Description |
|----------|-------------|
| `POST /v1/files` | Upload file (max 500MB) |
| `GET /v1/files` | List files with pagination |
| `GET /v1/files/{id}` | Get file metadata |
| `GET /v1/files/{id}/content` | Download file content |
| `DELETE /v1/files/{id}` | Delete file |

### Message Batches API

| Endpoint | Description |
|----------|-------------|
| `POST /v1/messages/batches` | Create batch (processes immediately) |
| `GET /v1/messages/batches` | List batches with pagination |
| `GET /v1/messages/batches/{id}` | Get batch status |
| `POST /v1/messages/batches/{id}/cancel` | Cancel in-progress batch |
| `GET /v1/messages/batches/{id}/results` | Stream results as JSONL |
| `DELETE /v1/messages/batches/{id}` | Delete completed batch |

### Request Headers

| Header | Description |
|--------|-------------|
| `x-api-key` | API authentication (if `CLAUDE8CODE_AUTH_KEY` is set) |
| `x-request-id` | Correlation ID (auto-generated if not provided) |
| `x-session-id` | Session ID for multi-turn conversations |
| `x-sdk-message-mode` | Override SDK message mode (`forward`/`formatted`/`ignore`) |

## Usage Examples

### Basic Request (curl)

```bash
curl http://localhost:8787/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: sk-dummy" \
  -d '{
    "model": "claude-sonnet-4-5-20250514",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "Write a Python hello world"}
    ]
  }'
```

### Streaming Request

```bash
curl http://localhost:8787/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: sk-dummy" \
  -d '{
    "model": "claude-sonnet-4-5-20250514",
    "max_tokens": 1024,
    "stream": true,
    "messages": [
      {"role": "user", "content": "Explain quantum computing"}
    ]
  }'
```

### Python Client

```python
import anthropic

# Point to claude8code
client = anthropic.Anthropic(
    api_key="sk-dummy",
    base_url="http://localhost:8787"
)

message = client.messages.create(
    model="claude-sonnet-4-5-20250514",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Create a Flask API with 3 endpoints"}
    ]
)
print(message.content[0].text)
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│    n8n      │────▶│  claude8code │────▶│ Claude Agent SDK│
│ (Anthropic  │     │   (FastAPI)  │     │   (Python)      │
│   Node)     │◀────│              │◀────│                 │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
                                          ┌────────▼────────┐
                                          │  Claude Code    │
                                          │  (Node.js CLI)  │
                                          │                 │
                                          │  • Skills       │
                                          │  • MCP Tools    │
                                          │  • Subagents    │
                                          └────────┬────────┘
                                                   │
                                          ┌────────▼────────┐
                                          │ Claude Max/Pro  │
                                          │  (Subscription) │
                                          └─────────────────┘
```

## Observability

claude8code includes built-in Prometheus metrics for monitoring.

### Metrics Endpoint

Access metrics at `http://localhost:8787/metrics`

Available metrics:
- `claude8code_requests_total` - Total requests by endpoint and status
- `claude8code_request_duration_seconds` - Request latency histogram
- `claude8code_errors_total` - Error count by type
- `claude8code_active_sessions` - Current active sessions
- `claude8code_tokens_total` - Token usage (input/output)

### Prometheus + Grafana Stack

Start the full observability stack:

```bash
make up-monitoring
```

This starts:
- **claude8code**: http://localhost:8787
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)

A pre-configured dashboard is included for monitoring requests, latency, and token usage.

### DuckDB Access Logs

When installed with `[analytics]`, claude8code logs all requests to a DuckDB database for analytics.

```sql
-- Token usage by model (last 24h)
SELECT model, COUNT(*) as requests, SUM(input_tokens + output_tokens) as tokens
FROM access_logs
WHERE timestamp > NOW() - INTERVAL 1 DAY
GROUP BY model;

-- Error rate by hour
SELECT DATE_TRUNC('hour', timestamp) as hour,
       COUNT(*) as total,
       COUNT(CASE WHEN error IS NOT NULL THEN 1 END) as errors
FROM access_logs
GROUP BY 1 ORDER BY 1;

-- Average latency by endpoint
SELECT path, AVG(duration_ms) as avg_ms
FROM access_logs
GROUP BY path;
```

Access statistics via API: `GET /v1/logs/stats`

## Advanced Features

### Session Pooling

claude8code maintains a pool of Claude SDK sessions for performance. Sessions are automatically:
- Reused across requests
- Cleared between requests (prevents context leakage)
- Cleaned up when expired (TTL-based)

**Safety guarantee:** Every session is cleared (equivalent to `/clear` in Claude Code) before being returned to the pool. This prevents conversation context from leaking between requests.

```toml
[session]
max_sessions = 100
ttl_seconds = 3600
clear_on_release = true  # Always true - safety guarantee
```

### SDK Message Modes

Control how Claude SDK internal messages (tool calls, results) appear in responses:

| Mode | Description |
|------|-------------|
| `forward` | Raw SDK blocks (tool_use, tool_result) - default |
| `formatted` | Convert to XML-tagged text format |
| `ignore` | Only final text output |

Configure globally in `settings.toml`:
```toml
[claude]
sdk_message_mode = "forward"
```

Or override per-request:
```bash
curl -H "x-sdk-message-mode: ignore" http://localhost:8787/v1/messages ...
```

### Request Context

Every request gets a unique correlation ID for debugging:
- Auto-generated or from `x-request-id` header
- Propagated through all logs
- Returned in response headers

```
[INFO] [req_abc123] Processing request
[ERROR] [req_abc123] Claude API failed
[INFO] [req_abc123] Request completed in 1234ms
```

### Graceful Degradation

Optional dependencies are handled gracefully:
- No Prometheus? Metrics silently disabled
- No DuckDB? Access logs to stdout only
- Server always starts and functions

### File Storage

claude8code includes local file storage for the Files API beta:

- **Storage**: Local filesystem (configurable directory)
- **Size limit**: 500 MB per file
- **TTL**: Automatic cleanup after expiration (default 24 hours)
- **MIME detection**: Automatic content type detection

Files can be uploaded and referenced in Messages API requests using file IDs.

### Message Batches

Unlike Anthropic's production API which processes batches over 24 hours, claude8code processes batches **immediately** using asyncio for fast iteration:

- **Concurrent processing**: Configurable parallelism
- **JSONL results**: Stream results as they complete
- **Lifecycle**: in_progress → ended (with cancel support)
- **TTL**: Results retained for 29 days (matching Anthropic spec)

```bash
# Create batch
curl -X POST http://localhost:8787/v1/messages/batches \
  -H "Content-Type: application/json" \
  -d '{"requests": [{"custom_id": "req-1", "params": {...}}]}'

# Get results
curl http://localhost:8787/v1/messages/batches/{batch_id}/results
```

### Token Counting

Estimate token usage before sending requests:

```bash
curl -X POST http://localhost:8787/v1/messages/count_tokens \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5-20250514",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

Requires `tiktoken` optional dependency. Falls back to estimation if not installed.

## Workspace & Extensibility

claude8code supports Claude Code's extensibility features through a workspace directory. Add custom skills, commands, agents, hooks, and MCP servers.

### Workspace Structure

```
workspace/
├── .mcp.json               # MCP server configuration
└── .claude/
    ├── settings.json       # Hooks and permissions
    ├── commands/           # Custom slash commands
    │   └── {name}.md
    ├── skills/             # Custom skills
    │   └── {name}/
    │       └── SKILL.md
    └── agents/             # Custom subagents
        └── {name}.md
```

### Adding a Slash Command

Create `workspace/.claude/commands/my-command.md`:

```markdown
# /my-command

Brief description.

## Instructions
When the user types `/my-command`:
1. Perform action one
2. Perform action two
```

### Adding a Skill

Create `workspace/.claude/skills/my-skill/SKILL.md`:

```markdown
# My Skill

## Description
What this skill does and when it should be used.

## Instructions
When invoked:
1. Step one
2. Step two
```

### Adding an Agent

Create `workspace/.claude/agents/my-agent.md`:

```markdown
# My Agent

## Role
Define the agent's role and capabilities.

## Instructions
How the agent should behave when spawned.
```

### Configuring Hooks

Edit `workspace/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "echo 'Running...'"}]
      }
    ]
  }
}
```

### Adding MCP Servers

Edit `workspace/.mcp.json`:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
    }
  }
}
```

### Configuring Workspace Path

Default: `workspace/` relative to where claude8code starts.

Override in `settings/settings.toml`:
```toml
[claude]
cwd = "/absolute/path/to/workspace"
```

Or via environment:
```bash
export CLAUDE8CODE_CWD="/path/to/workspace"
```

## Development

```bash
# Clone and install dependencies
git clone https://github.com/krisjobs/claude8code.git
cd claude8code
uv sync --all-extras

# Run server
uv run python main.py

# Run with auto-reload
uv run python main.py --reload

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src

# Lint and type check
uv run ruff check src tests
uv run mypy src

# Format code
uv run ruff format src tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development guidelines.

## Troubleshooting

### "CLINotFoundError: Claude Code CLI not found"

Install Claude Code CLI:
```bash
npm install -g @anthropic-ai/claude-code
```

### "Authentication required"

Log in to Claude Code:
```bash
claude /login
```

### n8n still hitting api.anthropic.com

Make sure the environment variable is set **before** starting n8n:
```bash
export ANTHROPIC_BASE_URL=http://localhost:8787
n8n start
```

### Connection refused

Check that claude8code is running and accessible:
```bash
curl http://localhost:8787/health
```

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Before submitting a PR:
1. Run `uv run ruff check src tests` to check code quality
2. Run `uv run pytest` to verify all tests pass
3. Update documentation if needed

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## License

MIT - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) - The official Python SDK
- [Claude Code](https://claude.ai/code) - Anthropic's agentic coding tool
- [n8n](https://n8n.io) - Workflow automation platform
