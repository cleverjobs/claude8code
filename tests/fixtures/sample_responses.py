"""Sample response data for testing."""

from src.models import (
    MessagesResponse,
    Usage,
    TextBlock,
    ThinkingBlock,
    ToolUseResponseBlock,
)


# Simple text response
SIMPLE_RESPONSE = {
    "id": "msg_test123",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-4-5-20250514",
    "content": [{"type": "text", "text": "Hello! I'm Claude, an AI assistant."}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 10, "output_tokens": 15},
}

# Response with tool use
TOOL_USE_RESPONSE = {
    "id": "msg_tool456",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-4-5-20250514",
    "content": [
        {
            "type": "tool_use",
            "id": "toolu_abc123",
            "name": "get_weather",
            "input": {"location": "London"},
        }
    ],
    "stop_reason": "tool_use",
    "usage": {"input_tokens": 25, "output_tokens": 30},
}

# Response with thinking (extended thinking)
THINKING_RESPONSE = {
    "id": "msg_think789",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-4-5-20250514",
    "content": [
        {
            "type": "thinking",
            "thinking": "Let me analyze this step by step...",
            "signature": "sig_abc123",
        },
        {"type": "text", "text": "Here's my analysis..."},
    ],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 50, "output_tokens": 200},
}

# Response with cache tokens
CACHED_RESPONSE = {
    "id": "msg_cache999",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-4-5-20250514",
    "content": [{"type": "text", "text": "Cached response content"}],
    "stop_reason": "end_turn",
    "usage": {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_creation_input_tokens": 80,
        "cache_read_input_tokens": 20,
    },
}

# Error response
ERROR_RESPONSE = {
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "message": "Invalid request: missing required field 'messages'",
    },
}


def make_response(
    text: str,
    model: str = "claude-sonnet-4-5-20250514",
    input_tokens: int = 10,
    output_tokens: int = 15,
    stop_reason: str = "end_turn",
) -> dict:
    """Create a simple message response.

    Args:
        text: Response text content
        model: Model that generated response
        input_tokens: Input token count
        output_tokens: Output token count
        stop_reason: Why generation stopped

    Returns:
        Response dictionary
    """
    import uuid

    return {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


# Streaming event samples
STREAM_MESSAGE_START = {
    "type": "message_start",
    "message": {
        "id": "msg_stream001",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-5-20250514",
        "content": [],
        "stop_reason": None,
        "usage": {"input_tokens": 10, "output_tokens": 0},
    },
}

STREAM_CONTENT_BLOCK_START = {
    "type": "content_block_start",
    "index": 0,
    "content_block": {"type": "text", "text": ""},
}

STREAM_CONTENT_DELTA = {
    "type": "content_block_delta",
    "index": 0,
    "delta": {"type": "text_delta", "text": "Hello"},
}

STREAM_CONTENT_BLOCK_STOP = {"type": "content_block_stop", "index": 0}

STREAM_MESSAGE_DELTA = {
    "type": "message_delta",
    "delta": {"stop_reason": "end_turn"},
    "usage": {"output_tokens": 5},
}

STREAM_MESSAGE_STOP = {"type": "message_stop"}
