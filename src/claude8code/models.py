"""Pydantic models matching Anthropic's Messages API schema.

These models ensure compatibility with n8n's native Anthropic node
and any other client expecting the official API format.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime


# ============================================================================
# Request Models (what n8n sends to us)
# ============================================================================

class ContentBlockText(BaseModel):
    """Text content block in a message."""
    type: Literal["text"] = "text"
    text: str


class ContentBlockImage(BaseModel):
    """Image content block in a message."""
    type: Literal["image"] = "image"
    source: ImageSource


class ImageSource(BaseModel):
    """Image source for vision requests."""
    type: Literal["base64", "url"]
    media_type: str | None = None
    data: str | None = None
    url: str | None = None


class ToolUseBlock(BaseModel):
    """Tool use content block."""
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any]


class ToolResultBlock(BaseModel):
    """Tool result content block."""
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str | list[ContentBlockText | ContentBlockImage]
    is_error: bool = False


ContentBlock = ContentBlockText | ContentBlockImage | ToolUseBlock | ToolResultBlock


class Message(BaseModel):
    """A message in the conversation."""
    role: Literal["user", "assistant"]
    content: str | list[ContentBlock]


class ToolDefinition(BaseModel):
    """Tool definition for function calling."""
    name: str
    description: str | None = None
    input_schema: dict[str, Any]


class ThinkingConfig(BaseModel):
    """Configuration for extended thinking process (ultrathink)."""
    type: Literal["enabled"] = "enabled"
    budget_tokens: int = Field(ge=1024, description="Token budget for thinking process")


class MessagesRequest(BaseModel):
    """Request body for POST /v1/messages - matches Anthropic's schema."""
    model: str
    messages: list[Message]
    max_tokens: int = 4096
    system: str | list[dict[str, Any]] | None = None
    stop_sequences: list[str] | None = None
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    tools: list[ToolDefinition] | None = None
    tool_choice: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    thinking: ThinkingConfig | None = None


# ============================================================================
# Response Models (what we return to n8n)
# ============================================================================

class Usage(BaseModel):
    """Token usage information."""
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None


class TextBlock(BaseModel):
    """Text block in response content."""
    type: Literal["text"] = "text"
    text: str


class ToolUseResponseBlock(BaseModel):
    """Tool use block in response."""
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any]


ResponseContentBlock = TextBlock | ToolUseResponseBlock


class MessagesResponse(BaseModel):
    """Response body for POST /v1/messages - matches Anthropic's schema."""
    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: list[ResponseContentBlock]
    model: str
    stop_reason: Literal["end_turn", "max_tokens", "stop_sequence", "tool_use"] | None = None
    stop_sequence: str | None = None
    usage: Usage


# ============================================================================
# Streaming Event Models (SSE format)
# ============================================================================

class MessageStartEvent(BaseModel):
    """Event sent at the start of a message stream."""
    type: Literal["message_start"] = "message_start"
    message: MessagesResponse


class ContentBlockStartEvent(BaseModel):
    """Event sent at the start of a content block."""
    type: Literal["content_block_start"] = "content_block_start"
    index: int
    content_block: ResponseContentBlock


class ContentBlockDeltaText(BaseModel):
    """Delta for text content blocks."""
    type: Literal["text_delta"] = "text_delta"
    text: str


class ContentBlockDeltaToolInput(BaseModel):
    """Delta for tool input JSON."""
    type: Literal["input_json_delta"] = "input_json_delta"
    partial_json: str


class ContentBlockDeltaEvent(BaseModel):
    """Event sent for content block deltas (streaming text)."""
    type: Literal["content_block_delta"] = "content_block_delta"
    index: int
    delta: ContentBlockDeltaText | ContentBlockDeltaToolInput


class ContentBlockStopEvent(BaseModel):
    """Event sent at the end of a content block."""
    type: Literal["content_block_stop"] = "content_block_stop"
    index: int


class MessageDeltaUsage(BaseModel):
    """Usage info in message delta."""
    output_tokens: int


class MessageDelta(BaseModel):
    """Delta info for message."""
    stop_reason: Literal["end_turn", "max_tokens", "stop_sequence", "tool_use"] | None = None
    stop_sequence: str | None = None


class MessageDeltaEvent(BaseModel):
    """Event sent with message delta (stop reason, final usage)."""
    type: Literal["message_delta"] = "message_delta"
    delta: MessageDelta
    usage: MessageDeltaUsage


class MessageStopEvent(BaseModel):
    """Event sent at the end of a message stream."""
    type: Literal["message_stop"] = "message_stop"


class PingEvent(BaseModel):
    """Keepalive ping event."""
    type: Literal["ping"] = "ping"


class ErrorEvent(BaseModel):
    """Error event in stream."""
    type: Literal["error"] = "error"
    error: dict[str, Any]


StreamEvent = (
    MessageStartEvent
    | ContentBlockStartEvent
    | ContentBlockDeltaEvent
    | ContentBlockStopEvent
    | MessageDeltaEvent
    | MessageStopEvent
    | PingEvent
    | ErrorEvent
)


# ============================================================================
# Error Response Models
# ============================================================================

class ErrorDetail(BaseModel):
    """Error detail object."""
    type: str
    message: str


class ErrorResponse(BaseModel):
    """Error response body."""
    type: Literal["error"] = "error"
    error: ErrorDetail


# ============================================================================
# Models List Response (for /v1/models endpoint)
# ============================================================================

class ModelInfo(BaseModel):
    """Information about a single model."""
    id: str
    object: Literal["model"] = "model"
    created: int = Field(default_factory=lambda: int(datetime.now().timestamp()))
    owned_by: str = "anthropic"


class ModelsListResponse(BaseModel):
    """Response for GET /v1/models."""
    object: Literal["list"] = "list"
    data: list[ModelInfo]
