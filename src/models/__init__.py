"""Pydantic models matching Anthropic's Messages API schema.

This module re-exports all models for convenient imports:
    from src.models import MessagesRequest, MessagesResponse
"""

from .errors import (
    SDKMessageMode,
    ErrorType,
    ErrorDetail,
    ErrorResponse,
)

from .requests import (
    CacheControl,
    ImageSource,
    DocumentSource,
    ContentBlockText,
    ContentBlockImage,
    ContentBlockDocument,
    ToolUseBlock,
    ToolResultBlock,
    ContentBlock,
    Message,
    ToolDefinition,
    ThinkingConfig,
    MessagesRequest,
)

from .responses import (
    Usage,
    TextBlock,
    ThinkingBlock,
    RedactedThinkingBlock,
    ToolUseResponseBlock,
    ResponseContentBlock,
    StopReason,
    MessagesResponse,
    ModelInfo,
    ModelsListResponse,
)

from .streaming import (
    MessageStartEvent,
    ContentBlockStartEvent,
    ContentBlockDeltaText,
    ContentBlockDeltaThinking,
    ContentBlockDeltaToolInput,
    ContentBlockDelta,
    ContentBlockDeltaEvent,
    ContentBlockStopEvent,
    MessageDeltaUsage,
    MessageDelta,
    MessageDeltaEvent,
    MessageStopEvent,
    PingEvent,
    ErrorEvent,
    StreamEvent,
)

__all__ = [
    # Errors
    "SDKMessageMode",
    "ErrorType",
    "ErrorDetail",
    "ErrorResponse",
    # Requests
    "CacheControl",
    "ImageSource",
    "DocumentSource",
    "ContentBlockText",
    "ContentBlockImage",
    "ContentBlockDocument",
    "ToolUseBlock",
    "ToolResultBlock",
    "ContentBlock",
    "Message",
    "ToolDefinition",
    "ThinkingConfig",
    "MessagesRequest",
    # Responses
    "Usage",
    "TextBlock",
    "ThinkingBlock",
    "RedactedThinkingBlock",
    "ToolUseResponseBlock",
    "ResponseContentBlock",
    "StopReason",
    "MessagesResponse",
    "ModelInfo",
    "ModelsListResponse",
    # Streaming
    "MessageStartEvent",
    "ContentBlockStartEvent",
    "ContentBlockDeltaText",
    "ContentBlockDeltaThinking",
    "ContentBlockDeltaToolInput",
    "ContentBlockDelta",
    "ContentBlockDeltaEvent",
    "ContentBlockStopEvent",
    "MessageDeltaUsage",
    "MessageDelta",
    "MessageDeltaEvent",
    "MessageStopEvent",
    "PingEvent",
    "ErrorEvent",
    "StreamEvent",
]
