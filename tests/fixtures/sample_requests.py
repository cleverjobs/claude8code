"""Sample request data for testing."""

from src.models import MessagesRequest, Message, ContentBlock


# Simple text requests
SIMPLE_MESSAGE_REQUEST = {
    "model": "claude-sonnet-4-5-20250514",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Hello, Claude!"}],
}

MESSAGE_WITH_SYSTEM = {
    "model": "claude-sonnet-4-5-20250514",
    "max_tokens": 1024,
    "system": "You are a helpful assistant.",
    "messages": [{"role": "user", "content": "Hello!"}],
}

# Streaming requests
STREAMING_REQUEST = {
    "model": "claude-sonnet-4-5-20250514",
    "max_tokens": 1024,
    "stream": True,
    "messages": [{"role": "user", "content": "Tell me a story"}],
}

# Multi-turn conversation
CONVERSATION_REQUEST = {
    "model": "claude-sonnet-4-5-20250514",
    "max_tokens": 1024,
    "messages": [
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there! How can I help you?"},
        {"role": "user", "content": "What's 2+2?"},
    ],
}

# Request with content blocks (multimodal)
CONTENT_BLOCKS_REQUEST = {
    "model": "claude-sonnet-4-5-20250514",
    "max_tokens": 1024,
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What do you see in this image?"},
            ],
        }
    ],
}

# Request with tools
TOOL_REQUEST = {
    "model": "claude-sonnet-4-5-20250514",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "What's the weather in London?"}],
    "tools": [
        {
            "name": "get_weather",
            "description": "Get current weather for a location",
            "input_schema": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        }
    ],
}

# Extended thinking (ultrathink) request
THINKING_REQUEST = {
    "model": "claude-sonnet-4-5-20250514",
    "max_tokens": 16000,
    "thinking": {"type": "enabled", "budget_tokens": 10000},
    "messages": [{"role": "user", "content": "Solve this complex problem..."}],
}

# Request with all models
MODELS = [
    "claude-sonnet-4-5-20250514",
    "claude-opus-4-20250514",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
]


def make_request(
    content: str,
    model: str = "claude-sonnet-4-5-20250514",
    max_tokens: int = 1024,
    stream: bool = False,
    system: str | None = None,
) -> dict:
    """Create a simple message request.

    Args:
        content: User message content
        model: Model to use
        max_tokens: Maximum tokens in response
        stream: Whether to stream response
        system: Optional system prompt

    Returns:
        Request dictionary
    """
    request = {
        "model": model,
        "max_tokens": max_tokens,
        "stream": stream,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        request["system"] = system
    return request
