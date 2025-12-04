"""Bridge between Anthropic Messages API and Claude Agent SDK.

This module translates incoming Anthropic API requests into Claude Agent SDK
calls and converts the SDK responses back to Anthropic API format.

Supports SDK message modes:
- forward: Pass through raw SDK messages (tool_use, tool_result blocks)
- formatted: Convert tool blocks to XML-tagged text format
- ignore: Strip SDK internal messages, only return final text
"""

from __future__ import annotations

import uuid
import json
import asyncio
from typing import AsyncIterator, Any
from pathlib import Path

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    AssistantMessage,
    UserMessage,
    TextBlock,
    ToolUseBlock as SdkToolUseBlock,
    ToolResultBlock as SdkToolResultBlock,
    ResultMessage,
)

from .config import settings
from .models import (
    MessagesRequest,
    MessagesResponse,
    Usage,
    TextBlock as ResponseTextBlock,
    ToolUseResponseBlock,
    ResponseContentBlock,
    StreamEvent,
    MessageStartEvent,
    ContentBlockStartEvent,
    ContentBlockDeltaEvent,
    ContentBlockStopEvent,
    MessageDeltaEvent,
    MessageStopEvent,
    ContentBlockDeltaText,
    MessageDelta,
    MessageDeltaUsage,
    SDKMessageMode,
)


# Model mapping: n8n model names -> Claude Agent SDK models
MODEL_MAP = {
    # Claude 4.5 models (latest)
    "claude-opus-4-5-20251101": "claude-opus-4-5-20251101",
    "claude-sonnet-4-5-20250514": "claude-sonnet-4-5-20250514",
    "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
    # Claude 4 models
    "claude-sonnet-4-20250514": "claude-sonnet-4-20250514",
    "claude-opus-4-20250514": "claude-opus-4-20250514",
    # Aliases for n8n compatibility
    "claude-3-5-sonnet-latest": "claude-sonnet-4-5-20250514",
    "claude-3-5-sonnet-20241022": "claude-sonnet-4-5-20250514",
    "claude-3-opus-latest": "claude-opus-4-5-20251101",
    "claude-3-5-haiku-latest": "claude-haiku-4-5-20251001",
    # Extended ultrathink alias
    "claude-opus-4-5": "claude-opus-4-5-20251101",
}


def get_sdk_message_mode(header_value: str | None = None) -> SDKMessageMode:
    """Get the SDK message mode from header or settings.

    Args:
        header_value: Value from x-sdk-message-mode header (optional)

    Returns:
        SDKMessageMode to use for this request
    """
    # Header override takes precedence
    if header_value:
        try:
            return SDKMessageMode(header_value.lower())
        except ValueError:
            pass  # Fall back to settings

    # Use settings default
    mode = settings.sdk_message_mode
    if isinstance(mode, SDKMessageMode):
        return mode
    if isinstance(mode, str):
        try:
            return SDKMessageMode(mode.lower())
        except ValueError:
            pass

    return SDKMessageMode.FORWARD


def format_tool_use_as_xml(name: str, input_data: dict[str, Any]) -> str:
    """Format a tool use block as XML-tagged text.

    Args:
        name: Tool name
        input_data: Tool input as dict

    Returns:
        XML-formatted string
    """
    input_json = json.dumps(input_data, indent=2)
    return f'<tool_use name="{name}">\n{input_json}\n</tool_use>'


def format_tool_result_as_xml(content: str) -> str:
    """Format a tool result as XML-tagged text.

    Args:
        content: Tool result content

    Returns:
        XML-formatted string
    """
    return f"<tool_result>\n{content}\n</tool_result>"


def apply_message_mode(
    content_blocks: list[ResponseContentBlock],
    mode: SDKMessageMode,
) -> list[ResponseContentBlock]:
    """Apply SDK message mode to response content blocks.

    Args:
        content_blocks: Original response blocks
        mode: SDK message mode to apply

    Returns:
        Transformed content blocks based on mode
    """
    if mode == SDKMessageMode.FORWARD:
        # Pass through unchanged
        return content_blocks

    if mode == SDKMessageMode.IGNORE:
        # Only keep text blocks
        return [
            block for block in content_blocks
            if isinstance(block, ResponseTextBlock)
        ]

    if mode == SDKMessageMode.FORMATTED:
        # Convert tool blocks to XML-formatted text
        result_parts: list[str] = []

        for block in content_blocks:
            if isinstance(block, ResponseTextBlock):
                result_parts.append(block.text)
            elif isinstance(block, ToolUseResponseBlock):
                result_parts.append(format_tool_use_as_xml(block.name, block.input))

        # Combine into single text block
        if result_parts:
            combined_text = "\n\n".join(part for part in result_parts if part)
            return [ResponseTextBlock(text=combined_text)]
        return []

    return content_blocks


