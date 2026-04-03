"""Unit tests for provider protocol and exceptions.

This module tests the ChatProvider protocol, StreamedMessage protocol,
and all exception types.
"""

from __future__ import annotations

import pytest

from agentlite.provider import (
    TokenUsage,
    ChatProviderError,
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    APIEmptyResponseError,
    ChatProvider,
    StreamedMessage,
)


class TestTokenUsage:
    """Tests for TokenUsage."""

    def test_token_usage_creation(self):
        """Test TokenUsage creation."""
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.cached_tokens == 0  # Default

    def test_token_usage_with_cached(self):
        """Test TokenUsage with cached tokens."""
        usage = TokenUsage(input_tokens=100, output_tokens=50, cached_tokens=20)
        assert usage.cached_tokens == 20

    def test_token_usage_total(self):
        """Test total token calculation."""
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.total == 150

    def test_token_usage_total_with_cached(self):
        """Test total with cached tokens (not included in total)."""
        usage = TokenUsage(input_tokens=100, output_tokens=50, cached_tokens=20)
        # Total is input + output, cached is tracked separately
        assert usage.total == 150


class TestChatProviderError:
    """Tests for ChatProviderError hierarchy."""

    def test_base_error_creation(self):
        """Test base ChatProviderError creation."""
        error = ChatProviderError("Something went wrong")
        assert error.message == "Something went wrong"
        assert str(error) == "Something went wrong"

    def test_api_connection_error(self):
        """Test APIConnectionError creation."""
        error = APIConnectionError("Connection failed")
        assert isinstance(error, ChatProviderError)
        assert error.message == "Connection failed"

    def test_api_timeout_error(self):
        """Test APITimeoutError creation."""
        error = APITimeoutError("Request timed out")
        assert isinstance(error, ChatProviderError)
        assert error.message == "Request timed out"

    def test_api_status_error(self):
        """Test APIStatusError creation."""
        error = APIStatusError(429, "Rate limit exceeded")
        assert isinstance(error, ChatProviderError)
        assert error.status_code == 429
        assert error.message == "Rate limit exceeded"

    def test_api_status_error_different_codes(self):
        """Test APIStatusError with different status codes."""
        codes = [400, 401, 403, 404, 429, 500, 502, 503]
        for code in codes:
            error = APIStatusError(code, f"Error {code}")
            assert error.status_code == code

    def test_api_empty_response_error(self):
        """Test APIEmptyResponseError creation."""
        error = APIEmptyResponseError("Empty response from API")
        assert isinstance(error, ChatProviderError)
        assert error.message == "Empty response from API"

    def test_exception_hierarchy(self):
        """Test that all exceptions inherit from ChatProviderError."""
        errors = [
            APIConnectionError("test"),
            APITimeoutError("test"),
            APIStatusError(500, "test"),
            APIEmptyResponseError("test"),
        ]
        for error in errors:
            assert isinstance(error, ChatProviderError)


class TestChatProviderProtocol:
    """Tests for ChatProvider protocol."""

    def test_protocol_is_runtime_checkable(self):
        """Test that ChatProvider is runtime checkable."""
        # ChatProvider should have @runtime_checkable
        from typing import runtime_checkable

        assert hasattr(ChatProvider, "__protocol_attrs__")

    def test_mock_provider_implements_protocol(self, mock_provider):
        """Test that MockProvider implements ChatProvider."""
        assert isinstance(mock_provider, ChatProvider)

    def test_mock_provider_has_model_name(self, mock_provider):
        """Test that mock provider has model_name property."""
        assert hasattr(mock_provider, "model_name")
        assert isinstance(mock_provider.model_name, str)

    def test_mock_provider_has_generate_method(self, mock_provider):
        """Test that mock provider has generate method."""
        assert hasattr(mock_provider, "generate")
        assert callable(mock_provider.generate)


class TestStreamedMessageProtocol:
    """Tests for StreamedMessage protocol."""

    def test_protocol_is_runtime_checkable(self):
        """Test that StreamedMessage is runtime checkable."""
        assert hasattr(StreamedMessage, "__protocol_attrs__")

    def test_mock_streamed_message_implements_protocol(self):
        """Test that MockStreamedMessage implements StreamedMessage."""
        from tests.conftest import MockStreamedMessage
        from agentlite import TextPart

        stream = MockStreamedMessage([TextPart(text="Hello")])
        assert isinstance(stream, StreamedMessage)

    def test_streamed_message_has_id_property(self):
        """Test that streamed message has id property."""
        from tests.conftest import MockStreamedMessage
        from agentlite import TextPart

        stream = MockStreamedMessage([TextPart(text="Hello")])
        assert hasattr(stream, "id")
        assert stream.id == "mock-msg-123"

    def test_streamed_message_has_usage_property(self):
        """Test that streamed message has usage property."""
        from tests.conftest import MockStreamedMessage
        from agentlite import TextPart

        stream = MockStreamedMessage([TextPart(text="Hello")])
        assert hasattr(stream, "usage")
        assert stream.usage is not None
        assert isinstance(stream.usage, TokenUsage)

    def test_streamed_message_is_async_iterable(self):
        """Test that streamed message is async iterable."""
        from tests.conftest import MockStreamedMessage
        from agentlite import TextPart

        stream = MockStreamedMessage([TextPart(text="Hello")])
        assert hasattr(stream, "__aiter__")
