"""Tests for claude8code models and configuration."""

import os
from unittest.mock import patch

from src.core import Settings
from src.models import (
    ContentBlockText,
    Message,
    MessagesRequest,
    MessagesResponse,
    TextBlock,
    Usage,
)


class TestModels:
    """Test Pydantic models match Anthropic's schema."""

    def test_simple_message_request(self) -> None:
        """Test basic message request parsing."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=1024,
            messages=[Message(role="user", content="Hello!")],
        )
        assert request.model == "claude-sonnet-4-5-20250514"
        assert request.max_tokens == 1024
        assert len(request.messages) == 1
        assert request.messages[0].role == "user"
        assert request.messages[0].content == "Hello!"

    def test_message_with_content_blocks(self) -> None:
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
                    ],
                )
            ],
        )
        assert len(request.messages[0].content) == 2

    def test_message_with_system_prompt(self) -> None:
        """Test request with system prompt."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=1024,
            system="You are a helpful assistant",
            messages=[Message(role="user", content="Hi")],
        )
        assert request.system == "You are a helpful assistant"

    def test_streaming_flag(self) -> None:
        """Test stream flag defaults and parsing."""
        # Default is False
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=1024,
            messages=[Message(role="user", content="Hi")],
        )
        assert request.stream is False

        # Explicit True
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=1024,
            stream=True,
            messages=[Message(role="user", content="Hi")],
        )
        assert request.stream is True

    def test_response_structure(self) -> None:
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
        first_block = response.content[0]
        assert first_block.type == "text"
        assert first_block.text == "Hello!"
        assert response.stop_reason == "end_turn"
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 5


class TestConfig:
    """Test configuration loading."""

    def test_default_settings(self) -> None:
        """Test default configuration values."""
        settings = Settings()
        assert settings.host == "0.0.0.0"
        assert settings.port == 8787
        assert settings.debug is False
        assert settings.max_turns == 10
        assert settings.permission_mode == "acceptEdits"

    def test_allowed_tools_empty_returns_none(self) -> None:
        """Test empty allowed_tools returns None (all tools allowed)."""
        settings = Settings()
        # Default has no allowed tools specified, so returns None
        assert settings.get_allowed_tools_list() is None

    def test_setting_sources_default(self) -> None:
        """Test default setting sources."""
        settings = Settings()
        sources = settings.get_setting_sources_list()
        # Default is ["user", "project"]
        assert "user" in sources
        assert "project" in sources

    def test_cors_origins_default(self) -> None:
        """Test default CORS origins."""
        settings = Settings()
        origins = settings.get_cors_origins_list()
        # Default is ["*"]
        assert origins == ["*"]

    def test_cwd_default_from_toml(self) -> None:
        """Test cwd defaults to value from nested config when loaded via get_settings."""
        from settings import get_settings

        # Clear env var to test TOML default
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE8CODE_CWD", None)
            settings = get_settings()
            # Default from settings.toml is "workspace"
            assert settings.cwd == "workspace"
            assert settings.cwd_override is None

    def test_cwd_env_var_override(self) -> None:
        """Test CLAUDE8CODE_CWD env var overrides nested config."""
        from settings import get_settings

        with patch.dict(os.environ, {"CLAUDE8CODE_CWD": "/custom/workspace/path"}):
            settings = get_settings()
            assert settings.cwd_override == "/custom/workspace/path"
            assert settings.cwd == "/custom/workspace/path"

    def test_cwd_env_var_takes_precedence(self) -> None:
        """Test env var takes precedence over nested claude.cwd."""
        from settings import get_settings

        # Even if claude.cwd is set in TOML, env var should override
        with patch.dict(os.environ, {"CLAUDE8CODE_CWD": "/env/override"}):
            settings = get_settings()
            # cwd property should return the override
            assert settings.cwd == "/env/override"
            # Nested config still has TOML value
            assert settings.claude.cwd == "workspace"


class TestCwdPathResolution:
    """Test cwd path resolution to absolute paths."""

    def test_relative_path_resolved_to_absolute(self) -> None:
        """Test relative cwd is resolved to absolute in build_claude_options."""
        from settings import reload_settings
        from src.sdk.bridge import build_claude_options

        request = MessagesRequest(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="test")],
        )

        # With default relative "workspace" cwd (no env override)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE8CODE_CWD", None)
            reload_settings()

            options = build_claude_options(request)
            if options.cwd:
                from pathlib import Path

                cwd_path = Path(options.cwd) if isinstance(options.cwd, str) else options.cwd
                # Should be resolved to absolute
                assert cwd_path.is_absolute()
                # Should end with "workspace" (the relative path resolved)
                assert str(cwd_path).endswith("workspace")

    def test_absolute_path_preserved(self) -> None:
        """Test absolute cwd path is preserved in build_claude_options."""
        from settings import get_settings
        from src.sdk.bridge import build_claude_options

        request = MessagesRequest(
            model="claude-sonnet-4-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="test")],
        )

        # Set absolute path via env var and patch the settings used by bridge
        with patch.dict(os.environ, {"CLAUDE8CODE_CWD": "/absolute/workspace/path"}):
            # Get fresh settings with the env var
            fresh_settings = get_settings()
            # Patch the settings module used by bridge
            with patch("src.sdk.bridge.settings", fresh_settings):
                from pathlib import Path

                options = build_claude_options(request)
                assert options.cwd is not None
                cwd_path = Path(options.cwd) if isinstance(options.cwd, str) else options.cwd
                assert cwd_path.is_absolute()
                assert str(cwd_path) == "/absolute/workspace/path"
