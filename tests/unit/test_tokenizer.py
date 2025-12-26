"""Unit tests for token counting module."""

from src.sdk.tokenizer import (
    TIKTOKEN_AVAILABLE,
    count_content_block_tokens,
    count_message_tokens,
    count_request_tokens,
    count_system_prompt_tokens,
    count_tokens,
    count_tool_definition_tokens,
)


class TestCountTokens:
    """Test the count_tokens function."""

    def test_count_tokens_simple_text(self) -> None:
        """Test counting tokens in simple text."""
        result = count_tokens("Hello, world!")
        assert result > 0
        # With tiktoken, "Hello, world!" is typically 4 tokens

    def test_count_tokens_empty_string(self) -> None:
        """Test counting tokens in empty string."""
        result = count_tokens("")
        assert result == 0

    def test_count_tokens_unicode(self) -> None:
        """Test counting tokens with unicode characters."""
        result = count_tokens("Hello, ")
        assert result > 0

    def test_count_tokens_long_text(self) -> None:
        """Test counting tokens in long text."""
        long_text = "The quick brown fox jumps over the lazy dog. " * 100
        result = count_tokens(long_text)
        assert result > 100  # Should be many tokens

    def test_count_tokens_returns_int(self) -> None:
        """Test that count_tokens always returns an integer."""
        result = count_tokens("Test text")
        assert isinstance(result, int)


class TestCountContentBlockTokens:
    """Test the count_content_block_tokens function."""

    def test_text_block(self) -> None:
        """Test counting tokens in a text content block."""
        block = {"type": "text", "text": "Hello, Claude!"}
        result = count_content_block_tokens(block)
        assert result > 0

    def test_text_block_empty(self) -> None:
        """Test counting tokens in empty text block."""
        block = {"type": "text", "text": ""}
        result = count_content_block_tokens(block)
        assert result == 0

    def test_text_block_missing_text_key(self) -> None:
        """Test text block without text key defaults to empty."""
        block = {"type": "text"}
        result = count_content_block_tokens(block)
        assert result == 0

    def test_image_block(self) -> None:
        """Test image block returns fixed 1000 tokens."""
        block = {"type": "image", "source": {"type": "base64", "data": "..."}}
        result = count_content_block_tokens(block)
        assert result == 1000

    def test_document_block_with_data(self) -> None:
        """Test document block with base64 data."""
        # 120 chars of data should be ~20 tokens (120/6)
        block = {"type": "document", "source": {"type": "base64", "data": "A" * 120}}
        result = count_content_block_tokens(block)
        assert result == 20

    def test_document_block_without_data(self) -> None:
        """Test document block without data defaults to 1500."""
        block = {"type": "document", "source": {}}
        result = count_content_block_tokens(block)
        assert result == 1500

    def test_document_block_empty_data(self) -> None:
        """Test document block with empty data defaults to 1500."""
        block = {"type": "document", "source": {"data": ""}}
        result = count_content_block_tokens(block)
        assert result == 1500

    def test_tool_use_block(self) -> None:
        """Test counting tokens in tool_use block."""
        block = {"type": "tool_use", "name": "get_weather", "input": {"location": "London"}}
        result = count_content_block_tokens(block)
        assert result > 0

    def test_tool_use_block_empty_input(self) -> None:
        """Test tool_use block with empty input."""
        block = {"type": "tool_use", "name": "simple_tool", "input": {}}
        result = count_content_block_tokens(block)
        assert result > 0  # At least the tool name tokens

    def test_tool_result_block_string_content(self) -> None:
        """Test tool_result block with string content."""
        block = {"type": "tool_result", "content": "The weather in London is sunny."}
        result = count_content_block_tokens(block)
        assert result > 0

    def test_tool_result_block_list_content(self) -> None:
        """Test tool_result block with list of blocks."""
        block = {
            "type": "tool_result",
            "content": [
                {"type": "text", "text": "Result part 1"},
                {"type": "text", "text": "Result part 2"},
            ],
        }
        result = count_content_block_tokens(block)
        assert result > 0

    def test_tool_result_block_empty_content(self) -> None:
        """Test tool_result block with empty content."""
        block = {"type": "tool_result", "content": ""}
        result = count_content_block_tokens(block)
        assert result == 0

    def test_unknown_block_type(self) -> None:
        """Test unknown block type returns 0."""
        block = {"type": "unknown_type", "data": "something"}
        result = count_content_block_tokens(block)
        assert result == 0

    def test_missing_type_defaults_to_text(self) -> None:
        """Test missing type defaults to text."""
        block = {"text": "Some text"}
        result = count_content_block_tokens(block)
        assert result > 0


