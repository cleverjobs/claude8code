# claude8code

[![Tests](https://github.com/krisjobs/claude8code/actions/workflows/test.yml/badge.svg)](https://github.com/krisjobs/claude8code/actions/workflows/test.yml)
[![Docker](https://github.com/krisjobs/claude8code/actions/workflows/docker.yml/badge.svg)](https://github.com/krisjobs/claude8code/actions/workflows/docker.yml)
[![codecov](https://codecov.io/gh/krisjobs/claude8code/branch/main/graph/badge.svg)](https://codecov.io/gh/krisjobs/claude8code)
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
# From PyPI (when published)
pip install claude8code

# From source
git clone https://github.com/krisjobs/claude8code.git
cd claude8code
pip install -e .
```

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
4. It just works! ✨

## Configuration

All settings can be configured via environment variables:

```bash
# Server settings
CLAUDE8CODE_HOST=0.0.0.0           # Bind address
CLAUDE8CODE_PORT=8787              # Port
CLAUDE8CODE_DEBUG=false            # Enable debug logging

# Claude Agent SDK settings
CLAUDE8CODE_DEFAULT_MODEL=claude-sonnet-4-5-20250514
CLAUDE8CODE_MAX_TURNS=10           # Max agent loop iterations
CLAUDE8CODE_PERMISSION_MODE=acceptEdits  # Auto-accept file edits
CLAUDE8CODE_CWD=/path/to/project   # Working directory

# System prompt
CLAUDE8CODE_SYSTEM_PROMPT_MODE=claude_code  # "claude_code" or "custom"
CLAUDE8CODE_CUSTOM_SYSTEM_PROMPT="You are a helpful assistant"

# Tool restrictions
CLAUDE8CODE_ALLOWED_TOOLS=Read,Write,Bash  # Comma-separated list

# Settings sources (user, project, local)
CLAUDE8CODE_SETTING_SOURCES=user,project
```

Or use a `.env` file:

```env
CLAUDE8CODE_PORT=8787
CLAUDE8CODE_MAX_TURNS=20
CLAUDE8CODE_CWD=/home/user/projects
```

## API Endpoints

### Anthropic-Compatible (for n8n)

| Endpoint | Description |
|----------|-------------|
| `POST /v1/messages` | Create message (streaming & non-streaming) |
| `GET /v1/models` | List available models |

### Extended API

| Endpoint | Description |
|----------|-------------|
| `POST /v1/sessions` | Create persistent session |
| `DELETE /v1/sessions/{id}` | Close session |
| `GET /v1/config` | View current configuration |
| `GET /health` | Health check |

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

## Development

```bash
# Clone and install dev dependencies
git clone https://github.com/krisjobs/claude8code.git
cd claude8code
make install

# Run with auto-reload
make run

# Run tests
make test

# Run tests with coverage
make coverage

# Lint and type check
make lint

# Format code
make format
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
1. Run `make lint` to check code quality
2. Run `make test` to verify all tests pass
3. Update documentation if needed

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## License

MIT - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) - The official Python SDK
- [Claude Code](https://claude.ai/code) - Anthropic's agentic coding tool
- [n8n](https://n8n.io) - Workflow automation platform
