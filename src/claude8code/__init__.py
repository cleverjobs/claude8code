"""claude8code - Anthropic-compatible API server powered by Claude Agent SDK.

Use your Claude Max/Pro subscription with n8n's native Anthropic node
by simply changing the base URL to point to this server.

Features:
- Full Claude Agent SDK integration (subagents, skills, MCP tools)
- Streaming support via SSE
- Anthropic Messages API compatible
- Session management for multi-turn conversations

Quick Start:
    # Start the server
    claude8code --port 8787
    
    # Set n8n environment variable
    ANTHROPIC_BASE_URL=http://localhost:8787 n8n start
    
    # Use Anthropic Chat Model node with any API key
"""

__version__ = "0.1.0"

from .config import settings
from .server import app
from .security import verify_api_key
from .mcp_tools import get_custom_tools, get_tool_names, create_tools_server

__all__ = [
    "app",
    "settings",
    "verify_api_key",
    "get_custom_tools",
    "get_tool_names",
    "create_tools_server",
    "__version__",
]
