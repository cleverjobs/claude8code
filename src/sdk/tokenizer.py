"""Token counting using tiktoken for API compatibility.

This module provides token counting functionality using the tiktoken library.
It uses the cl100k_base encoding which is similar to what Claude uses.

Gracefully degrades if tiktoken is not installed - returns None for counts.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Try to import tiktoken (optional dependency)
try:
    import tiktoken

    _encoder = tiktoken.get_encoding("cl100k_base")
    TIKTOKEN_AVAILABLE = True
    logger.info("tiktoken loaded successfully - token counting enabled")
except ImportError:
    _encoder = None  # type: ignore[assignment]
    TIKTOKEN_AVAILABLE = False
    logger.warning("tiktoken not installed - token counting will return estimates")


def count_tokens(text: str) -> int:
    """Count tokens in a text string.

    Args:
        text: The text to count tokens for.

    Returns:
        Number of tokens, or estimate if tiktoken not available.
    """
    if _encoder is not None:
        return len(_encoder.encode(text))
    # Fallback: rough estimate (4 chars per token average)
    return len(text) // 4


def count_content_block_tokens(block: dict[str, Any]) -> int:
    """Count tokens in a content block.

    Handles text, image, document, tool_use, and tool_result blocks.

    Args:
        block: A content block dictionary.

    Returns:
        Token count for the block.
    """
    block_type = block.get("type", "text")
    tokens = 0

    if block_type == "text":
        tokens = count_tokens(block.get("text", ""))
    elif block_type == "image":
        # Images have a fixed token overhead (roughly 85 tokens per tile)
        # For simplicity, estimate ~1000 tokens for an average image
        tokens = 1000
    elif block_type == "document":
        # PDFs are converted to ~1500 tokens per page on average
        # Estimate based on base64 data size if available
        data = block.get("source", {}).get("data", "")
        # Base64 is ~1.33x the original size, PDF text extraction varies
        # Rough estimate: 1 token per 6 base64 chars
        tokens = len(data) // 6 if data else 1500
    elif block_type == "tool_use":
        # Count the tool name and input
        tokens = count_tokens(block.get("name", ""))
        input_data = block.get("input", {})
        tokens += count_tokens(json.dumps(input_data))
    elif block_type == "tool_result":
        content = block.get("content", "")
        if isinstance(content, str):
            tokens = count_tokens(content)
        elif isinstance(content, list):
            tokens = sum(count_content_block_tokens(b) for b in content)

    return tokens


def count_message_tokens(message: dict[str, Any]) -> int:
    """Count tokens in a message.

    Args:
        message: A message dictionary with role and content.

    Returns:
        Token count for the message.
    """
    tokens = 0

    # Role overhead (roughly 4 tokens for role marker)
    tokens += 4

    content = message.get("content", "")
    if isinstance(content, str):
        tokens += count_tokens(content)
    elif isinstance(content, list):
        tokens += sum(count_content_block_tokens(block) for block in content)

    return tokens


def count_tool_definition_tokens(tool: dict[str, Any]) -> int:
    """Count tokens in a tool definition.

    Args:
        tool: A tool definition dictionary.

    Returns:
        Token count for the tool.
    """
    tokens = 0

    # Tool name and description
    tokens += count_tokens(tool.get("name", ""))
    if tool.get("description"):
        tokens += count_tokens(tool["description"])

    # Input schema (JSON)
    input_schema = tool.get("input_schema", {})
    tokens += count_tokens(json.dumps(input_schema))

    return tokens


def count_system_prompt_tokens(system: str | list[dict[str, Any]] | None) -> int:
    """Count tokens in a system prompt.

    Args:
        system: System prompt as string or list of content blocks.

    Returns:
        Token count for the system prompt.
    """
    if system is None:
        return 0

    if isinstance(system, str):
        return count_tokens(system)

    # List of content blocks
    tokens = 0
    for block in system:
        if isinstance(block, dict):
            tokens += count_content_block_tokens(block)
    return tokens


def count_request_tokens(
    messages: list[dict[str, Any]],
    system: str | list[dict[str, Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> int:
    """Count total input tokens for a request.

    Args:
        messages: List of messages.
        system: Optional system prompt.
        tools: Optional list of tool definitions.

    Returns:
        Total token count for the request.
    """
    tokens = 0

    # System prompt tokens
    tokens += count_system_prompt_tokens(system)

    # Message tokens
    for message in messages:
        tokens += count_message_tokens(message)

    # Tool definition tokens
    if tools:
        for tool in tools:
            tokens += count_tool_definition_tokens(tool)

    # Add overhead for message formatting (~10 tokens)
    tokens += 10

    return tokens
