"""Pytest configuration and fixtures."""

import os
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# Check if we should use mocked Claude API
USE_CLAUDE_MOCK = os.environ.get("USE_CLAUDE_MOCK", "true").lower() == "true"


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


@pytest.fixture
def mock_assistant_message():
    """Create a mock AssistantMessage."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="Hello! I'm Claude, an AI assistant.")]
    return mock_msg


@pytest.fixture
def mock_result_message():
    """Create a mock ResultMessage."""
    mock_msg = MagicMock()
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=20)
    return mock_msg


@pytest.fixture
def mock_claude_query(mock_assistant_message, mock_result_message):
    """Mock the claude_agent_sdk.query function."""
    async def mock_query(*args, **kwargs) -> AsyncIterator:
        yield mock_assistant_message
        yield mock_result_message

    return mock_query


@pytest.fixture
def client():
    """Create a FastAPI test client with mocked Claude API."""
    if USE_CLAUDE_MOCK:
        # Mock the entire claude_agent_sdk module
        mock_sdk = MagicMock()

        # Create mock message types
        mock_assistant = MagicMock()
        mock_assistant.content = [MagicMock(text="Hello! I'm Claude.")]

        mock_result = MagicMock()
        mock_result.usage = MagicMock(input_tokens=10, output_tokens=15)

        async def mock_query(*args, **kwargs):
            yield mock_assistant
            yield mock_result

        mock_sdk.query = mock_query
        mock_sdk.ClaudeAgentOptions = MagicMock
        mock_sdk.ClaudeSDKClient = MagicMock()
        mock_sdk.AssistantMessage = type(mock_assistant)
        mock_sdk.ResultMessage = type(mock_result)
        mock_sdk.TextBlock = MagicMock
        mock_sdk.ToolUseBlock = MagicMock
        mock_sdk.ToolResultBlock = MagicMock
        mock_sdk.UserMessage = MagicMock

        with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk}):
            # Import after patching
            from claude8code.server import app
            return TestClient(app)
    else:
        from claude8code.server import app
        return TestClient(app)


@pytest.fixture
def mock_session_manager():
    """Mock the session manager for testing."""
    mock_manager = MagicMock()
    mock_manager.get_or_create_session = AsyncMock(
        return_value=("session_123", MagicMock())
    )
    mock_manager.close_session = AsyncMock(return_value=True)
    mock_manager.close_all = AsyncMock()
    return mock_manager
