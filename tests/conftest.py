"""Pytest configuration and fixtures."""

import os
from collections.abc import AsyncIterator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Check if we should use mocked Claude API
USE_CLAUDE_MOCK = os.environ.get("USE_CLAUDE_MOCK", "true").lower() == "true"


# Import SDK types for proper isinstance() checks in mocks
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock  # noqa: E402


@pytest.fixture
def sample_messages_request() -> dict[str, Any]:
    """Sample Anthropic Messages API request."""
    return {
        "model": "claude-sonnet-4-5-20250514",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "Hello, Claude!"}],
    }


@pytest.fixture
def sample_streaming_request() -> dict[str, Any]:
    """Sample streaming request."""
    return {
        "model": "claude-sonnet-4-5-20250514",
        "max_tokens": 1024,
        "stream": True,
        "messages": [{"role": "user", "content": "Tell me a story"}],
    }


@pytest.fixture
def sample_tool_request() -> dict[str, Any]:
    """Sample request with tools."""
    return {
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


@pytest.fixture
def mock_assistant_message() -> MagicMock:
    """Create a mock AssistantMessage."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="Hello! I'm Claude, an AI assistant.")]
    return mock_msg


@pytest.fixture
def mock_result_message() -> MagicMock:
    """Create a mock ResultMessage."""
    mock_msg = MagicMock()
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=20)
    return mock_msg


@pytest.fixture
def mock_claude_query(mock_assistant_message: MagicMock, mock_result_message: MagicMock) -> Any:
    """Mock the claude_agent_sdk.query function."""

    async def mock_query(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
        yield mock_assistant_message
        yield mock_result_message

    return mock_query


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create a FastAPI test client with mocked Claude API."""
    from src.api.app import app

    if USE_CLAUDE_MOCK:
        # Create mock message types using spec= for proper isinstance() checks
        mock_text_block = MagicMock(spec=TextBlock)
        mock_text_block.text = "Hello! I'm Claude."

        mock_assistant = MagicMock(spec=AssistantMessage)
        mock_assistant.content = [mock_text_block]

        mock_usage = MagicMock()
        mock_usage.input_tokens = 10
        mock_usage.output_tokens = 15

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.usage = mock_usage

        async def mock_query(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
            yield mock_assistant
            yield mock_result

        # Patch the query function where it's used (in bridge module)
        # Use start/stop to keep patch active during test
        patcher = patch("src.sdk.bridge.query", mock_query)
        patcher.start()
        yield TestClient(app)
        patcher.stop()
    else:
        yield TestClient(app)


@pytest.fixture
def mock_session_manager() -> MagicMock:
    """Mock the session manager for testing."""
    mock_manager = MagicMock()
    mock_manager.get_or_create_session = AsyncMock(return_value=("session_123", MagicMock()))
    mock_manager.close_session = AsyncMock(return_value=True)
    mock_manager.close_all = AsyncMock()
    return mock_manager
