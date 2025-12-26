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
    ttl: Literal["5m", "1h"] | None = None


class ImageSource(BaseModel):
    """Image source for vision requests."""

    type: Literal["base64", "url"]
    media_type: str | None = None
    data: str | None = None
    url: str | None = None


class Base64DocumentSource(BaseModel):
    """Base64-encoded document source for PDF processing."""

    type: Literal["base64"] = "base64"
    media_type: Literal["application/pdf"] = "application/pdf"
    data: str


class PlainTextDocumentSource(BaseModel):
    """Plain text document source."""

    type: Literal["text"] = "text"
    media_type: Literal["text/plain"] = "text/plain"
    data: str


class ContentDocumentSource(BaseModel):
    """Content blocks document source."""

    type: Literal["content"] = "content"
    content: str | list[dict[str, Any]]


class URLDocumentSource(BaseModel):
    """URL-based document source for PDFs."""

    type: Literal["url"] = "url"
    url: str


# Union of all document source types
DocumentSource = (
    Base64DocumentSource | PlainTextDocumentSource | ContentDocumentSource | URLDocumentSource
)


class CitationsConfig(BaseModel):
    """Configuration for document citations."""

    enabled: bool = False


# Citation types for response text blocks
class CitationCharLocation(BaseModel):
    """Citation referencing text by character position."""

    type: Literal["char_location"] = "char_location"
    cited_text: str
    document_index: int
    document_title: str | None = None
    start_char_index: int
    end_char_index: int


class CitationPageLocation(BaseModel):
    """Citation referencing a page in a PDF document."""

    type: Literal["page_location"] = "page_location"
    cited_text: str
    document_index: int
    document_title: str | None = None
    page_number: int


class CitationContentBlockLocation(BaseModel):
    """Citation referencing a content block."""

    type: Literal["content_block_location"] = "content_block_location"
    cited_text: str
    document_index: int
    document_title: str | None = None
    content_block_index: int


class CitationWebSearchResultLocation(BaseModel):
    """Citation referencing a web search result."""

    type: Literal["web_search_result_location"] = "web_search_result_location"
    cited_text: str
    url: str
    title: str | None = None


class CitationSearchResultLocation(BaseModel):
    """Citation referencing a search result block."""

    type: Literal["search_result_location"] = "search_result_location"
    cited_text: str
    document_index: int
    document_title: str | None = None


# Union of all citation types
Citation = (
    CitationCharLocation
    | CitationPageLocation
    | CitationContentBlockLocation
    | CitationWebSearchResultLocation
    | CitationSearchResultLocation
)


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
    """Document content block for PDF and text document processing."""

    type: Literal["document"] = "document"
    source: (
        Base64DocumentSource | PlainTextDocumentSource | ContentDocumentSource | URLDocumentSource
    )
    title: str | None = None
    context: str | None = None
    citations: CitationsConfig | None = None
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


# Web search content blocks
class WebSearchResult(BaseModel):
    """Individual web search result."""

    type: Literal["web_search_result"] = "web_search_result"
    url: str
    title: str
    encrypted_content: str | None = None
    page_age: str | None = None


class WebSearchError(BaseModel):
    """Error from web search tool."""

    type: Literal["web_search_error"] = "web_search_error"
    error_code: str
    message: str


class ServerToolUseBlock(BaseModel):
    """Server-side tool use block (e.g., web search)."""

    type: Literal["server_tool_use"] = "server_tool_use"
    id: str
    name: Literal["web_search"] = "web_search"
    input: dict[str, Any]


class WebSearchToolResultBlock(BaseModel):
    """Result from server-side web search tool."""

    type: Literal["web_search_tool_result"] = "web_search_tool_result"
    tool_use_id: str
    content: list[WebSearchResult] | WebSearchError


class SearchResultBlock(BaseModel):
    """Search result content block for embedding search results in context."""

    type: Literal["search_result"] = "search_result"
    title: str
    source: str
    content: list[dict[str, Any]]  # List of text blocks
    citations: CitationsConfig | None = None
    cache_control: CacheControl | None = None


ContentBlock = (
    ContentBlockText
    | ContentBlockImage
    | ContentBlockDocument
    | ToolUseBlock
    | ToolResultBlock
    | ServerToolUseBlock
    | WebSearchToolResultBlock
    | SearchResultBlock
)


class Message(BaseModel):
    """A message in the conversation."""

    role: Literal["user", "assistant"]
    content: str | list[ContentBlock]


class ToolDefinition(BaseModel):
    """Tool definition for function calling."""

    name: str
    description: str | None = None
    input_schema: dict[str, Any]
    cache_control: CacheControl | None = None


# Built-in tool types
class ToolBash(BaseModel):
    """Built-in bash tool for shell execution."""

    type: Literal["bash_20250124"] = "bash_20250124"
    name: Literal["bash"] = "bash"
    cache_control: CacheControl | None = None


class ToolTextEditor20250124(BaseModel):
    """Built-in text editor tool (January 2025 version)."""

    type: Literal["text_editor_20250124"] = "text_editor_20250124"
    name: Literal["str_replace_based_edit_tool"] = "str_replace_based_edit_tool"
    cache_control: CacheControl | None = None


class ToolTextEditor20250429(BaseModel):
    """Built-in text editor tool (April 2025 version)."""

    type: Literal["text_editor_20250429"] = "text_editor_20250429"
    name: Literal["str_replace_based_edit_tool"] = "str_replace_based_edit_tool"
    cache_control: CacheControl | None = None


class ToolTextEditor(BaseModel):
    """Built-in text editor tool (latest version with max_characters)."""

    type: Literal["text_editor_20250728"] = "text_editor_20250728"
    name: Literal["str_replace_based_edit_tool"] = "str_replace_based_edit_tool"
    max_characters: int | None = None
    cache_control: CacheControl | None = None


class UserLocation(BaseModel):
    """User location for web search tool."""

    type: Literal["approximate"] = "approximate"
    city: str | None = None
    region: str | None = None
    country: str | None = None
    timezone: str | None = None


class WebSearchTool(BaseModel):
    """Built-in web search tool for server-side searches."""

    type: Literal["web_search_20250305"] = "web_search_20250305"
    name: Literal["web_search"] = "web_search"
    max_uses: int | None = None
    allowed_domains: list[str] | None = None
    blocked_domains: list[str] | None = None
    user_location: UserLocation | None = None
    cache_control: CacheControl | None = None


# Union of all tool types
Tool = (
    ToolDefinition
    | ToolBash
    | ToolTextEditor20250124
    | ToolTextEditor20250429
    | ToolTextEditor
    | WebSearchTool
)


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
    tools: list[Tool] | None = None
    tool_choice: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    thinking: ThinkingConfig | None = None
    service_tier: Literal["auto", "standard_only"] | None = None


class CountTokensRequest(BaseModel):
    """Request body for POST /v1/messages/count_tokens - matches Anthropic's schema.

    Used to count tokens before sending a request, for cost estimation.
    """

    model: str
    messages: list[Message]
    system: str | list[dict[str, Any]] | None = None
    tools: list[Tool] | None = None
    tool_choice: dict[str, Any] | None = None
    thinking: ThinkingConfig | None = None