def generate_message_id() -> str:
    """Generate a message ID in Anthropic format."""
    return f"msg_{uuid.uuid4().hex[:24]}"


def build_prompt_from_messages(request: MessagesRequest) -> str:
    """Convert Anthropic messages array to a single prompt for Claude Agent SDK.
    
    The Claude Agent SDK's query() function takes a single prompt string,
    so we need to format the conversation history appropriately.
    """
    parts = []
    
    for msg in request.messages:
        role_prefix = "Human:" if msg.role == "user" else "Assistant:"
        
        if isinstance(msg.content, str):
            parts.append(f"{role_prefix} {msg.content}")
        else:
            # Handle content blocks
            text_parts = []
            for block in msg.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
                elif hasattr(block, "type") and block.type == "tool_result":
                    text_parts.append(f"[Tool Result: {block.content}]")
            if text_parts:
                parts.append(f"{role_prefix} {' '.join(text_parts)}")
    
    return "\n\n".join(parts)


def build_claude_options(request: MessagesRequest) -> ClaudeAgentOptions:
    """Build ClaudeAgentOptions from the request and server settings."""
    
    # Determine system prompt
    system_prompt: str | dict[str, str] | None = None
    if settings.system_prompt_mode == "claude_code":
        system_prompt = {"type": "preset", "preset": "claude_code"}
    elif settings.custom_system_prompt:
        system_prompt = settings.custom_system_prompt
    
    # Override with request system prompt if provided
    if request.system:
        if isinstance(request.system, str):
            system_prompt = request.system
        elif isinstance(request.system, list):
            # Concatenate system prompt blocks
            system_prompt = " ".join(
                block.get("text", "") for block in request.system 
                if block.get("type") == "text"
            )
    
    # Build options
    options = ClaudeAgentOptions(
        model=MODEL_MAP.get(request.model, request.model),
        max_turns=settings.max_turns,
        permission_mode=settings.permission_mode,
    )
    
    # Set system prompt
    if system_prompt:
        options.system_prompt = system_prompt
    
    # Set working directory
    if settings.cwd:
        options.cwd = Path(settings.cwd)
    
    # Set allowed tools
    allowed = settings.get_allowed_tools_list()
    if allowed:
        options.allowed_tools = allowed
    
    # Set setting sources
    sources = settings.get_setting_sources_list()
    if sources:
        options.setting_sources = sources

    # Add extended thinking if requested
    if request.thinking:
        options.thinking = {
            "type": request.thinking.type,
            "budget_tokens": request.thinking.budget_tokens,
        }

    return options


async def process_request(
    request: MessagesRequest,
    sdk_message_mode: SDKMessageMode | None = None,
) -> MessagesResponse:
    """Process a non-streaming Messages API request.

    Converts the request to Claude Agent SDK format, executes it,
    and returns an Anthropic-compatible response.

    Args:
        request: The incoming messages request
        sdk_message_mode: Optional mode override (uses settings default if None)
    """
    prompt = build_prompt_from_messages(request)
    options = build_claude_options(request)

    # Get the message mode to use
    mode = sdk_message_mode or get_sdk_message_mode()

    # Collect all response content
    content_blocks: list[ResponseContentBlock] = []
    full_text = ""
    input_tokens = 0
    output_tokens = 0

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    full_text += block.text
                elif isinstance(block, SdkToolUseBlock):
                    content_blocks.append(ToolUseResponseBlock(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    ))
        elif isinstance(message, ResultMessage):
            # Extract usage from result if available
            if hasattr(message, "usage"):
                input_tokens = getattr(message.usage, "input_tokens", 0)
                output_tokens = getattr(message.usage, "output_tokens", 0)

    # Add collected text as a single block
    if full_text:
        content_blocks.insert(0, ResponseTextBlock(text=full_text))

    # Apply SDK message mode
    content_blocks = apply_message_mode(content_blocks, mode)

    # Estimate tokens if not provided
    if input_tokens == 0:
        input_tokens = len(prompt) // 4  # Rough estimate
    if output_tokens == 0:
        output_tokens = len(full_text) // 4

    return MessagesResponse(
        id=generate_message_id(),
        content=content_blocks,
        model=request.model,
        stop_reason="end_turn",
        usage=Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )


