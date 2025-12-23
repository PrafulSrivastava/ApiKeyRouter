"""Tests for RequestIntent and Message models."""

import pytest
from pydantic import ValidationError

from apikeyrouter.domain.models.request_intent import Message, RequestIntent


class TestMessage:
    """Tests for Message model."""

    def test_message_creation_with_required_fields(self) -> None:
        """Test creating a message with required fields."""
        msg = Message(role="user", content="Hello!")
        assert msg.role == "user"
        assert msg.content == "Hello!"
        assert msg.name is None
        assert msg.function_call is None

    def test_message_creation_with_optional_fields(self) -> None:
        """Test creating a message with optional fields."""
        msg = Message(
            role="assistant",
            content="Hi there!",
            name="assistant-1",
            function_call={"name": "get_weather", "arguments": '{"city": "NYC"}'},
        )
        assert msg.role == "assistant"
        assert msg.content == "Hi there!"
        assert msg.name == "assistant-1"
        assert msg.function_call == {"name": "get_weather", "arguments": '{"city": "NYC"}'}

    def test_message_role_validation(self) -> None:
        """Test that message role is validated."""
        # Valid roles
        for role in ["system", "user", "assistant", "tool"]:
            msg = Message(role=role, content="test")
            assert msg.role == role.lower()

        # Invalid role
        with pytest.raises(ValueError, match="Role must be one of"):
            Message(role="invalid", content="test")

    def test_message_role_case_insensitive(self) -> None:
        """Test that message role is case-insensitive."""
        msg = Message(role="USER", content="test")
        assert msg.role == "user"

    def test_message_content_validation(self) -> None:
        """Test that message content is validated."""
        # Valid content
        msg = Message(role="user", content="Hello world")
        assert msg.content == "Hello world"

        # Empty content should raise error
        with pytest.raises(ValueError, match="Message content cannot be empty"):
            Message(role="user", content="")

        # Whitespace-only content should raise error
        with pytest.raises(ValueError, match="Message content cannot be empty"):
            Message(role="user", content="   ")

    def test_message_content_stripped(self) -> None:
        """Test that message content is stripped of whitespace."""
        msg = Message(role="user", content="  Hello world  ")
        assert msg.content == "Hello world"

    def test_message_tool_calls(self) -> None:
        """Test message with tool calls (empty content allowed)."""
        msg = Message(
            role="assistant",
            content="",  # Empty content allowed when tool_calls present
            tool_calls=[
                {"id": "call_1", "type": "function", "function": {"name": "get_weather"}}
            ],
        )
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1
        assert msg.content == ""


class TestRequestIntent:
    """Tests for RequestIntent model."""

    def test_request_intent_creation_with_required_fields(self) -> None:
        """Test creating a RequestIntent with required fields."""
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )
        assert intent.model == "gpt-4"
        assert len(intent.messages) == 1
        assert intent.messages[0].content == "Hello!"
        assert intent.parameters == {}

    def test_request_intent_creation_with_parameters(self) -> None:
        """Test creating a RequestIntent with parameters."""
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
            parameters={"temperature": 0.7, "max_tokens": 100, "top_p": 0.9},
        )
        assert intent.model == "gpt-4"
        assert intent.parameters["temperature"] == 0.7
        assert intent.parameters["max_tokens"] == 100
        assert intent.parameters["top_p"] == 0.9

    def test_request_intent_model_validation(self) -> None:
        """Test that model identifier is validated."""
        # Valid model
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="test")],
        )
        assert intent.model == "gpt-4"

        # Empty model should raise error (Pydantic ValidationError)
        with pytest.raises(ValidationError):
            RequestIntent(model="", messages=[Message(role="user", content="test")])

        # Whitespace-only model should raise error
        with pytest.raises(ValidationError):
            RequestIntent(model="   ", messages=[Message(role="user", content="test")])

    def test_request_intent_model_stripped(self) -> None:
        """Test that model identifier is stripped."""
        intent = RequestIntent(
            model="  gpt-4  ",
            messages=[Message(role="user", content="test")],
        )
        assert intent.model == "gpt-4"

    def test_request_intent_messages_validation(self) -> None:
        """Test that messages list is validated."""
        # Valid messages
        intent = RequestIntent(
            model="gpt-4",
            messages=[
                Message(role="system", content="You are helpful"),
                Message(role="user", content="Hello!"),
            ],
        )
        assert len(intent.messages) == 2

        # Empty messages should raise error (Pydantic ValidationError)
        with pytest.raises(ValidationError):
            RequestIntent(model="gpt-4", messages=[])

    def test_request_intent_helper_methods(self) -> None:
        """Test helper methods for common parameters."""
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="test")],
            parameters={"temperature": 0.7, "max_tokens": 100, "top_p": 0.9, "stream": True},
        )

        assert intent.get_temperature() == 0.7
        assert intent.get_max_tokens() == 100
        assert intent.get_top_p() == 0.9
        assert intent.get_stream() is True

    def test_request_intent_helper_methods_defaults(self) -> None:
        """Test helper methods return None/False when parameters not set."""
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="test")],
        )

        assert intent.get_temperature() is None
        assert intent.get_max_tokens() is None
        assert intent.get_top_p() is None
        assert intent.get_stream() is False  # Defaults to False

    def test_request_intent_multiple_messages(self) -> None:
        """Test RequestIntent with multiple messages."""
        intent = RequestIntent(
            model="gpt-4",
            messages=[
                Message(role="system", content="You are a helpful assistant"),
                Message(role="user", content="What is 2+2?"),
                Message(role="assistant", content="2+2 equals 4"),
                Message(role="user", content="What about 3+3?"),
            ],
        )
        assert len(intent.messages) == 4
        assert intent.messages[0].role == "system"
        assert intent.messages[1].role == "user"
        assert intent.messages[2].role == "assistant"
        assert intent.messages[3].role == "user"

