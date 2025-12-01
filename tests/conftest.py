"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def sample_messages_request():
    """Sample Anthropic Messages API request."""
    return {
        "model": "claude-sonnet-4-5-20250514",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "Hello, Claude!"}
        ]
    }


@pytest.fixture
def sample_streaming_request():
    """Sample streaming request."""
    return {
        "model": "claude-sonnet-4-5-20250514",
        "max_tokens": 1024,
        "stream": True,
        "messages": [
            {"role": "user", "content": "Tell me a story"}
        ]
    }


@pytest.fixture
def sample_tool_request():
    """Sample request with tools."""
    return {
        "model": "claude-sonnet-4-5-20250514",
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": "What's the weather in London?"}
        ],
        "tools": [
            {
                "name": "get_weather",
                "description": "Get current weather for a location",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"}
                    },
                    "required": ["location"]
                }
            }
        ]
    }
