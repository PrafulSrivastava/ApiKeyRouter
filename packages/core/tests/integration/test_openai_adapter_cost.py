"""Tests for OpenAIAdapter cost estimation."""

from decimal import Decimal

import pytest

from apikeyrouter.domain.models.cost_estimate import CostEstimate
from apikeyrouter.domain.models.request_intent import Message, RequestIntent
from apikeyrouter.domain.models.system_error import ErrorCategory, SystemError
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter


class TestOpenAIAdapterCostEstimation:
    """Tests for estimate_cost method."""

    @pytest.mark.asyncio
    async def test_estimate_cost_gpt4(self) -> None:
        """Test cost estimation for gpt-4."""
        adapter = OpenAIAdapter()
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
            parameters={"max_tokens": 100},
        )

        estimate = await adapter.estimate_cost(intent)

        assert isinstance(estimate, CostEstimate)
        assert estimate.currency == "USD"
        assert estimate.amount > 0
        assert estimate.input_tokens_estimate > 0
        assert estimate.output_tokens_estimate > 0
        assert 0.0 <= estimate.confidence <= 1.0
        assert estimate.estimation_method == "token_count_approximation"
        assert estimate.breakdown is not None
        assert "input_cost" in estimate.breakdown
        assert "output_cost" in estimate.breakdown

    @pytest.mark.asyncio
    async def test_estimate_cost_gpt35_turbo(self) -> None:
        """Test cost estimation for gpt-3.5-turbo."""
        adapter = OpenAIAdapter()
        intent = RequestIntent(
            model="gpt-3.5-turbo",
            messages=[Message(role="user", content="Hello!")],
            parameters={"max_tokens": 100},
        )

        estimate = await adapter.estimate_cost(intent)

        assert isinstance(estimate, CostEstimate)
        assert estimate.currency == "USD"
        assert estimate.amount > 0
        # gpt-3.5-turbo should be cheaper than gpt-4
        assert estimate.amount < Decimal("0.01")  # Should be very cheap

    @pytest.mark.asyncio
    async def test_estimate_cost_calculates_correctly(self) -> None:
        """Test that cost calculation is mathematically correct."""
        adapter = OpenAIAdapter()
        # Use a simple message to get predictable token count
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello")],  # ~5 chars = ~1-2 tokens
            parameters={"max_tokens": 1000},  # 80% = 800 tokens
        )

        estimate = await adapter.estimate_cost(intent)

        # Verify calculation: (input_tokens / 1000) * input_price + (output_tokens / 1000) * output_price
        input_cost = (Decimal(estimate.input_tokens_estimate) / Decimal(1000)) * Decimal("0.03")
        output_cost = (Decimal(estimate.output_tokens_estimate) / Decimal(1000)) * Decimal("0.06")
        expected_total = input_cost + output_cost

        # Allow small rounding differences
        assert abs(estimate.amount - expected_total) < Decimal("0.0001")

    @pytest.mark.asyncio
    async def test_estimate_cost_without_max_tokens(self) -> None:
        """Test cost estimation when max_tokens not specified."""
        adapter = OpenAIAdapter()
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        estimate = await adapter.estimate_cost(intent)

        assert estimate.output_tokens_estimate == adapter.DEFAULT_OUTPUT_TOKENS
        assert estimate.confidence == 0.7  # Lower confidence without max_tokens

    @pytest.mark.asyncio
    async def test_estimate_cost_with_max_tokens(self) -> None:
        """Test cost estimation with max_tokens specified."""
        adapter = OpenAIAdapter()
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
            parameters={"max_tokens": 500},
        )

        estimate = await adapter.estimate_cost(intent)

        # Should estimate 80% of max_tokens
        assert estimate.output_tokens_estimate == 400
        assert estimate.confidence == 0.85  # Higher confidence with max_tokens

    @pytest.mark.asyncio
    async def test_estimate_cost_handles_unknown_model(self) -> None:
        """Test that estimate_cost raises error for unknown model."""
        adapter = OpenAIAdapter()
        intent = RequestIntent(
            model="unknown-model-xyz",
            messages=[Message(role="user", content="Hello!")],
        )

        with pytest.raises(SystemError) as exc_info:
            await adapter.estimate_cost(intent)

        assert exc_info.value.category == ErrorCategory.ValidationError
        assert "unknown model" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_estimate_cost_token_estimation(self) -> None:
        """Test that token estimation works correctly."""
        adapter = OpenAIAdapter()

        # Test with different message lengths
        intent1 = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hi")],  # Short message
        )
        estimate1 = await adapter.estimate_cost(intent1)

        intent2 = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="This is a much longer message that should result in more tokens being estimated.")],  # Long message
        )
        estimate2 = await adapter.estimate_cost(intent2)

        # Longer message should have more input tokens
        assert estimate2.input_tokens_estimate > estimate1.input_tokens_estimate
        # But output tokens should be same (both use default)
        assert estimate2.output_tokens_estimate == estimate1.output_tokens_estimate

    @pytest.mark.asyncio
    async def test_estimate_cost_multiple_messages(self) -> None:
        """Test cost estimation with multiple messages."""
        adapter = OpenAIAdapter()
        intent = RequestIntent(
            model="gpt-4",
            messages=[
                Message(role="system", content="You are helpful"),
                Message(role="user", content="Hello!"),
                Message(role="assistant", content="Hi there!"),
                Message(role="user", content="How are you?"),
            ],
        )

        estimate = await adapter.estimate_cost(intent)

        # Multiple messages should result in more input tokens
        assert estimate.input_tokens_estimate > 10  # Should be more than single message

    @pytest.mark.asyncio
    async def test_estimate_cost_breakdown(self) -> None:
        """Test that cost breakdown is provided."""
        adapter = OpenAIAdapter()
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
            parameters={"max_tokens": 100},
        )

        estimate = await adapter.estimate_cost(intent)

        assert estimate.breakdown is not None
        assert "input_cost" in estimate.breakdown
        assert "output_cost" in estimate.breakdown
        assert estimate.breakdown["input_cost"] >= 0
        assert estimate.breakdown["output_cost"] >= 0
        # Total should equal sum of breakdown
        assert abs(estimate.amount - (estimate.breakdown["input_cost"] + estimate.breakdown["output_cost"])) < Decimal("0.0001")

    @pytest.mark.asyncio
    async def test_estimate_cost_model_variants(self) -> None:
        """Test cost estimation for different model variants."""
        adapter = OpenAIAdapter()

        # Test gpt-4-turbo
        intent_turbo = RequestIntent(
            model="gpt-4-turbo",
            messages=[Message(role="user", content="Hello!")],
            parameters={"max_tokens": 100},
        )
        estimate_turbo = await adapter.estimate_cost(intent_turbo)

        # Test gpt-4
        intent_gpt4 = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
            parameters={"max_tokens": 100},
        )
        estimate_gpt4 = await adapter.estimate_cost(intent_gpt4)

        # gpt-4-turbo should be cheaper than gpt-4
        assert estimate_turbo.amount < estimate_gpt4.amount

    @pytest.mark.asyncio
    async def test_estimate_cost_total_tokens_property(self) -> None:
        """Test that total_tokens_estimate property works."""
        adapter = OpenAIAdapter()
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
        )

        estimate = await adapter.estimate_cost(intent)

        assert estimate.total_tokens_estimate == estimate.input_tokens_estimate + estimate.output_tokens_estimate

