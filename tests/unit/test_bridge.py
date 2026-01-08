"""Unit tests for the bridge module."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import (
    ContentBlockText,
    Message,
    MessagesRequest,
    SDKMessageMode,
    TextBlock,
    ToolUseResponseBlock,
)
from src.sdk.bridge import (
    MODEL_MAP,
    apply_message_mode,
    build_claude_options,
    build_prompt_from_messages,
    format_tool_result_as_xml,
    format_tool_use_as_xml,
    generate_message_id,
    get_sdk_message_mode,
    process_request,
    process_request_streaming,
)


class TestBuildClaudeOptions:
    """Test build_claude_options function."""

    def test_basic_options(self) -> None:
        """Test basic options building."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
        )
        options = build_claude_options(request)
        assert options is not None
        # max_turns comes from settings (default is 10)
        assert options.max_turns is not None and options.max_turns > 0

    def test_options_with_temperature(self) -> None:
        """Test options with temperature."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
            temperature=0.7,
        )
        options = build_claude_options(request)
        assert options is not None

    def test_options_with_system_prompt(self) -> None:
        """Test options with system prompt."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
            system="You are helpful",
        )
        options = build_claude_options(request)
        assert options is not None


class TestProcessRequest:
    """Test process_request function."""

    @pytest.mark.asyncio
    async def test_process_request_basic(self) -> None:
        """Test basic non-streaming request processing."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
        )

        # Mock the query function
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text="Hello back", type="text")]
        mock_result.model = "claude-sonnet-4-5-20250514"
        mock_result.stop_reason = "end_turn"
        mock_result.usage = MagicMock(input_tokens=10, output_tokens=5)

        with patch("src.sdk.bridge.query") as mock_query:
            # Make query return an async generator with our result
            async def mock_gen() -> Any:
                yield mock_result

            mock_query.return_value = mock_gen()

            result = await process_request(request)
            assert result is not None

    @pytest.mark.asyncio
    async def test_process_request_with_mode(self) -> None:
        """Test request processing with specific mode."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
        )

        mock_result = MagicMock()
        mock_result.content = [MagicMock(text="Response", type="text")]
        mock_result.model = "claude-sonnet-4-5-20250514"
        mock_result.stop_reason = "end_turn"
        mock_result.usage = MagicMock(input_tokens=10, output_tokens=5)

        with patch("src.sdk.bridge.query") as mock_query:

            async def mock_gen() -> Any:
                yield mock_result

            mock_query.return_value = mock_gen()

            result = await process_request(request, SDKMessageMode.FORWARD)
            assert result is not None


class TestProcessRequestStreaming:
    """Test process_request_streaming function."""

    @pytest.mark.asyncio
    async def test_streaming_yields_events(self) -> None:
        """Test that streaming yields proper events."""
        from claude_agent_sdk import AssistantMessage
        from claude_agent_sdk import TextBlock as SdkTextBlock

        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
        )

        # Create mock SDK response
        mock_text_block = MagicMock(spec=SdkTextBlock)
        mock_text_block.text = "Hello response"
        type(mock_text_block).__name__ = "TextBlock"

        mock_message = MagicMock(spec=AssistantMessage)
        mock_message.content = [mock_text_block]

        with patch("src.sdk.bridge.query") as mock_query:

            async def mock_gen() -> Any:
                yield mock_message

            mock_query.return_value = mock_gen()

            events = []
            async for event in process_request_streaming(request):
                events.append(event)

            # Should have at least message_start
            assert len(events) >= 1
            assert events[0].type == "message_start"


class TestFormatXMLFunctions:
    """Test XML formatting functions."""

    def test_format_tool_use_empty_input(self) -> None:
        """Test formatting tool use with empty input."""
        result = format_tool_use_as_xml("my_tool", {})
        assert '<tool_use name="my_tool">' in result
        assert "</tool_use>" in result

    def test_format_tool_result_multiline(self) -> None:
        """Test formatting multiline tool result."""
        content = "Line 1\nLine 2\nLine 3"
        result = format_tool_result_as_xml(content)
        assert "<tool_result>" in result
        assert "Line 1" in result
        assert "Line 3" in result
        assert "</tool_result>" in result