async def process_request_streaming(
    request: MessagesRequest,
    sdk_message_mode: SDKMessageMode | None = None,
) -> AsyncIterator[StreamEvent]:
    """Process a streaming Messages API request.

    Yields SSE events matching Anthropic's streaming format.

    Args:
        request: The incoming messages request
        sdk_message_mode: Optional mode override (uses settings default if None)
    """
    prompt = build_prompt_from_messages(request)
    options = build_claude_options(request)

    # Get the message mode to use
    mode = sdk_message_mode or get_sdk_message_mode()

    message_id = generate_message_id()

    # Emit message_start
    yield MessageStartEvent(
        message=MessagesResponse(
            id=message_id,
            content=[],
            model=request.model,
            stop_reason=None,
            usage=Usage(input_tokens=0, output_tokens=0),
        )
    )

    content_index = 0
    current_text = ""
    output_tokens = 0
    text_block_started = False

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    # Start new text block if not started
                    if not text_block_started:
                        yield ContentBlockStartEvent(
                            index=content_index,
                            content_block=ResponseTextBlock(text=""),
                        )
                        text_block_started = True

                    # Stream the text in chunks
                    new_text = block.text
                    if new_text:
                        yield ContentBlockDeltaEvent(
                            index=content_index,
                            delta=ContentBlockDeltaText(text=new_text),
                        )
                        current_text += new_text
                        output_tokens += len(new_text) // 4

                elif isinstance(block, SdkToolUseBlock):
                    # Handle tool use based on mode
                    if mode == SDKMessageMode.IGNORE:
                        # Skip tool use blocks entirely
                        continue

                    if mode == SDKMessageMode.FORMATTED:
                        # Convert tool use to XML-formatted text
                        xml_text = format_tool_use_as_xml(block.name, block.input)

                        if not text_block_started:
                            yield ContentBlockStartEvent(
                                index=content_index,
                                content_block=ResponseTextBlock(text=""),
                            )
                            text_block_started = True

                        # Add separator if we already have text
                        if current_text:
                            xml_text = "\n\n" + xml_text

                        yield ContentBlockDeltaEvent(
                            index=content_index,
                            delta=ContentBlockDeltaText(text=xml_text),
                        )
                        current_text += xml_text
                        output_tokens += len(xml_text) // 4

                    else:  # FORWARD mode
                        # Close current text block if open
                        if text_block_started:
                            yield ContentBlockStopEvent(index=content_index)
                            content_index += 1
                            current_text = ""
                            text_block_started = False

                        # Emit tool use block
                        yield ContentBlockStartEvent(
                            index=content_index,
                            content_block=ToolUseResponseBlock(
                                id=block.id,
                                name=block.name,
                                input=block.input,
                            ),
                        )
                        yield ContentBlockStopEvent(index=content_index)
                        content_index += 1

    # Close any open text block
    if text_block_started:
        yield ContentBlockStopEvent(index=content_index)

    # Emit message_delta with stop reason
    yield MessageDeltaEvent(
        delta=MessageDelta(stop_reason="end_turn"),
        usage=MessageDeltaUsage(output_tokens=output_tokens),
    )

    # Emit message_stop
    yield MessageStopEvent()


class SessionManager:
    """Manages Claude SDK client sessions for multi-turn conversations.

    This enables using ClaudeSDKClient for conversations that need
    persistence, custom tools, or hooks.

    NOTE: For connection pooling with automatic context clearing,
    use the SessionPool from session_pool.py instead.
    """

    def __init__(self):
        self._sessions: dict[str, ClaudeSDKClient] = {}
        self._lock = asyncio.Lock()

    async def get_or_create_session(
        self,
        session_id: str | None = None,
        options: ClaudeAgentOptions | None = None,
    ) -> tuple[str, ClaudeSDKClient]:
        """Get existing session or create a new one."""
        async with self._lock:
            if session_id and session_id in self._sessions:
                return session_id, self._sessions[session_id]

            # Create new session
            new_id = session_id or f"session_{uuid.uuid4().hex[:16]}"
            client = ClaudeSDKClient(options=options)
            await client.__aenter__()
            self._sessions[new_id] = client
            return new_id, client

    async def close_session(self, session_id: str) -> bool:
        """Close and remove a session."""
        async with self._lock:
            if session_id in self._sessions:
                client = self._sessions.pop(session_id)
                await client.__aexit__(None, None, None)
                return True
            return False

    async def close_all(self):
        """Close all sessions."""
        async with self._lock:
            for client in self._sessions.values():
                await client.__aexit__(None, None, None)
            self._sessions.clear()


# Global session manager (for explicit session management API)
session_manager = SessionManager()


# Re-export session pool for convenience
from .session_pool import (
    SessionPool,
    PooledSession,
    get_pool,
    init_pool,
    shutdown_pool,
)
