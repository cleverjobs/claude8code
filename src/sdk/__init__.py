"""Claude Agent SDK integration for claude8code.

This package contains:
- bridge: Request/response translation between Anthropic API and Claude SDK
- session_pool: Connection pooling for Claude SDK clients
- mcp_tools: Custom MCP tools for Claude Agent SDK
"""

from .batch_processor import (
    BatchProcessor,
    get_batch_processor,
    init_batch_processor,
    shutdown_batch_processor,
)
from .bridge import (
    MODEL_MAP,
    SessionManager,
    build_claude_options,
    build_prompt_from_messages,
    get_sdk_message_mode,
    process_request,
    process_request_streaming,
    session_manager,
)
from .file_store import (
    FileStore,
    get_file_store,
    init_file_store,
    shutdown_file_store,
)
from .mcp_tools import (
    create_tools_server,
    get_custom_tools,
    get_tool_names,
)
from .session_pool import (
    PooledSession,
    SessionPool,
    get_pool,
    init_pool,
    shutdown_pool,
)
from .tokenizer import (
    TIKTOKEN_AVAILABLE,
    count_request_tokens,
    count_tokens,
)
from .workspace import (
    WorkspaceConfig,
    expand_command,
    get_project_instructions,
    get_workspace,
    load_workspace,
    reload_workspace,
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
    # Tokenizer
    "count_tokens",
    "count_request_tokens",
    "TIKTOKEN_AVAILABLE",
    # File Store
    "FileStore",
    "get_file_store",
    "init_file_store",
    "shutdown_file_store",
    # Batch Processor
    "BatchProcessor",
    "get_batch_processor",
    "init_batch_processor",
    "shutdown_batch_processor",
    # Workspace
    "WorkspaceConfig",
    "load_workspace",
    "get_workspace",
    "reload_workspace",
    "expand_command",
    "get_project_instructions",
]