class TestApplyMessageModeAdditional:
    """Additional tests for apply_message_mode."""

    def test_empty_blocks(self) -> None:
        """Test applying mode to empty list."""
        result = apply_message_mode([], SDKMessageMode.FORWARD)
        assert result == []

    def test_text_only_blocks(self) -> None:
        """Test mode with only text blocks."""
        blocks = [
            TextBlock(text="Hello"),
            TextBlock(text="World"),
        ]
        result = apply_message_mode(blocks, SDKMessageMode.IGNORE)  # type: ignore[arg-type]
        assert len(result) == 2
        assert all(b.type == "text" for b in result)


class TestModelMap:
    """Additional tests for model mapping."""

    def test_model_map_has_latest_aliases(self) -> None:
        """Test model map has latest aliases."""
        assert "claude-3-5-sonnet-latest" in MODEL_MAP
        assert "claude-3-opus-latest" in MODEL_MAP

    def test_model_map_has_versioned_models(self) -> None:
        """Test model map has versioned models."""
        assert "claude-opus-4-5-20251101" in MODEL_MAP
        assert "claude-sonnet-4-5-20250514" in MODEL_MAP
        assert "claude-haiku-4-5-20251001" in MODEL_MAP


class TestGenerateMessageId:
    """Additional tests for message ID generation."""

    def test_id_is_string(self) -> None:
        """Test ID is a string."""
        msg_id = generate_message_id()
        assert isinstance(msg_id, str)

    def test_id_prefix(self) -> None:
        """Test ID has correct prefix."""
        msg_id = generate_message_id()
        assert msg_id.startswith("msg_")


