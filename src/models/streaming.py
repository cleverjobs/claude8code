"""Streaming event models for SSE format.

These models define the Server-Sent Events format for streaming
responses matching Anthropic's API specification.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel

from .responses import (
    MessagesResponse,
    ResponseContentBlock,
    StopReason,
)


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


class ContentBlockDeltaThinking(BaseModel):
    """Delta for thinking content blocks (extended thinking)."""
    type: Literal["thinking_delta"] = "thinking_delta"
    thinking: str


class ContentBlockDeltaToolInput(BaseModel):
    """Delta for tool input JSON."""
    type: Literal["input_json_delta"] = "input_json_delta"
    partial_json: str


ContentBlockDelta = ContentBlockDeltaText | ContentBlockDeltaThinking | ContentBlockDeltaToolInput


class ContentBlockDeltaEvent(BaseModel):
    """Event sent for content block deltas (streaming text)."""
    type: Literal["content_block_delta"] = "content_block_delta"
    index: int
    delta: ContentBlockDelta


class ContentBlockStopEvent(BaseModel):
    """Event sent at the end of a content block."""
    type: Literal["content_block_stop"] = "content_block_stop"
    index: int


class MessageDeltaUsage(BaseModel):
    """Usage info in message delta."""
    output_tokens: int


class MessageDelta(BaseModel):
    """Delta info for message."""
    stop_reason: StopReason | None = None
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
