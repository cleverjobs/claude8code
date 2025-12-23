"""Request models matching Anthropic's Messages API schema.

These models ensure compatibility with n8n's native Anthropic node
and any other client expecting the official API format.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class CacheControl(BaseModel):
    """Cache control for prompt caching.

    Allows caching of system prompts and messages to reduce costs
    for repeated context.
    """
    type: Literal["ephemeral"] = "ephemeral"


class ImageSource(BaseModel):
    """Image source for vision requests."""
    type: Literal["base64", "url"]
    media_type: str | None = None
    data: str | None = None
    url: str | None = None


class DocumentSource(BaseModel):
    """Document source for PDF processing (beta feature)."""
    type: Literal["base64"] = "base64"
    media_type: Literal["application/pdf"] = "application/pdf"
    data: str


class ContentBlockText(BaseModel):
    """Text content block in a message."""
    type: Literal["text"] = "text"
    text: str
    cache_control: CacheControl | None = None


class ContentBlockImage(BaseModel):
    """Image content block in a message."""
    type: Literal["image"] = "image"
    source: ImageSource


class ContentBlockDocument(BaseModel):
    """Document content block for PDF processing (beta feature)."""
    type: Literal["document"] = "document"
    source: DocumentSource
    cache_control: CacheControl | None = None


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


ContentBlock = ContentBlockText | ContentBlockImage | ContentBlockDocument | ToolUseBlock | ToolResultBlock


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
