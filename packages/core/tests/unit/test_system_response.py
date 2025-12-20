"""Tests for SystemResponse and related models."""

from datetime import datetime

from pydantic import ValidationError

import pytest

from apikeyrouter.domain.models.cost_estimate import CostEstimate
from apikeyrouter.domain.models.system_response import (
    ResponseMetadata,
    SystemResponse,
    TokenUsage,
)


class TestTokenUsage:
    """Tests for TokenUsage model."""

    def test_token_usage_creation(self) -> None:
        """Test creating a TokenUsage instance."""
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150

    def test_token_usage_total_computed(self) -> None:
        """Test that total_tokens is computed correctly."""
        usage = TokenUsage(input_tokens=200, output_tokens=300)
        assert usage.total_tokens == 500

    def test_token_usage_zero_tokens(self) -> None:
        """Test TokenUsage with zero tokens."""
        usage = TokenUsage(input_tokens=0, output_tokens=0)
        assert usage.total_tokens == 0

    def test_token_usage_validation(self) -> None:
        """Test that token counts cannot be negative."""
        # Valid - zero is allowed
        usage = TokenUsage(input_tokens=0, output_tokens=0)
        assert usage.input_tokens == 0

        # Invalid - negative not allowed
        with pytest.raises(Exception):  # Pydantic validation error
            TokenUsage(input_tokens=-1, output_tokens=0)


class TestResponseMetadata:
    """Tests for ResponseMetadata model."""

    def test_response_metadata_creation(self) -> None:
        """Test creating a ResponseMetadata instance."""
        tokens = TokenUsage(input_tokens=100, output_tokens=50)
        metadata = ResponseMetadata(
            model_used="gpt-4",
            tokens_used=tokens,
            response_time_ms=1250,
            provider_id="openai",
            timestamp=datetime.utcnow(),
        )
        assert metadata.model_used == "gpt-4"
        assert metadata.tokens_used.input_tokens == 100
        assert metadata.response_time_ms == 1250
        assert metadata.provider_id == "openai"
        assert isinstance(metadata.timestamp, datetime)

    def test_response_metadata_with_optional_fields(self) -> None:
        """Test ResponseMetadata with optional fields."""
        tokens = TokenUsage(input_tokens=100, output_tokens=50)
        metadata = ResponseMetadata(
            model_used="gpt-4",
            tokens_used=tokens,
            response_time_ms=1250,
            provider_id="openai",
            timestamp=datetime.utcnow(),
            finish_reason="stop",
            request_id="req-123",
            additional_metadata={"custom": "value"},
        )
        assert metadata.finish_reason == "stop"
        assert metadata.request_id == "req-123"
        assert metadata.additional_metadata == {"custom": "value"}

    def test_response_metadata_model_validation(self) -> None:
        """Test that model_used is validated."""
        tokens = TokenUsage(input_tokens=100, output_tokens=50)
        
        # Valid model
        metadata = ResponseMetadata(
            model_used="gpt-4",
            tokens_used=tokens,
            response_time_ms=1000,
            provider_id="openai",
            timestamp=datetime.utcnow(),
        )
        assert metadata.model_used == "gpt-4"

        # Empty model should raise error (Pydantic ValidationError)
        with pytest.raises(ValidationError):
            ResponseMetadata(
                model_used="",
                tokens_used=tokens,
                response_time_ms=1000,
                provider_id="openai",
                timestamp=datetime.utcnow(),
            )

    def test_response_metadata_provider_id_validation(self) -> None:
        """Test that provider_id is validated and lowercased."""
        tokens = TokenUsage(input_tokens=100, output_tokens=50)
        
        metadata = ResponseMetadata(
            model_used="gpt-4",
            tokens_used=tokens,
            response_time_ms=1000,
            provider_id="OPENAI",
            timestamp=datetime.utcnow(),
        )
        assert metadata.provider_id == "openai"  # Should be lowercased

        # Empty provider_id should raise error (Pydantic ValidationError)
        with pytest.raises(ValidationError):
            ResponseMetadata(
                model_used="gpt-4",
                tokens_used=tokens,
                response_time_ms=1000,
                provider_id="",
                timestamp=datetime.utcnow(),
            )

    def test_response_metadata_response_time_validation(self) -> None:
        """Test that response_time_ms cannot be negative."""
        tokens = TokenUsage(input_tokens=100, output_tokens=50)
        
        # Valid - zero is allowed
        metadata = ResponseMetadata(
            model_used="gpt-4",
            tokens_used=tokens,
            response_time_ms=0,
            provider_id="openai",
            timestamp=datetime.utcnow(),
        )
        assert metadata.response_time_ms == 0

        # Invalid - negative not allowed
        with pytest.raises(Exception):  # Pydantic validation error
            ResponseMetadata(
                model_used="gpt-4",
                tokens_used=tokens,
                response_time_ms=-1,
                provider_id="openai",
                timestamp=datetime.utcnow(),
            )


