"""RequestIntent and Message models for system-defined request format."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Message(BaseModel):
    """Represents a chat message in a conversation.

    Messages are the building blocks of LLM conversations. Each message
    has a role (system, user, assistant, tool) and content. Optional fields
    support advanced features like function calling and tool usage.

    Example:
        ```python
        user_msg = Message(role="user", content="Hello!")
        system_msg = Message(role="system", content="You are a helpful assistant")
        ```
    """

    role: str = Field(
        ...,
        description="Message role: 'system', 'user', 'assistant', or 'tool'",
        min_length=1,
    )
    content: str = Field(
        ...,
        description="Message content text",
    )
    name: str | None = Field(
        default=None,
        description="Optional name for the message (e.g., function name)",
    )
    function_call: dict[str, Any] | None = Field(
        default=None,
        description="Function call information (for function calling)",
    )
    tool_calls: list[dict[str, Any]] | None = Field(
        default=None,
        description="Tool calls made by the assistant",
    )
    tool_call_id: str | None = Field(
        default=None,
        description="Tool call ID (for tool role messages)",
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate message role."""
        valid_roles = {"system", "user", "assistant", "tool"}
        if v.lower() not in valid_roles:
            raise ValueError(
                f"Role must be one of {valid_roles}, got {v!r}"
            )
        return v.lower()

    @field_validator("content", mode="before")
    @classmethod
    def validate_and_strip_content(cls, v: str) -> str:
        """Validate and strip message content."""
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def validate_content_with_tool_calls(self) -> Message:
        """Validate message content - allow empty if tool_calls present."""
        # Allow empty content if tool_calls are present (for assistant messages with tool calls)
        if (not self.content or not self.content.strip()) and not self.tool_calls:
            raise ValueError("Message content cannot be empty unless tool_calls are present")
        return self


class RequestIntent(BaseModel):
    """System-defined request format for LLM API calls.

    RequestIntent represents a provider-agnostic request structure. All
    providers must adapt their API calls to match this format, ensuring
    the system controls the interface rather than adapting to each provider.

    Key Features:
    - Model identifier specifies which LLM to use
    - Messages array contains the conversation history
    - Parameters dict supports common LLM parameters (temperature, max_tokens, etc.)
    - Provider-agnostic structure enables easy provider switching

    Example:
        ```python
        intent = RequestIntent(
            model="gpt-4",
            messages=[
                Message(role="system", content="You are helpful"),
                Message(role="user", content="Hello!")
            ],
            parameters={"temperature": 0.7, "max_tokens": 100}
        )
        ```
    """

    model: str = Field(
        ...,
        description="LLM model identifier (e.g., 'gpt-4', 'claude-3-opus')",
        min_length=1,
    )
    messages: list[Message] = Field(
        ...,
        description="List of chat messages in the conversation",
        min_length=1,
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="LLM parameters (temperature, max_tokens, top_p, etc.)",
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        """Validate model identifier."""
        if not v or not v.strip():
            raise ValueError("Model identifier cannot be empty")
        v = v.strip()
        if len(v) > 200:
            raise ValueError("Model identifier must be 200 characters or less")
        return v

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: list[Message]) -> list[Message]:
        """Validate messages list."""
        if not v:
            raise ValueError("Messages list cannot be empty")
        if len(v) > 1000:
            raise ValueError("Messages list cannot contain more than 1000 messages")
        return v

    @field_validator("parameters", mode="before")
    @classmethod
    def validate_parameters(cls, v: dict[str, Any] | None) -> dict[str, Any]:
        """Validate parameters dictionary."""
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("Parameters must be a dictionary")
        # Validate parameter ranges
        if "temperature" in v:
            temp = v["temperature"]
            if isinstance(temp, (int, float)) and (temp < 0.0 or temp > 2.0):
                raise ValueError("Temperature must be between 0.0 and 2.0")
        if "max_tokens" in v:
            max_tokens = v["max_tokens"]
            if isinstance(max_tokens, int) and (max_tokens < 1 or max_tokens > 1000000):
                raise ValueError("max_tokens must be a positive integer not exceeding 1000000")
        if "top_p" in v:
            top_p = v["top_p"]
            if isinstance(top_p, (int, float)) and (top_p < 0.0 or top_p > 1.0):
                raise ValueError("top_p must be between 0.0 and 1.0")
        return v

    def get_temperature(self) -> float | None:
        """Get temperature parameter if set.

        Returns:
            Temperature value (0.0 to 2.0) or None if not set.
        """
        return self.parameters.get("temperature")

    def get_max_tokens(self) -> int | None:
        """Get max_tokens parameter if set.

        Returns:
            Max tokens value or None if not set.
        """
        return self.parameters.get("max_tokens")

    def get_top_p(self) -> float | None:
        """Get top_p parameter if set.

        Returns:
            Top-p value (0.0 to 1.0) or None if not set.
        """
        return self.parameters.get("top_p")

    def get_stream(self) -> bool:
        """Get stream parameter if set.

        Returns:
            Stream value (defaults to False if not set).
        """
        return self.parameters.get("stream", False)

