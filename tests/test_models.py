"""Tests for claude8code models and configuration."""

import pytest
from claude8code.models import (
    MessagesRequest,
    MessagesResponse,
    Message,
    ContentBlockText,
    TextBlock,
    Usage,
)
from claude8code.config import Settings


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
    
    def test_allowed_tools_parsing(self):
        """Test allowed_tools comma-separated parsing."""
        settings = Settings(allowed_tools="Read,Write,Bash")
        tools = settings.get_allowed_tools_list()
        assert tools == ["Read", "Write", "Bash"]
        
        # Empty returns None
        settings = Settings(allowed_tools="")
        assert settings.get_allowed_tools_list() is None
    
    def test_setting_sources_parsing(self):
        """Test setting_sources parsing."""
        settings = Settings(setting_sources="user,project,local")
        sources = settings.get_setting_sources_list()
        assert sources == ["user", "project", "local"]
    
    def test_cors_origins_parsing(self):
        """Test CORS origins parsing."""
        # Wildcard
        settings = Settings(cors_origins="*")
        assert settings.get_cors_origins_list() == ["*"]
        
        # Multiple origins
        settings = Settings(cors_origins="http://localhost:5678,http://n8n.local")
        origins = settings.get_cors_origins_list()
        assert origins == ["http://localhost:5678", "http://n8n.local"]
