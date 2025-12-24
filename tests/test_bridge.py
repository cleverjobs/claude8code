"""Tests for claude8code bridge module."""

import pytest

from src.sdk.bridge import (
    build_prompt_from_messages,
    generate_message_id,
    get_sdk_message_mode,
    format_tool_use_as_xml,
    format_tool_result_as_xml,
    apply_message_mode,
    MODEL_MAP,
)
from src.models import (
    MessagesRequest,
    Message,
    ContentBlockText,
    SDKMessageMode,
    TextBlock,
    ToolUseResponseBlock,
)


class TestMessageIdGeneration:
    """Test message ID generation."""

    def test_message_id_format(self):
        """Test message ID has correct format."""
        msg_id = generate_message_id()
        assert msg_id.startswith("msg_")
        assert len(msg_id) == 28  # "msg_" + 24 hex chars

    def test_message_ids_unique(self):
        """Test message IDs are unique."""
        ids = [generate_message_id() for _ in range(100)]
        assert len(set(ids)) == 100


class TestPromptBuilding:
    """Test prompt building from messages."""

    def test_simple_user_message(self):
        """Test building prompt from simple user message."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=1024,
            messages=[Message(role="user", content="Hello!")]
        )
        prompt = build_prompt_from_messages(request)
        assert "Human: Hello!" in prompt

    def test_assistant_message(self):
        """Test building prompt with assistant message."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=1024,
            messages=[
                Message(role="user", content="Hi"),
                Message(role="assistant", content="Hello!"),
            ]
        )
        prompt = build_prompt_from_messages(request)
        assert "Human: Hi" in prompt
        assert "Assistant: Hello!" in prompt

    def test_content_blocks(self):
        """Test building prompt from content blocks."""
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
        prompt = build_prompt_from_messages(request)
        assert "Part 1" in prompt
        assert "Part 2" in prompt

    def test_multiple_messages(self):
        """Test building prompt from conversation."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=1024,
            messages=[
                Message(role="user", content="What is 2+2?"),
                Message(role="assistant", content="4"),
                Message(role="user", content="What is 3+3?"),
            ]
        )
        prompt = build_prompt_from_messages(request)

        # Check order is preserved
        parts = prompt.split("\n\n")
        assert len(parts) == 3
        assert "Human: What is 2+2?" in parts[0]
        assert "Assistant: 4" in parts[1]
        assert "Human: What is 3+3?" in parts[2]


class TestModelMapping:
    """Test model ID mapping."""

    def test_direct_model_ids(self):
        """Test that direct model IDs map to themselves."""
        assert MODEL_MAP["claude-sonnet-4-5-20250514"] == "claude-sonnet-4-5-20250514"
        assert MODEL_MAP["claude-opus-4-5-20251101"] == "claude-opus-4-5-20251101"

    def test_alias_mapping(self):
        """Test that aliases map to correct models."""
        assert MODEL_MAP["claude-3-5-sonnet-latest"] == "claude-sonnet-4-5-20250514"
        assert MODEL_MAP["claude-3-opus-latest"] == "claude-opus-4-5-20251101"

    def test_all_models_have_valid_targets(self):
        """Test all mappings point to valid model IDs."""
        valid_models = {
            "claude-opus-4-5-20251101",
            "claude-sonnet-4-5-20250514",
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
        }
        for source, target in MODEL_MAP.items():
            assert target in valid_models, f"{source} maps to unknown model {target}"


class TestSDKMessageMode:
    """Test SDK message mode parsing."""

    def test_get_mode_from_header_forward(self):
        """Test parsing 'forward' mode from header."""
        mode = get_sdk_message_mode("forward")
        assert mode == SDKMessageMode.FORWARD

    def test_get_mode_from_header_formatted(self):
        """Test parsing 'formatted' mode from header."""
        mode = get_sdk_message_mode("formatted")
        assert mode == SDKMessageMode.FORMATTED

    def test_get_mode_from_header_ignore(self):
        """Test parsing 'ignore' mode from header."""
        mode = get_sdk_message_mode("ignore")
        assert mode == SDKMessageMode.IGNORE

    def test_get_mode_case_insensitive(self):
        """Test mode parsing is case-insensitive."""
        assert get_sdk_message_mode("FORWARD") == SDKMessageMode.FORWARD
        assert get_sdk_message_mode("Formatted") == SDKMessageMode.FORMATTED
        assert get_sdk_message_mode("IGNORE") == SDKMessageMode.IGNORE

    def test_get_mode_invalid_falls_back(self):
        """Test invalid header value falls back to default."""
        mode = get_sdk_message_mode("invalid_mode")
        assert mode == SDKMessageMode.FORWARD  # Default

    def test_get_mode_none_uses_default(self):
        """Test None header uses settings default."""
        mode = get_sdk_message_mode(None)
        # Should return the settings default (FORWARD by default)
        assert isinstance(mode, SDKMessageMode)


class TestXMLFormatting:
    """Test XML formatting for tool use/results."""

    def test_format_tool_use_as_xml(self):
        """Test tool use XML formatting."""
        result = format_tool_use_as_xml("get_weather", {"location": "London"})
        assert '<tool_use name="get_weather">' in result
        assert '"location": "London"' in result
        assert "</tool_use>" in result

    def test_format_tool_use_complex_input(self):
        """Test tool use with complex nested input."""
        result = format_tool_use_as_xml(
            "search",
            {"query": "test", "options": {"limit": 10, "sort": "date"}}
        )
        assert '<tool_use name="search">' in result
        assert '"options"' in result
        assert "</tool_use>" in result

    def test_format_tool_result_as_xml(self):
        """Test tool result XML formatting."""
        result = format_tool_result_as_xml("The weather is sunny")
        assert "<tool_result>" in result
        assert "The weather is sunny" in result
        assert "</tool_result>" in result


class TestApplyMessageMode:
    """Test message mode application to content blocks."""

    def test_forward_mode_preserves_blocks(self):
        """Test forward mode returns blocks unchanged."""
        blocks = [
            TextBlock(text="Hello"),
            ToolUseResponseBlock(id="tool_1", name="test", input={}),
        ]
        result = apply_message_mode(blocks, SDKMessageMode.FORWARD)
        assert len(result) == 2
        assert result[0].type == "text"
        assert result[1].type == "tool_use"

    def test_ignore_mode_filters_tool_blocks(self):
        """Test ignore mode removes tool blocks."""
        blocks = [
            TextBlock(text="Hello"),
            ToolUseResponseBlock(id="tool_1", name="test", input={}),
            TextBlock(text="World"),
        ]
        result = apply_message_mode(blocks, SDKMessageMode.IGNORE)
        # Should only have text blocks
        assert all(b.type == "text" for b in result)

    def test_formatted_mode_converts_tools(self):
        """Test formatted mode converts tool blocks to XML text."""
        blocks = [
            TextBlock(text="Hello"),
            ToolUseResponseBlock(id="tool_1", name="get_weather", input={"city": "NYC"}),
        ]
        result = apply_message_mode(blocks, SDKMessageMode.FORMATTED)
        # All should be text blocks after formatting
        assert all(b.type == "text" for b in result)
        # Tool should be converted to XML text
        texts = [b.text for b in result]
        assert any("tool_use" in t for t in texts)