class TestSystemResponse:
    """Tests for SystemResponse model."""

    def test_system_response_creation(self) -> None:
        """Test creating a SystemResponse instance."""
        tokens = TokenUsage(input_tokens=100, output_tokens=50)
        metadata = ResponseMetadata(
            model_used="gpt-4",
            tokens_used=tokens,
            response_time_ms=1250,
            provider_id="openai",
            timestamp=datetime.utcnow(),
        )
        response = SystemResponse(
            content="Hello! How can I help you?",
            metadata=metadata,
            cost=None,
            key_used="key-123",
            request_id="req-456",
        )
        assert response.content == "Hello! How can I help you?"
        assert response.metadata.model_used == "gpt-4"
        assert response.cost is None
        assert response.key_used == "key-123"
        assert response.request_id == "req-456"

    def test_system_response_with_cost(self) -> None:
        """Test SystemResponse with cost estimate."""
        tokens = TokenUsage(input_tokens=100, output_tokens=50)
        metadata = ResponseMetadata(
            model_used="gpt-4",
            tokens_used=tokens,
            response_time_ms=1250,
            provider_id="openai",
            timestamp=datetime.utcnow(),
        )
        # Use proper CostEstimate model
        from decimal import Decimal
        cost_estimate = CostEstimate(
            amount=Decimal("0.002"),
            currency="USD",
            confidence=0.9,
            estimation_method="token_count_approximation",
            input_tokens_estimate=100,
            output_tokens_estimate=50,
        )
        response = SystemResponse(
            content="Hello!",
            metadata=metadata,
            cost=cost_estimate,
            key_used="key-123",
            request_id="req-456",
        )
        assert response.cost == cost_estimate

    def test_system_response_empty_content(self) -> None:
        """Test SystemResponse with empty content (allowed)."""
        tokens = TokenUsage(input_tokens=100, output_tokens=0)
        metadata = ResponseMetadata(
            model_used="gpt-4",
            tokens_used=tokens,
            response_time_ms=1000,
            provider_id="openai",
            timestamp=datetime.utcnow(),
        )
        response = SystemResponse(
            content="",
            metadata=metadata,
            cost=None,
            key_used="key-123",
            request_id="req-456",
        )
        assert response.content == ""

    def test_system_response_key_validation(self) -> None:
        """Test that key_used is validated."""
        tokens = TokenUsage(input_tokens=100, output_tokens=50)
        metadata = ResponseMetadata(
            model_used="gpt-4",
            tokens_used=tokens,
            response_time_ms=1000,
            provider_id="openai",
            timestamp=datetime.utcnow(),
        )

        # Valid key
        response = SystemResponse(
            content="test",
            metadata=metadata,
            cost=None,
            key_used="key-123",
            request_id="req-456",
        )
        assert response.key_used == "key-123"

        # Empty key should raise error (Pydantic ValidationError)
        with pytest.raises(ValidationError):
            SystemResponse(
                content="test",
                metadata=metadata,
                cost=None,
                key_used="",
                request_id="req-456",
            )

    def test_system_response_request_id_validation(self) -> None:
        """Test that request_id is validated."""
        tokens = TokenUsage(input_tokens=100, output_tokens=50)
        metadata = ResponseMetadata(
            model_used="gpt-4",
            tokens_used=tokens,
            response_time_ms=1000,
            provider_id="openai",
            timestamp=datetime.utcnow(),
        )

        # Valid request_id
        response = SystemResponse(
            content="test",
            metadata=metadata,
            cost=None,
            key_used="key-123",
            request_id="req-456",
        )
        assert response.request_id == "req-456"

        # Empty request_id should raise error (Pydantic ValidationError)
        with pytest.raises(ValidationError):
            SystemResponse(
                content="test",
                metadata=metadata,
                cost=None,
                key_used="key-123",
                request_id="",
            )

    def test_system_response_full_example(self) -> None:
        """Test a complete SystemResponse example."""
        tokens = TokenUsage(input_tokens=150, output_tokens=75)
        metadata = ResponseMetadata(
            model_used="gpt-4",
            tokens_used=tokens,
            response_time_ms=2340,
            provider_id="openai",
            timestamp=datetime.utcnow(),
            finish_reason="stop",
            request_id="req-789",
            additional_metadata={"model_version": "gpt-4-0613"},
        )
        response = SystemResponse(
            content="The answer is 42.",
            metadata=metadata,
            cost=None,
            key_used="key-abc",
            request_id="req-789",
        )
        
        assert response.content == "The answer is 42."
        assert response.metadata.tokens_used.total_tokens == 225
        assert response.metadata.finish_reason == "stop"
        assert response.key_used == "key-abc"
        assert response.request_id == "req-789"

