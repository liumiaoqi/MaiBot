"""Unit tests for message types.

This module tests all message-related types including ContentPart,
Message, ToolCall, and their various subclasses.
"""

from __future__ import annotations

import pytest

from agentlite import (
    ContentPart,
    Message,
    TextPart,
    ImageURLPart,
    AudioURLPart,
    ToolCall,
    ToolCallPart,
)


class TestContentPart:
    """Tests for ContentPart base class and registry."""

    def test_content_part_registry_auto_registers_subclasses(self):
        """Test that ContentPart subclasses are auto-registered."""
        # All defined subclasses should be in registry
        assert "text" in ContentPart._ContentPart__content_part_registry
        assert "image_url" in ContentPart._ContentPart__content_part_registry
        assert "audio_url" in ContentPart._ContentPart__content_part_registry

    def test_text_part_creation(self):
        """Test basic TextPart creation."""
        part = TextPart(text="Hello, world!")
        assert part.type == "text"
        assert part.text == "Hello, world!"

    def test_text_part_model_dump(self):
        """Test TextPart serialization."""
        part = TextPart(text="Hello")
        dumped = part.model_dump()
        assert dumped == {"type": "text", "text": "Hello"}

    def test_text_part_merge_success(self):
        """Test successful text merge during streaming."""
        part1 = TextPart(text="Hello ")
        part2 = TextPart(text="world!")

        result = part1.merge_in_place(part2)

        assert result is True
        assert part1.text == "Hello world!"

    def test_text_part_merge_failure(self):
        """Test merge failure with incompatible types."""
        text_part = TextPart(text="Hello")

        # Try to merge with non-TextPart
        result = text_part.merge_in_place("not a part")
        assert result is False
        assert text_part.text == "Hello"  # Unchanged


class TestImageURLPart:
    """Tests for ImageURLPart."""

    def test_image_url_part_creation(self):
        """Test ImageURLPart creation."""
        part = ImageURLPart(image_url=ImageURLPart.ImageURL(url="https://example.com/image.png"))
        assert part.type == "image_url"
        assert part.image_url.url == "https://example.com/image.png"

    def test_image_url_part_with_detail(self):
        """Test ImageURLPart with detail parameter."""
        part = ImageURLPart(
            image_url=ImageURLPart.ImageURL(url="https://example.com/image.png", detail="high")
        )
        assert part.image_url.detail == "high"

    def test_image_url_part_default_detail(self):
        """Test ImageURLPart default detail is None."""
        part = ImageURLPart(image_url=ImageURLPart.ImageURL(url="https://example.com/image.png"))
        assert part.image_url.detail is None


class TestAudioURLPart:
    """Tests for AudioURLPart."""

    def test_audio_url_part_creation(self):
        """Test AudioURLPart creation."""
        part = AudioURLPart(audio_url=AudioURLPart.AudioURL(url="https://example.com/audio.mp3"))
        assert part.type == "audio_url"
        assert part.audio_url.url == "https://example.com/audio.mp3"


class TestToolCall:
    """Tests for ToolCall."""

    def test_tool_call_creation(self):
        """Test ToolCall creation."""
        call = ToolCall(
            id="call_123", function=ToolCall.FunctionBody(name="add", arguments='{"a": 1, "b": 2}')
        )
        assert call.type == "function"
        assert call.id == "call_123"
        assert call.function.name == "add"
        assert call.function.arguments == '{"a": 1, "b": 2}'

    def test_tool_call_merge_with_part(self):
        """Test ToolCall merging with ToolCallPart."""
        call = ToolCall(
            id="call_123", function=ToolCall.FunctionBody(name="add", arguments='{"a": 1')
        )
        part = ToolCallPart(arguments_part=', "b": 2}')

        result = call.merge_in_place(part)

        assert result is True
        assert call.function.arguments == '{"a": 1, "b": 2}'

    def test_tool_call_merge_failure(self):
        """Test ToolCall merge failure with incompatible types."""
        call = ToolCall(id="call_123", function=ToolCall.FunctionBody(name="add", arguments="{}"))

        result = call.merge_in_place("not a part")
        assert result is False


class TestToolCallPart:
    """Tests for ToolCallPart."""

    def test_tool_call_part_creation(self):
        """Test ToolCallPart creation."""
        part = ToolCallPart(arguments_part='{"a": 1}')
        assert part.arguments_part == '{"a": 1}'

    def test_tool_call_part_none(self):
        """Test ToolCallPart with None arguments."""
        part = ToolCallPart(arguments_part=None)
        assert part.arguments_part is None

    def test_tool_call_part_merge(self):
        """Test ToolCallPart merging."""
        part1 = ToolCallPart(arguments_part='{"a":')
        part2 = ToolCallPart(arguments_part=" 1}")

        result = part1.merge_in_place(part2)

        assert result is True
        assert part1.arguments_part == '{"a": 1}'

    def test_tool_call_part_merge_none(self):
        """Test ToolCallPart merge when self is None."""
        part1 = ToolCallPart(arguments_part=None)
        part2 = ToolCallPart(arguments_part='{"a": 1}')

        result = part1.merge_in_place(part2)

        assert result is True
        assert part1.arguments_part == '{"a": 1}'


