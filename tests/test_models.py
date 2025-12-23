"""Tests for claude8code models and configuration."""

import pytest
from src.models import (
    MessagesRequest,
    MessagesResponse,
    Message,
    ContentBlockText,
    TextBlock,
    Usage,
)
from src.core import Settings


class TestModels:
    """Test Pydantic models match Anthropic's schema."""
    
    def test_simple_message_request(self):
        """Test basic message request parsing."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=1024,
            messages=[
                Message(role="user", content="Hello!")
            ]
        )
        assert request.model == "claude-sonnet-4-5-20250514"
        assert request.max_tokens == 1024
        assert len(request.messages) == 1
        assert request.messages[0].role == "user"
        assert request.messages[0].content == "Hello!"
    
    def test_message_with_content_blocks(self):
        """Test message with content block array."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=1024,
            messages=[
                Message(
                    role="user",
                    content=[
                        ContentBlockText(text="Part 1"),
                        ContentBlockText(text="Part 2"),
                    ]
                )
            ]
        )
        assert len(request.messages[0].content) == 2
    
    def test_message_with_system_prompt(self):
        """Test request with system prompt."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=1024,
            system="You are a helpful assistant",
            messages=[
                Message(role="user", content="Hi")
            ]
        )
        assert request.system == "You are a helpful assistant"
    
    def test_streaming_flag(self):
        """Test stream flag defaults and parsing."""
        # Default is False
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=1024,
            messages=[Message(role="user", content="Hi")]
        )
        assert request.stream is False
        
        # Explicit True
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=1024,
            stream=True,
            messages=[Message(role="user", content="Hi")]
        )
        assert request.stream is True
    
    def test_response_structure(self):
        """Test response model structure."""
        response = MessagesResponse(
            id="msg_test123",
            content=[TextBlock(text="Hello!")],
            model="claude-sonnet-4-5-20250514",
            stop_reason="end_turn",
            usage=Usage(input_tokens=10, output_tokens=5),
        )
        assert response.id == "msg_test123"
        assert response.type == "message"
        assert response.role == "assistant"
        assert len(response.content) == 1
        assert response.content[0].text == "Hello!"
        assert response.stop_reason == "end_turn"
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 5


class TestConfig:
    """Test configuration loading."""

    def test_default_settings(self):
        """Test default configuration values."""
        settings = Settings()
        assert settings.host == "0.0.0.0"
        assert settings.port == 8787
        assert settings.debug is False
        assert settings.max_turns == 10
        assert settings.permission_mode == "acceptEdits"

    def test_allowed_tools_empty_returns_none(self):
        """Test empty allowed_tools returns None (all tools allowed)."""
        settings = Settings()
        # Default has no allowed tools specified, so returns None
        assert settings.get_allowed_tools_list() is None

    def test_setting_sources_default(self):
        """Test default setting sources."""
        settings = Settings()
        sources = settings.get_setting_sources_list()
        # Default is ["user", "project"]
        assert "user" in sources
        assert "project" in sources

    def test_cors_origins_default(self):
        """Test default CORS origins."""
        settings = Settings()
        origins = settings.get_cors_origins_list()
        # Default is ["*"]
        assert origins == ["*"]
