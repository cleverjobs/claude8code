"""claude8code - Anthropic-compatible API server powered by Claude Agent SDK.

This package provides a FastAPI server that accepts Anthropic Messages API
requests and routes them through Claude Agent SDK.

Subpackages:
- api: HTTP/API layer (routes, middleware, security)
- sdk: Claude Agent SDK integration (bridge, session pool)
- models: Pydantic data models (requests, responses, streaming, errors)
- core: Shared infrastructure (config, context, metrics, access_log)
"""

__version__ = "0.1.0"

# Re-export commonly used items for convenience
from .models import (
    MessagesRequest,
    MessagesResponse,
    ErrorType,
    ErrorResponse,
    SDKMessageMode,
)

from .core import settings

from .sdk import (
    process_request,
    process_request_streaming,
    session_manager,
)

__all__ = [
    "__version__",
    # Models
    "MessagesRequest",
    "MessagesResponse",
    "ErrorType",
    "ErrorResponse",
    "SDKMessageMode",
    # Core
    "settings",
    # SDK
    "process_request",
    "process_request_streaming",
    "session_manager",
]
