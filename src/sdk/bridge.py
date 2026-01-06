"""Bridge between Anthropic Messages API and Claude Agent SDK.

This module translates incoming Anthropic API requests into Claude Agent SDK
calls and converts the SDK responses back to Anthropic API format.

Supports SDK message modes:
- forward: Pass through raw SDK messages (tool_use, tool_result blocks)
- formatted: Convert tool blocks to XML-tagged text format
- ignore: Strip SDK internal messages, only return final text
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, cast

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    query,
)
from claude_agent_sdk import (
    ToolUseBlock as SdkToolUseBlock,
)
from claude_agent_sdk.types import (
    HookEvent,
    HookMatcher,
    PermissionMode,
    SettingSource,
    SystemPromptPreset,
)

# Try to import ThinkingBlock - may not be available in all SDK versions
HAS_THINKING_BLOCK = False
SdkThinkingBlock: type[Any] | None = None
try:
    from claude_agent_sdk import ThinkingBlock as _SdkThinkingBlock

    SdkThinkingBlock = _SdkThinkingBlock
    HAS_THINKING_BLOCK = True
except ImportError:
    pass  # SdkThinkingBlock stays None, HAS_THINKING_BLOCK stays False

from ..core import settings  # noqa: E402
from ..models import (  # noqa: E402
    ContentBlockDeltaEvent,
    ContentBlockDeltaText,
    ContentBlockDeltaThinking,
    ContentBlockStartEvent,
    ContentBlockStopEvent,
    MessageDelta,
    MessageDeltaEvent,
    MessageDeltaUsage,
    MessagesRequest,
    MessagesResponse,
    MessageStartEvent,
    MessageStopEvent,
    ResponseContentBlock,
    SDKMessageMode,
    StreamEvent,
    ToolUseResponseBlock,
    Usage,
)
from ..models import TextBlock as ResponseTextBlock  # noqa: E402
from ..models import ThinkingBlock as ResponseThinkingBlock  # noqa: E402
from .hooks import get_configured_hooks  # noqa: E402
from .workspace import build_system_context, expand_command, get_workspace  # noqa: E402

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
        return [block for block in content_blocks if isinstance(block, ResponseTextBlock)]

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

    Also handles command expansion:
    - If request.command is set, expands that command
    - If user message starts with /command, expands that command
    """
    workspace = get_workspace(settings.cwd)
    parts = []

    for i, msg in enumerate(request.messages):
        role_prefix = "Human:" if msg.role == "user" else "Assistant:"

        if isinstance(msg.content, str):
            content = msg.content

            # Handle command expansion for the last user message
            if msg.role == "user" and i == len(request.messages) - 1:
                # Explicit command parameter takes precedence
                if request.command and request.command in workspace.commands:
                    command_content = workspace.commands[request.command]
                    if content:
                        content = f"{command_content}\n\nUser input: {content}"
                    else:
                        content = command_content
                else:
                    # Check for /command in prompt
                    content, _ = expand_command(content, workspace)

            parts.append(f"{role_prefix} {content}")
        else:
            # Handle content blocks
            text_parts: list[str] = []
            for block in msg.content:
                if hasattr(block, "text"):
                    text_parts.append(getattr(block, "text"))
                elif hasattr(block, "type") and getattr(block, "type") == "tool_result":
                    text_parts.append(f"[Tool Result: {getattr(block, 'content', '')}]")
            if text_parts:
                parts.append(f"{role_prefix} {' '.join(text_parts)}")

    return "\n\n".join(parts)