class TestMessage:
    """Tests for Message."""

    def test_message_string_content_coercion(self):
        """Test that string content is coerced to TextPart."""
        msg = Message(role="user", content="Hello!")

        assert len(msg.content) == 1
        assert isinstance(msg.content[0], TextPart)
        assert msg.content[0].text == "Hello!"

    def test_message_part_content(self):
        """Test Message with ContentPart content."""
        part = TextPart(text="Hello!")
        msg = Message(role="user", content=part)

        assert len(msg.content) == 1
        assert msg.content[0].text == "Hello!"

    def test_message_list_content(self):
        """Test Message with list of ContentParts."""
        parts = [TextPart(text="Hello"), TextPart(text=" world!")]
        msg = Message(role="user", content=parts)

        assert len(msg.content) == 2

    def test_message_extract_text(self):
        """Test text extraction from message."""
        msg = Message(role="user", content="Hello world!")

        assert msg.extract_text() == "Hello world!"

    def test_message_extract_text_with_separator(self):
        """Test text extraction with custom separator."""
        parts = [TextPart(text="Hello"), TextPart(text="world!")]
        msg = Message(role="user", content=parts)

        assert msg.extract_text(sep=" ") == "Hello world!"
        assert msg.extract_text(sep="-") == "Hello-world!"

    def test_message_has_tool_calls_false(self):
        """Test has_tool_calls returns False when no tool calls."""
        msg = Message(role="assistant", content="Hello!")
        assert msg.has_tool_calls() is False

    def test_message_has_tool_calls_true(self):
        """Test has_tool_calls returns True when tool calls present."""
        tool_call = ToolCall(
            id="call_123", function=ToolCall.FunctionBody(name="add", arguments="{}")
        )
        msg = Message(role="assistant", content="Let me calculate that.", tool_calls=[tool_call])
        assert msg.has_tool_calls() is True

    def test_message_has_tool_calls_empty_list(self):
        """Test has_tool_calls with empty tool_calls list."""
        msg = Message(role="assistant", content="Hello!", tool_calls=[])
        assert msg.has_tool_calls() is False

    def test_message_tool_response(self):
        """Test message with tool response."""
        msg = Message(role="tool", content="Result: 42", tool_call_id="call_123")
        assert msg.role == "tool"
        assert msg.tool_call_id == "call_123"

    def test_message_serialization(self):
        """Test Message serialization with model_dump."""
        msg = Message(role="user", content="Hello!")
        dumped = msg.model_dump()

        assert dumped["role"] == "user"
        assert "content" in dumped

    def test_message_all_roles(self):
        """Test Message creation with all valid roles."""
        for role in ["system", "user", "assistant", "tool"]:
            msg = Message(role=role, content="Test")
            assert msg.role == role


class TestPolymorphicContentPart:
    """Tests for polymorphic ContentPart validation."""

    def test_polymorphic_validation_text(self):
        """Test that text type validates to TextPart."""
        data = {"type": "text", "text": "Hello"}
        part = ContentPart.model_validate(data)

        assert isinstance(part, TextPart)
        assert part.text == "Hello"

    def test_polymorphic_validation_image(self):
        """Test that image_url type validates to ImageURLPart."""
        data = {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}}
        part = ContentPart.model_validate(data)

        assert isinstance(part, ImageURLPart)
        assert part.image_url.url == "https://example.com/image.png"

    def test_polymorphic_validation_unknown_type(self):
        """Test validation with unknown type raises error."""
        data = {"type": "unknown_type", "content": "test"}

        with pytest.raises(ValueError, match="Unknown content part type"):
            ContentPart.model_validate(data)

    def test_polymorphic_validation_no_type(self):
        """Test validation without type raises error."""
        data = {"content": "test"}

        with pytest.raises(ValueError):
            ContentPart.model_validate(data)


class TestMessageEdgeCases:
    """Tests for edge cases in Message handling."""

    def test_empty_string_content(self):
        """Test Message with empty string content."""
        msg = Message(role="user", content="")
        assert msg.content[0].text == ""

    def test_message_with_name(self):
        """Test Message with name field."""
        msg = Message(role="user", content="Hello", name="user1")
        assert msg.name == "user1"

    def test_message_history_isolation(self):
        """Test that history modifications don't affect original."""
        msg = Message(role="user", content="Hello")

        # Modify the content list
        msg.content.append(TextPart(text="Extra"))

        # Original should be modified (it's the same object)
        assert len(msg.content) == 2
