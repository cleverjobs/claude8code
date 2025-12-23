"""Integration tests for streaming endpoints."""

import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock


# Check if we should use mocked Claude API
USE_CLAUDE_MOCK = os.environ.get("USE_CLAUDE_MOCK", "true").lower() == "true"


@pytest.fixture
def streaming_client():
    """Create a FastAPI test client configured for streaming tests."""
    from src.api.app import app

    if USE_CLAUDE_MOCK:
        # Create mock messages that simulate streaming response
        mock_text_block = MagicMock(spec=TextBlock)
        mock_text_block.text = "Hello! I'm Claude, streaming."

        mock_assistant = MagicMock(spec=AssistantMessage)
        mock_assistant.content = [mock_text_block]

        mock_usage = MagicMock()
        mock_usage.input_tokens = 15
        mock_usage.output_tokens = 25

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.usage = mock_usage

        async def mock_query(*args, **kwargs):
            yield mock_assistant
            yield mock_result

        patcher = patch("src.sdk.bridge.query", mock_query)
        patcher.start()
        yield TestClient(app)
        patcher.stop()
    else:
        yield TestClient(app)


class TestStreamingEndpoint:
    """Test the streaming /v1/messages endpoint."""

    def test_streaming_request_returns_sse(self, streaming_client: TestClient):
        """Test streaming request returns SSE format."""
        if not USE_CLAUDE_MOCK:
            pytest.skip("Only run with mocked API")

        request = {
            "model": "claude-sonnet-4-5-20250514",
            "max_tokens": 1024,
            "stream": True,
            "messages": [{"role": "user", "content": "Hello!"}],
        }

        # Use stream=True to get raw response
        with streaming_client.stream(
            "POST",
            "/v1/messages",
            json=request,
            headers={"x-api-key": "sk-test"},
        ) as response:
            assert response.status_code == 200
            content_type = response.headers.get("content-type", "")
            assert "text/event-stream" in content_type

    def test_streaming_request_has_events(self, streaming_client: TestClient):
        """Test streaming response contains SSE events."""
        if not USE_CLAUDE_MOCK:
            pytest.skip("Only run with mocked API")

        request = {
            "model": "claude-sonnet-4-5-20250514",
            "max_tokens": 1024,
            "stream": True,
            "messages": [{"role": "user", "content": "Hello!"}],
        }

        with streaming_client.stream(
            "POST",
            "/v1/messages",
            json=request,
            headers={"x-api-key": "sk-test"},
        ) as response:
            assert response.status_code == 200

            # Read all content
            content = response.read().decode("utf-8")

            # Should contain SSE event markers
            # SSE format: "event: <type>\ndata: <json>\n\n"
            assert "event:" in content or "data:" in content

    def test_non_streaming_request_returns_json(self, streaming_client: TestClient):
        """Test non-streaming request returns JSON."""
        if not USE_CLAUDE_MOCK:
            pytest.skip("Only run with mocked API")

        request = {
            "model": "claude-sonnet-4-5-20250514",
            "max_tokens": 1024,
            "stream": False,
            "messages": [{"role": "user", "content": "Hello!"}],
        }

        response = streaming_client.post(
            "/v1/messages",
            json=request,
            headers={"x-api-key": "sk-test"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "message"
        assert data["role"] == "assistant"


class TestStreamingEdgeCases:
    """Test streaming edge cases and error handling."""

    def test_streaming_request_validation_error(self, streaming_client: TestClient):
        """Test streaming request with validation error."""
        request = {
            "model": "claude-sonnet-4-5-20250514",
            "stream": True,
            # Missing "messages" field
        }

        response = streaming_client.post(
            "/v1/messages",
            json=request,
            headers={"x-api-key": "sk-test"},
        )

        assert response.status_code == 422  # Validation error

    def test_streaming_request_missing_model(self, streaming_client: TestClient):
        """Test streaming request with missing model."""
        request = {
            "max_tokens": 1024,
            "stream": True,
            "messages": [{"role": "user", "content": "Hello!"}],
        }

        response = streaming_client.post(
            "/v1/messages",
            json=request,
            headers={"x-api-key": "sk-test"},
        )

        assert response.status_code == 422