def build_claude_options(request: MessagesRequest) -> ClaudeAgentOptions:
    """Build ClaudeAgentOptions from the request and server settings."""

    # Load workspace configuration
    workspace = get_workspace(settings.cwd)
    workspace_context = build_system_context(workspace)

    # Determine system prompt
    system_prompt: str | SystemPromptPreset | None = None
    if settings.system_prompt_mode == "claude_code":
        system_prompt = SystemPromptPreset(type="preset", preset="claude_code")
    elif settings.custom_system_prompt:
        system_prompt = settings.custom_system_prompt

    # Override with request system prompt if provided
    if request.system:
        if isinstance(request.system, str):
            system_prompt = request.system
        elif isinstance(request.system, list):
            # Concatenate system prompt blocks
            system_prompt = " ".join(
                block.get("text", "") for block in request.system if block.get("type") == "text"
            )

    # Inject workspace context into system prompt
    if workspace_context:
        if system_prompt is None:
            system_prompt = workspace_context
        elif isinstance(system_prompt, str):
            system_prompt = f"{system_prompt}\n\n{workspace_context}"
        # Note: SystemPromptPreset doesn't support appending, workspace context
        # will be applied separately via the prompt if using preset

    # Build options
    options = ClaudeAgentOptions(
        model=MODEL_MAP.get(request.model, request.model),
        max_turns=settings.max_turns,
        permission_mode=cast(PermissionMode, settings.permission_mode)
        if settings.permission_mode
        else None,
    )

    # Set system prompt
    if system_prompt:
        options.system_prompt = system_prompt

    # Set working directory (resolve to absolute path)
    if settings.cwd:
        cwd_path = Path(settings.cwd)
        if not cwd_path.is_absolute():
            cwd_path = cwd_path.resolve()
        options.cwd = cwd_path

    # Set allowed tools
    allowed = settings.get_allowed_tools_list()
    if allowed:
        options.allowed_tools = allowed

    # Set setting sources
    sources = settings.get_setting_sources_list()
    if sources:
        options.setting_sources = cast(list[SettingSource], sources)

    # Add extended thinking if requested
    if request.thinking:
        options.max_thinking_tokens = request.thinking.budget_tokens

    # Add SDK hooks based on settings
    hooks_config = settings.get_hooks_config()
    hooks = get_configured_hooks(
        audit_enabled=hooks_config.audit_enabled,
        permission_enabled=hooks_config.permission_enabled,
        rate_limit_enabled=hooks_config.rate_limit_enabled,
        rate_limit_requests_per_minute=hooks_config.rate_limit_requests_per_minute,
        deny_patterns=hooks_config.deny_patterns if hooks_config.deny_patterns else None,
    )
    if hooks:
        options.hooks = cast(dict[HookEvent, list[HookMatcher]], hooks)

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
    thinking_blocks: list[ResponseThinkingBlock] = []
    full_text = ""
    input_tokens = 0
    output_tokens = 0
    cache_creation_input_tokens = None
    cache_read_input_tokens = None

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    full_text += block.text
                elif (
                    HAS_THINKING_BLOCK and SdkThinkingBlock and isinstance(block, SdkThinkingBlock)
                ):
                    # Extract thinking block from extended thinking response
                    thinking_blocks.append(
                        ResponseThinkingBlock(
                            thinking=block.thinking,
                            signature=getattr(block, "signature", None),
                        )
                    )
                elif isinstance(block, SdkToolUseBlock):
                    content_blocks.append(
                        ToolUseResponseBlock(
                            id=block.id,
                            name=block.name,
                            input=block.input,
                        )
                    )
        elif isinstance(message, ResultMessage):
            # Extract usage from result - prefer actual values over estimates
            if hasattr(message, "usage") and message.usage:
                usage = message.usage
                # Try to get actual token counts from various possible attributes
                if isinstance(usage, dict):
                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)
                    cache_creation_input_tokens = usage.get("cache_creation_input_tokens")
                    cache_read_input_tokens = usage.get("cache_read_input_tokens")
                else:
                    input_tokens = getattr(usage, "input_tokens", 0)
                    output_tokens = getattr(usage, "output_tokens", 0)
                    cache_creation_input_tokens = getattr(
                        usage, "cache_creation_input_tokens", None
                    )
                    cache_read_input_tokens = getattr(usage, "cache_read_input_tokens", None)

    # Build final content blocks - thinking blocks first, then text, then tools
    final_blocks: list[ResponseContentBlock] = []

    # Add thinking blocks first (if any)
    final_blocks.extend(thinking_blocks)

    # Add collected text as a single block
    if full_text:
        final_blocks.append(ResponseTextBlock(text=full_text))

    # Add tool use blocks
    final_blocks.extend(content_blocks)

    # Apply SDK message mode (only affects text and tool blocks, not thinking)
    final_blocks = apply_message_mode(final_blocks, mode)

    # Only estimate tokens if SDK provided no usage data at all
    # This is a fallback for older SDK versions
    if input_tokens == 0 and output_tokens == 0:
        import logging

        logging.getLogger("claude8code").warning(
            "No token usage from SDK - using estimates. Token counts may be inaccurate."
        )
        input_tokens = len(prompt) // 4
        output_tokens = len(full_text) // 4

    return MessagesResponse(
        id=generate_message_id(),
        content=final_blocks,
        model=request.model,
        stop_reason="end_turn",
        usage=Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
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
                # Handle thinking blocks (extended thinking)
                if HAS_THINKING_BLOCK and SdkThinkingBlock and isinstance(block, SdkThinkingBlock):
                    # Close any open text block first
                    if text_block_started:
                        yield ContentBlockStopEvent(index=content_index)
                        content_index += 1
                        current_text = ""
                        text_block_started = False

                    # Start thinking block
                    yield ContentBlockStartEvent(
                        index=content_index,
                        content_block=ResponseThinkingBlock(
                            thinking="",
                            signature=getattr(block, "signature", None),
                        ),
                    )

                    # Stream thinking content
                    if block.thinking:
                        yield ContentBlockDeltaEvent(
                            index=content_index,
                            delta=ContentBlockDeltaThinking(thinking=block.thinking),
                        )
                        output_tokens += len(block.thinking) // 4

                    # Close thinking block
                    yield ContentBlockStopEvent(index=content_index)
                    content_index += 1

                elif isinstance(block, TextBlock):
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

        elif isinstance(message, ResultMessage):
            # Extract actual token counts from SDK result
            if hasattr(message, "usage") and message.usage:
                usage = message.usage
                if isinstance(usage, dict):
                    actual_output = usage.get("output_tokens", 0)
                else:
                    actual_output = getattr(usage, "output_tokens", 0)
                if actual_output > 0:
                    output_tokens = actual_output

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

    def __init__(self) -> None:
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

    async def close_all(self) -> None:
        """Close all sessions."""
        async with self._lock:
            for client in self._sessions.values():
                await client.__aexit__(None, None, None)
            self._sessions.clear()


# Global session manager (for explicit session management API)
session_manager = SessionManager()


# Re-export session pool for convenience