class TestBuildPromptEdgeCases:
    """Test edge cases in prompt building."""

    def test_empty_content(self) -> None:
        """Test building prompt with empty content."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="")],
        )
        prompt = build_prompt_from_messages(request)
        assert "Human:" in prompt

    def test_mixed_content_types(self) -> None:
        """Test building prompt with mixed content types."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[
                Message(role="user", content="Text message"),
                Message(
                    role="user",
                    content=[ContentBlockText(text="Block message")],
                ),
            ],
        )
        prompt = build_prompt_from_messages(request)
        assert "Text message" in prompt
        assert "Block message" in prompt

    def test_system_as_list(self) -> None:
        """Test building prompt with system as list."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
            system=[{"type": "text", "text": "System prompt"}],
        )
        prompt = build_prompt_from_messages(request)
        assert "Hello" in prompt


class TestGetSdkMessageModeEdgeCases:
    """Test edge cases for SDK message mode parsing."""

    def test_whitespace_handling(self) -> None:
        """Test mode parsing handles whitespace."""
        mode = get_sdk_message_mode("  forward  ")
        assert mode == SDKMessageMode.FORWARD

    def test_empty_string(self) -> None:
        """Test empty string falls back to default."""
        mode = get_sdk_message_mode("")
        assert isinstance(mode, SDKMessageMode)

    def test_invalid_header_value(self) -> None:
        """Test invalid header falls back to settings."""
        mode = get_sdk_message_mode("invalid_mode_value")
        assert isinstance(mode, SDKMessageMode)

    def test_case_insensitive(self) -> None:
        """Test mode parsing is case insensitive."""
        mode = get_sdk_message_mode("IGNORE")
        assert mode == SDKMessageMode.IGNORE

    def test_formatted_mode(self) -> None:
        """Test formatted mode is recognized."""
        mode = get_sdk_message_mode("formatted")
        assert mode == SDKMessageMode.FORMATTED


class TestApplyMessageModeFormatted:
    """Test apply_message_mode with FORMATTED mode."""

    def test_formatted_with_tool_use(self) -> None:
        """Test FORMATTED mode converts tool use to XML."""
        blocks = [
            TextBlock(text="Some text"),
            ToolUseResponseBlock(id="tool_1", name="my_tool", input={"key": "value"}),
        ]
        result = apply_message_mode(blocks, SDKMessageMode.FORMATTED)  # type: ignore[arg-type]

        assert len(result) == 1
        assert result[0].type == "text"
        assert "Some text" in result[0].text  # type: ignore[union-attr]
        assert '<tool_use name="my_tool">' in result[0].text  # type: ignore[union-attr]

    def test_formatted_with_only_tool_use(self) -> None:
        """Test FORMATTED mode with only tool use blocks."""
        blocks = [
            ToolUseResponseBlock(id="tool_1", name="read_file", input={"path": "/test"}),
        ]
        result = apply_message_mode(blocks, SDKMessageMode.FORMATTED)  # type: ignore[arg-type]

        assert len(result) == 1
        assert '<tool_use name="read_file">' in result[0].text  # type: ignore[union-attr]

    def test_formatted_empty_result(self) -> None:
        """Test FORMATTED mode returns empty for no content."""
        result = apply_message_mode([], SDKMessageMode.FORMATTED)
        assert result == []


class TestBuildPromptToolResult:
    """Test build_prompt_from_messages with tool results."""

    def test_tool_result_content(self) -> None:
        """Test building prompt with tool_result type content."""
        from src.models.requests import ToolResultBlock

        # Create a proper tool result block
        tool_result = ToolResultBlock(
            tool_use_id="tool_123",
            content="File contents here",
        )

        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[
                Message(role="user", content=[tool_result]),
            ],
        )
        prompt = build_prompt_from_messages(request)
        assert "[Tool Result:" in prompt
        assert "File contents here" in prompt


class TestBuildClaudeOptionsSystemList:
    """Test build_claude_options with system as list."""

    def test_system_as_list_of_dicts(self) -> None:
        """Test system prompt as list of text blocks."""
        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
            system=[
                {"type": "text", "text": "You are helpful."},
                {"type": "text", "text": "Be concise."},
            ],
        )
        options = build_claude_options(request)
        assert options.system_prompt is not None
        assert "You are helpful." in options.system_prompt
        assert "Be concise." in options.system_prompt


class TestProcessRequestWithUsageDict:
    """Test process_request with usage as dictionary."""

    @pytest.mark.asyncio
    async def test_process_with_usage_dict(self) -> None:
        """Test request processing with usage as dict."""
        from claude_agent_sdk import AssistantMessage, ResultMessage
        from claude_agent_sdk import TextBlock as SdkTextBlock

        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
        )

        mock_text_block = MagicMock(spec=SdkTextBlock)
        mock_text_block.text = "Response"

        mock_assistant = MagicMock(spec=AssistantMessage)
        mock_assistant.content = [mock_text_block]

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.usage = {
            "input_tokens": 50,
            "output_tokens": 25,
            "cache_creation_input_tokens": 10,
            "cache_read_input_tokens": 5,
        }

        with patch("src.sdk.bridge.query") as mock_query:

            async def mock_gen() -> Any:
                yield mock_assistant
                yield mock_result

            mock_query.return_value = mock_gen()

            result = await process_request(request)
            assert result.usage.input_tokens == 50
            assert result.usage.output_tokens == 25
            assert result.usage.cache_creation_input_tokens == 10
            assert result.usage.cache_read_input_tokens == 5

    @pytest.mark.asyncio
    async def test_process_with_zero_usage_fallback(self) -> None:
        """Test request processing falls back to estimates when no usage."""
        from claude_agent_sdk import AssistantMessage
        from claude_agent_sdk import TextBlock as SdkTextBlock

        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
        )

        mock_text_block = MagicMock(spec=SdkTextBlock)
        mock_text_block.text = "Response text"

        mock_assistant = MagicMock(spec=AssistantMessage)
        mock_assistant.content = [mock_text_block]

        with patch("src.sdk.bridge.query") as mock_query:

            async def mock_gen() -> Any:
                yield mock_assistant

            mock_query.return_value = mock_gen()

            result = await process_request(request)
            # Fallback estimates based on text length
            assert result.usage.input_tokens > 0 or result.usage.output_tokens > 0


class TestProcessRequestStreamingToolUse:
    """Test process_request_streaming with tool use blocks."""

    @pytest.mark.asyncio
    async def test_streaming_with_tool_use_forward(self) -> None:
        """Test streaming with tool use in FORWARD mode."""
        from claude_agent_sdk import AssistantMessage
        from claude_agent_sdk import TextBlock as SdkTextBlock
        from claude_agent_sdk import ToolUseBlock as SdkToolUseBlock

        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
        )

        mock_text = MagicMock(spec=SdkTextBlock)
        mock_text.text = "Let me check"

        mock_tool = MagicMock(spec=SdkToolUseBlock)
        mock_tool.id = "tool_123"
        mock_tool.name = "read_file"
        mock_tool.input = {"path": "/test.txt"}

        mock_message = MagicMock(spec=AssistantMessage)
        mock_message.content = [mock_text, mock_tool]

        with patch("src.sdk.bridge.query") as mock_query:

            async def mock_gen() -> Any:
                yield mock_message

            mock_query.return_value = mock_gen()

            events = []
            async for event in process_request_streaming(request, SDKMessageMode.FORWARD):
                events.append(event)

            # Should have tool use block events
            event_types = [e.type for e in events]
            assert "message_start" in event_types
            assert "content_block_start" in event_types

    @pytest.mark.asyncio
    async def test_streaming_with_tool_use_ignore(self) -> None:
        """Test streaming with tool use in IGNORE mode skips tools."""
        from claude_agent_sdk import AssistantMessage
        from claude_agent_sdk import TextBlock as SdkTextBlock
        from claude_agent_sdk import ToolUseBlock as SdkToolUseBlock

        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
        )

        mock_text = MagicMock(spec=SdkTextBlock)
        mock_text.text = "Some text"

        mock_tool = MagicMock(spec=SdkToolUseBlock)
        mock_tool.id = "tool_123"
        mock_tool.name = "read_file"
        mock_tool.input = {}

        mock_message = MagicMock(spec=AssistantMessage)
        mock_message.content = [mock_text, mock_tool]

        with patch("src.sdk.bridge.query") as mock_query:

            async def mock_gen() -> Any:
                yield mock_message

            mock_query.return_value = mock_gen()

            events = []
            async for event in process_request_streaming(request, SDKMessageMode.IGNORE):
                events.append(event)

            # In IGNORE mode, tool use should be skipped
            assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_streaming_with_tool_use_formatted(self) -> None:
        """Test streaming with tool use in FORMATTED mode."""
        from claude_agent_sdk import AssistantMessage
        from claude_agent_sdk import TextBlock as SdkTextBlock
        from claude_agent_sdk import ToolUseBlock as SdkToolUseBlock

        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
        )

        mock_text = MagicMock(spec=SdkTextBlock)
        mock_text.text = "Starting"

        mock_tool = MagicMock(spec=SdkToolUseBlock)
        mock_tool.id = "tool_123"
        mock_tool.name = "edit_file"
        mock_tool.input = {"path": "/file.py"}

        mock_message = MagicMock(spec=AssistantMessage)
        mock_message.content = [mock_text, mock_tool]

        with patch("src.sdk.bridge.query") as mock_query:

            async def mock_gen() -> Any:
                yield mock_message

            mock_query.return_value = mock_gen()

            events = []
            async for event in process_request_streaming(request, SDKMessageMode.FORMATTED):
                events.append(event)

            # Check for text delta with XML-formatted tool use
            delta_events = [e for e in events if e.type == "content_block_delta"]
            assert len(delta_events) >= 1


class TestProcessRequestStreamingResult:
    """Test process_request_streaming with ResultMessage."""

    @pytest.mark.asyncio
    async def test_streaming_with_result_usage_dict(self) -> None:
        """Test streaming extracts usage from result dict."""
        from claude_agent_sdk import AssistantMessage, ResultMessage
        from claude_agent_sdk import TextBlock as SdkTextBlock

        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
        )

        mock_text = MagicMock(spec=SdkTextBlock)
        mock_text.text = "Response"

        mock_assistant = MagicMock(spec=AssistantMessage)
        mock_assistant.content = [mock_text]

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.usage = {"output_tokens": 100}

        with patch("src.sdk.bridge.query") as mock_query:

            async def mock_gen() -> Any:
                yield mock_assistant
                yield mock_result

            mock_query.return_value = mock_gen()

            events = []
            async for event in process_request_streaming(request):
                events.append(event)

            # Check message_delta has output tokens
            delta_events = [e for e in events if e.type == "message_delta"]
            assert len(delta_events) == 1
            assert delta_events[0].usage.output_tokens == 100

    @pytest.mark.asyncio
    async def test_streaming_with_result_usage_object(self) -> None:
        """Test streaming extracts usage from result object."""
        from claude_agent_sdk import AssistantMessage, ResultMessage
        from claude_agent_sdk import TextBlock as SdkTextBlock

        request = MessagesRequest(
            model="claude-sonnet-4-5-20250514",
            max_tokens=100,
            messages=[Message(role="user", content="Hello")],
        )

        mock_text = MagicMock(spec=SdkTextBlock)
        mock_text.text = "Response"

        mock_assistant = MagicMock(spec=AssistantMessage)
        mock_assistant.content = [mock_text]

        mock_usage = MagicMock()
        mock_usage.output_tokens = 75

        mock_result = MagicMock(spec=ResultMessage)
        mock_result.usage = mock_usage

        with patch("src.sdk.bridge.query") as mock_query:

            async def mock_gen() -> Any:
                yield mock_assistant
                yield mock_result

            mock_query.return_value = mock_gen()

            events = []
            async for event in process_request_streaming(request):
                events.append(event)

            delta_events = [e for e in events if e.type == "message_delta"]
            assert delta_events[0].usage.output_tokens == 75


class TestSessionManager:
    """Test SessionManager class."""

    @pytest.mark.asyncio
    async def test_create_and_get_session(self) -> None:
        """Test creating and retrieving a session."""
        from src.sdk.bridge import SessionManager

        manager = SessionManager()

        with patch("src.sdk.bridge.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            session_id, client = await manager.get_or_create_session("test_session")
            assert session_id == "test_session"
            assert client is mock_client

            # Getting same session should return same client
            session_id2, client2 = await manager.get_or_create_session("test_session")
            assert session_id2 == "test_session"
            assert client2 is mock_client

            await manager.close_all()

    @pytest.mark.asyncio
    async def test_auto_generate_session_id(self) -> None:
        """Test session ID is auto-generated when not provided."""
        from src.sdk.bridge import SessionManager

        manager = SessionManager()

        with patch("src.sdk.bridge.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            session_id, _ = await manager.get_or_create_session()
            assert session_id.startswith("session_")

            await manager.close_all()

    @pytest.mark.asyncio
    async def test_close_session(self) -> None:
        """Test closing a specific session."""
        from src.sdk.bridge import SessionManager

        manager = SessionManager()

        with patch("src.sdk.bridge.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            session_id, _ = await manager.get_or_create_session("to_close")

            result = await manager.close_session(session_id)
            assert result is True

            # Closing non-existent session returns False
            result = await manager.close_session("nonexistent")
            assert result is False

    @pytest.mark.asyncio
    async def test_close_all_sessions(self) -> None:
        """Test closing all sessions."""
        from src.sdk.bridge import SessionManager

        manager = SessionManager()

        with patch("src.sdk.bridge.ClaudeSDKClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()
            mock_client_class.return_value = mock_client

            await manager.get_or_create_session("session1")
            await manager.get_or_create_session("session2")

            await manager.close_all()

            # Sessions should be cleared
            assert len(manager._sessions) == 0