class TestCountMessageTokens:
    """Test the count_message_tokens function."""

    def test_message_with_string_content(self) -> None:
        """Test counting tokens in message with string content."""
        message = {"role": "user", "content": "Hello!"}
        result = count_message_tokens(message)
        # Should include role overhead (4) plus content tokens
        assert result >= 4

    def test_message_with_list_content(self) -> None:
        """Test counting tokens in message with list content."""
        message = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Hello!"},
                {"type": "text", "text": "How can I help?"},
            ],
        }
        result = count_message_tokens(message)
        assert result >= 4  # At least role overhead

    def test_message_with_empty_content(self) -> None:
        """Test message with empty string content."""
        message = {"role": "user", "content": ""}
        result = count_message_tokens(message)
        # Should still have role overhead
        assert result == 4

    def test_message_without_content_key(self) -> None:
        """Test message without content key."""
        message = {"role": "user"}
        result = count_message_tokens(message)
        assert result == 4  # Just role overhead

    def test_role_overhead_included(self) -> None:
        """Test that role overhead of 4 tokens is included."""
        message = {"role": "user", "content": ""}
        result = count_message_tokens(message)
        assert result == 4


class TestCountToolDefinitionTokens:
    """Test the count_tool_definition_tokens function."""

    def test_tool_with_description(self) -> None:
        """Test counting tokens in tool with description."""
        tool = {
            "name": "get_weather",
            "description": "Get the current weather for a location",
            "input_schema": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        }
        result = count_tool_definition_tokens(tool)
        assert result > 0

    def test_tool_without_description(self) -> None:
        """Test counting tokens in tool without description."""
        tool = {"name": "simple_tool", "input_schema": {"type": "object"}}
        result = count_tool_definition_tokens(tool)
        assert result > 0

    def test_tool_with_complex_schema(self) -> None:
        """Test tool with complex input schema."""
        tool = {
            "name": "complex_tool",
            "description": "A tool with many parameters",
            "input_schema": {
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "First param"},
                    "param2": {"type": "integer", "minimum": 0, "maximum": 100},
                    "param3": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["param1", "param2"],
            },
        }
        result = count_tool_definition_tokens(tool)
        # Complex schema should have more tokens
        assert result > 10

    def test_tool_empty_schema(self) -> None:
        """Test tool with empty input schema."""
        tool = {"name": "no_params", "input_schema": {}}
        result = count_tool_definition_tokens(tool)
        assert result > 0  # At least the name tokens


class TestCountSystemPromptTokens:
    """Test the count_system_prompt_tokens function."""

    def test_none_system_prompt(self) -> None:
        """Test None system prompt returns 0."""
        result = count_system_prompt_tokens(None)
        assert result == 0

    def test_string_system_prompt(self) -> None:
        """Test string system prompt."""
        result = count_system_prompt_tokens("You are a helpful assistant.")
        assert result > 0

    def test_empty_string_system_prompt(self) -> None:
        """Test empty string system prompt."""
        result = count_system_prompt_tokens("")
        assert result == 0

    def test_list_system_prompt(self) -> None:
        """Test list of content blocks as system prompt."""
        system = [
            {"type": "text", "text": "You are helpful."},
            {"type": "text", "text": "Be concise."},
        ]
        result = count_system_prompt_tokens(system)
        assert result > 0

    def test_list_with_non_dict_items(self) -> None:
        """Test list with non-dict items are skipped."""
        system = [
            {"type": "text", "text": "Valid block"},
            "not a dict",
            123,
            {"type": "text", "text": "Another valid block"},
        ]
        result = count_system_prompt_tokens(system)  # type: ignore[arg-type]
        # Should only count the dict blocks
        assert result > 0


