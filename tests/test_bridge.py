"""Tests for claude8code bridge module."""

import pytest

from src.sdk.bridge import (
    build_prompt_from_messages,
    generate_message_id,
    MODEL_MAP,
)
from src.models import MessagesRequest, Message, ContentBlockText


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
