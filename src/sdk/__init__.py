"""Claude Agent SDK integration for claude8code.

This package contains:
- bridge: Request/response translation between Anthropic API and Claude SDK
- session_pool: Connection pooling for Claude SDK clients
- mcp_tools: Custom MCP tools for Claude Agent SDK
"""

from .bridge import (
    process_request,
    process_request_streaming,
    build_claude_options,
    build_prompt_from_messages,
    get_sdk_message_mode,
    session_manager,
    SessionManager,
    MODEL_MAP,
)

from .session_pool import (
    SessionPool,
    PooledSession,
    get_pool,
    init_pool,
    shutdown_pool,
)

from .mcp_tools import (
    get_custom_tools,
    get_tool_names,
    create_tools_server,
)

__all__ = [
    # Bridge
    "process_request",
    "process_request_streaming",
    "build_claude_options",
    "build_prompt_from_messages",
    "get_sdk_message_mode",
    "session_manager",
    "SessionManager",
    "MODEL_MAP",
    # Session Pool
    "SessionPool",
    "PooledSession",
    "get_pool",
    "init_pool",
    "shutdown_pool",
    # MCP Tools
    "get_custom_tools",
    "get_tool_names",
    "create_tools_server",
]