class TestCountRequestTokens:
    """Test the count_request_tokens function."""

    def test_messages_only(self) -> None:
        """Test counting with messages only."""
        messages = [
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = count_request_tokens(messages)
        # Should include message tokens + 10 overhead
        assert result > 10

    def test_with_system_prompt(self) -> None:
        """Test counting with system prompt."""
        messages = [{"role": "user", "content": "Hello"}]
        system = "You are helpful."
        result = count_request_tokens(messages, system=system)

        # Compare to messages only
        messages_only = count_request_tokens(messages)
        assert result > messages_only

    def test_with_tools(self) -> None:
        """Test counting with tools."""
        messages = [{"role": "user", "content": "Hello"}]
        tools = [
            {
                "name": "get_weather",
                "description": "Get weather",
                "input_schema": {"type": "object"},
            }
        ]
        result = count_request_tokens(messages, tools=tools)

        # Compare to messages only
        messages_only = count_request_tokens(messages)
        assert result > messages_only

    def test_with_all_parameters(self) -> None:
        """Test counting with all parameters."""
        messages = [{"role": "user", "content": "What's the weather?"}]
        system = "You are a weather assistant."
        tools = [
            {
                "name": "get_weather",
                "description": "Get the current weather",
                "input_schema": {"type": "object", "properties": {"location": {"type": "string"}}},
            }
        ]
        result = count_request_tokens(messages, system=system, tools=tools)

        # Should be larger than with just messages
        messages_only = count_request_tokens(messages)
        assert result > messages_only + 10

    def test_empty_messages(self) -> None:
        """Test with empty messages list."""
        result = count_request_tokens([])
        # Should just be the 10 token overhead
        assert result == 10

    def test_includes_formatting_overhead(self) -> None:
        """Test that 10 token formatting overhead is included."""
        # Empty request should have exactly 10 tokens overhead
        result = count_request_tokens([])
        assert result == 10

    def test_none_tools_handled(self) -> None:
        """Test that None tools is handled."""
        messages = [{"role": "user", "content": "Hello"}]
        result = count_request_tokens(messages, tools=None)
        assert result > 0

    def test_empty_tools_list(self) -> None:
        """Test that empty tools list is handled."""
        messages = [{"role": "user", "content": "Hello"}]
        result = count_request_tokens(messages, tools=[])
        assert result > 0


class TestTiktokenAvailability:
    """Test tiktoken availability handling."""

    def test_tiktoken_available_flag_is_boolean(self) -> None:
        """Test TIKTOKEN_AVAILABLE is a boolean."""
        assert isinstance(TIKTOKEN_AVAILABLE, bool)

    def test_tiktoken_produces_consistent_results(self) -> None:
        """Test that tiktoken produces consistent token counts."""
        text = "The quick brown fox"
        result1 = count_tokens(text)
        result2 = count_tokens(text)
        assert result1 == result2

    def test_fallback_estimation(self) -> None:
        """Test fallback estimation when tiktoken encoder is not available."""
        from unittest.mock import patch

        # Mock _encoder to None to test fallback path
        with patch("src.sdk.tokenizer._encoder", None):
            # Fallback is len(text) // 4
            text = "12345678"  # 8 chars
            result = count_tokens(text)
            assert result == 2  # 8 // 4 = 2
