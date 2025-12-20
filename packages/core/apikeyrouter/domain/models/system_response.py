"""SystemResponse and related models for system-defined response format."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

if TYPE_CHECKING:
    from apikeyrouter.domain.models.cost_estimate import CostEstimate
else:
    # Import at runtime for model_rebuild
    from apikeyrouter.domain.models.cost_estimate import CostEstimate  # noqa: F401


class TokenUsage(BaseModel):
    """Represents token usage for an LLM request.

    TokenUsage tracks the number of tokens consumed in a request,
    broken down by input (prompt) and output (completion) tokens.
    The total is computed automatically.

    Example:
        ```python
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150
        ```
    """

    input_tokens: int = Field(
        ...,
        description="Number of input/prompt tokens",
        ge=0,
    )
    output_tokens: int = Field(
        ...,
        description="Number of output/completion tokens",
        ge=0,
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
    )

    @computed_field
    @property
    def total_tokens(self) -> int:
        """Compute total tokens (input + output)."""
        return self.input_tokens + self.output_tokens


class ResponseMetadata(BaseModel):
    """Metadata about a system response for observability.

    ResponseMetadata provides comprehensive information about a response
    for observability, debugging, and analytics. It includes information
    about the model used, token consumption, timing, and provider details.

    Example:
        ```python
        metadata = ResponseMetadata(
            model_used="gpt-4",
            tokens_used=TokenUsage(input_tokens=100, output_tokens=50),
            response_time_ms=1250,
            provider_id="openai",
            timestamp=datetime.utcnow()
        )
        ```
    """

    model_used: str = Field(
        ...,
        description="Model identifier that was actually used",
        min_length=1,
    )
    tokens_used: TokenUsage = Field(
        ...,
        description="Token usage information",
    )
    response_time_ms: int = Field(
        ...,
        description="Response time in milliseconds",
        ge=0,
    )
    provider_id: str = Field(
        ...,
        description="Provider identifier that handled the request",
        min_length=1,
    )
    timestamp: datetime = Field(
        ...,
        description="Timestamp when response was generated",
    )
    finish_reason: str | None = Field(
        default=None,
        description="Reason for completion (stop, length, tool_calls, etc.)",
    )
    request_id: str | None = Field(
        default=None,
        description="Request identifier for correlation",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation identifier for distributed tracing",
    )
    additional_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional provider-specific metadata",
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        str_strip_whitespace=True,
        protected_namespaces=(),
    )

    @field_validator("model_used")
    @classmethod
    def validate_model_used(cls, v: str) -> str:
        """Validate model identifier."""
        if not v or not v.strip():
            raise ValueError("Model identifier cannot be empty")
        return v.strip()

    @field_validator("provider_id")
    @classmethod
    def validate_provider_id(cls, v: str) -> str:
        """Validate provider identifier."""
        if not v or not v.strip():
            raise ValueError("Provider identifier cannot be empty")
        return v.strip().lower()


class SystemResponse(BaseModel):
    """System-defined response format for LLM API calls.

    SystemResponse represents a provider-agnostic response structure.
    All provider responses are normalized to this format, ensuring the
    system works with a consistent structure regardless of provider.

    Key Features:
    - Content contains the actual LLM response text
    - Metadata provides observability information
    - Cost tracking enables budget management
    - Key tracking enables usage analytics

    Example:
        ```python
        response = SystemResponse(
            content="Hello! How can I help you?",
            metadata=ResponseMetadata(...),
            cost=None,
            key_used="key-123",
            request_id="req-456"
        )
        print(response.content)  # LLM response
        print(response.metadata.tokens_used.total_tokens)  # Token count
        ```
    """

    content: str = Field(
        ...,
        description="Response text content from the LLM",
    )
    metadata: ResponseMetadata = Field(
        ...,
        description="Response metadata for observability",
    )
    cost: CostEstimate | None = Field(
        default=None,
        description="Cost estimate",
    )
    key_used: str = Field(
        ...,
        description="ID of the API key that was used for this request",
        min_length=1,
    )
    request_id: str = Field(
        ...,
        description="Unique identifier for this request",
        min_length=1,
    )

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate response content."""
        # Allow empty content (some responses might be empty)
        return v

    @field_validator("key_used")
    @classmethod
    def validate_key_used(cls, v: str) -> str:
        """Validate key ID."""
        if not v or not v.strip():
            raise ValueError("Key ID cannot be empty")
        return v.strip()

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, v: str) -> str:
        """Validate request ID."""
        if not v or not v.strip():
            raise ValueError("Request ID cannot be empty")
        return v.strip()


# Rebuild model to resolve forward references
SystemResponse.model_rebuild()
