# Using claude8code with Claude Agent SDK

This guide explains how to use claude8code as a local API endpoint for the Python Claude Agent SDK.

## Overview

claude8code exposes an Anthropic-compatible API that can be used as a custom endpoint via the `ANTHROPIC_BASE_URL` environment variable. This allows the Claude Agent SDK to route requests through claude8code, which then processes them using the Claude Agent SDK internally.

**Benefits:**
- Use Claude Max/Pro subscription instead of API billing
- Access Claude Code features (skills, MCP tools, subagents)
- Local development and testing without API costs

## Quick Start

### 1. Start claude8code

```bash
# Start the server
python -m claude8code

# Or with uv
uv run claude8code
```

The server starts on `http://localhost:8787` by default.

### 2. Configure Environment

```bash
# Point Agent SDK to claude8code
export ANTHROPIC_BASE_URL="http://localhost:8787/sdk"

# Required by SDK (value is ignored by claude8code)
export ANTHROPIC_API_KEY="dummy-key"
```

### 3. Use the Agent SDK

```python
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

async def main():
    options = ClaudeAgentOptions(
        system_prompt="You are a helpful coding assistant.",
        max_turns=5,
        allowed_tools=["Read", "Write", "Bash"]
    )

    async for message in query(prompt="What files are in the current directory?", options=options):
        if hasattr(message, 'content'):
            print(message.content)

if __name__ == "__main__":
    asyncio.run(main())
```

## URL Patterns

claude8code supports two URL patterns for flexibility:

| Base URL | Endpoints | Use Case |
|----------|-----------|----------|
| `http://localhost:8787` | `/v1/messages`, `/v1/models` | Direct Anthropic compatibility |
| `http://localhost:8787/sdk` | `/sdk/v1/messages`, `/sdk/v1/models` | ccproxy-style SDK prefix |

Both patterns are functionally identical. Use `/sdk` prefix for compatibility with tools that expect ccproxy-style URLs.

## Configuration Options

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_BASE_URL` | API endpoint URL | `https://api.anthropic.com` |
| `ANTHROPIC_API_KEY` | API key (ignored by claude8code) | Required by SDK |
| `ANTHROPIC_AUTH_TOKEN` | Auth token for claude8code | Optional |

### claude8code Settings

Configure via `settings/settings.toml` or environment variables:

```toml
[server]
host = "0.0.0.0"
port = 8787

[claude]
default_model = "claude-sonnet-4-5-20250514"
max_turns = 10
permission_mode = "acceptEdits"
sdk_message_mode = "forward"
```

Or via environment:

```bash
export CLAUDE8CODE_PORT=8787
export CLAUDE8CODE_DEFAULT_MODEL="claude-sonnet-4-5-20250514"
```

## Authentication

### No Authentication (Default)

By default, claude8code runs without authentication. Any client can connect.

### Enable Authentication

Set `CLAUDE8CODE_AUTH_KEY` to require API key authentication:

```bash
export CLAUDE8CODE_AUTH_KEY="your-secret-key"
```

Clients must then provide the key in either:
- `x-api-key: your-secret-key` header
- `Authorization: Bearer your-secret-key` header

## Verifying the Setup

### Check Server Health

```bash
# Root health check
curl http://localhost:8787/health

# SDK prefix health check
curl http://localhost:8787/sdk/health
```

### Test Message Endpoint

```bash
curl -X POST http://localhost:8787/sdk/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5-20250514",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 100
  }'
```

### Test with Agent SDK

```python
import os
import asyncio
from claude_agent_sdk import query, ClaudeAgentOptions

# Verify environment
assert os.getenv("ANTHROPIC_BASE_URL"), "Set ANTHROPIC_BASE_URL"

async def test():
    options = ClaudeAgentOptions(max_turns=1)
    async for msg in query(prompt="Say hello", options=options):
        print(f"Response type: {type(msg).__name__}")
        if hasattr(msg, 'content'):
            print(f"Content: {msg.content}")

asyncio.run(test())
```

## Troubleshooting

### "Connection refused"

**Cause:** claude8code not running

**Solution:** Start the server with `python -m claude8code`

### "Unauthorized" or 401 Error

**Cause:** Authentication is enabled but key not provided

**Solution:** Either:
1. Unset `CLAUDE8CODE_AUTH_KEY` to disable auth
2. Provide the key via `x-api-key` header or `Authorization: Bearer` header

### "Model not found"

**Cause:** Requested model not available

**Solution:** Use one of the supported models:
- `claude-sonnet-4-5-20250514`
- `claude-opus-4-5-20251101`
- `claude-haiku-4-5-20251001`

### Streaming Issues

**Cause:** Proxy or network issues with SSE

**Solution:**
1. Test with non-streaming first: `"stream": false`
2. Check for proxy servers that might buffer SSE responses

### "ANTHROPIC_API_KEY not set"

**Cause:** Agent SDK requires an API key

**Solution:** Set a dummy key: `export ANTHROPIC_API_KEY="dummy-key"`

The key value doesn't matter - claude8code ignores it and uses Claude Code CLI credentials instead.

## Advanced Usage

### Custom Working Directory

```bash
export CLAUDE8CODE_CWD="/path/to/your/project"
```

### Adjust Max Turns

```bash
export CLAUDE8CODE_MAX_TURNS=20
```

### SDK Message Mode

Control how SDK tool use messages appear in responses:

```bash
# forward: Pass through raw SDK messages (default)
export CLAUDE8CODE_SDK_MESSAGE_MODE="forward"

# formatted: Convert to XML-tagged text
export CLAUDE8CODE_SDK_MESSAGE_MODE="formatted"

# ignore: Strip SDK messages, only return final text
export CLAUDE8CODE_SDK_MESSAGE_MODE="ignore"
```

## See Also

- [claude8code README](../README.md)
- [Claude Agent SDK Documentation](https://docs.anthropic.com/en/docs/agents-and-tools/claude-agent-sdk)
- [Anthropic Messages API Reference](https://docs.anthropic.com/en/api/messages)
