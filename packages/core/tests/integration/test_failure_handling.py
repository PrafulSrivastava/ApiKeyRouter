"""Integration tests for failure handling and retry workflow."""

from datetime import datetime
from decimal import Decimal

import pytest

from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.request_intent import Message, RequestIntent
from apikeyrouter.domain.models.system_error import ErrorCategory, SystemError
from apikeyrouter.domain.models.system_response import ResponseMetadata, SystemResponse, TokenUsage
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore
from apikeyrouter.router import ApiKeyRouter


@pytest.fixture
async def api_key_router():
    """Create ApiKeyRouter instance for testing."""
    state_store = InMemoryStateStore(max_decisions=1000, max_transitions=1000)
    return ApiKeyRouter(state_store=state_store)


class MockProviderAdapterWithFailures(ProviderAdapter):
    """Mock ProviderAdapter that can simulate failures."""

    def __init__(
        self,
        provider_id: str = "openai",
        failure_keys: set[str] | None = None,
        retryable_errors: bool = True,
    ) -> None:
        """Initialize mock adapter with failure configuration.

        Args:
            provider_id: Provider identifier.
            failure_keys: Set of key IDs that should fail.
            retryable_errors: Whether errors should be retryable.
        """
        self.provider_id = provider_id
        self.failure_keys = failure_keys or set()
        self.retryable_errors = retryable_errors
        self.call_count: dict[str, int] = {}

    async def execute_request(self, intent, key):
        """Execute request - fails for keys in failure_keys set."""
        key_id = key.id
        self.call_count[key_id] = self.call_count.get(key_id, 0) + 1

        if key_id in self.failure_keys:
            raise SystemError(
                category=ErrorCategory.ProviderError,
                message=f"Mock failure for key {key_id}",
                retryable=self.retryable_errors,
            )

        # Success
        from apikeyrouter.domain.models.cost_estimate import CostEstimate

        return SystemResponse(
            content="Success response",
            request_id="mock-request-id",
            key_used=key.id,
            metadata=ResponseMetadata(
                model_used=intent.model if hasattr(intent, "model") else "mock-model",
                tokens_used=TokenUsage(input_tokens=10, output_tokens=5),
                response_time_ms=100,
                provider_id=key.provider_id,
                timestamp=datetime.utcnow(),
            ),
            cost=CostEstimate(
                amount=Decimal("0.001"),
                currency="USD",
                confidence=0.9,
                estimation_method="mock",
                input_tokens_estimate=10,
                output_tokens_estimate=5,
            ),
        )

    def normalize_response(self, provider_response):
        """Normalize response - mock implementation."""
        return provider_response

    def map_error(self, provider_error: Exception):
        """Map error - mock implementation."""
        if isinstance(provider_error, SystemError):
            return provider_error
        return SystemError(
            category=ErrorCategory.ProviderError,
            message=str(provider_error),
            retryable=self.retryable_errors,
        )

    def get_capabilities(self):
        """Get capabilities - mock implementation."""
        return {
            "models": ["gpt-4", "gpt-3.5-turbo"],
            "supports_streaming": True,
        }

    async def estimate_cost(self, request_intent):
        """Estimate cost - mock implementation."""
        from apikeyrouter.domain.models.cost_estimate import CostEstimate

        return CostEstimate(
            amount=Decimal("0.001"),
            currency="USD",
            confidence=0.9,
            estimation_method="mock",
            input_tokens_estimate=10,
            output_tokens_estimate=5,
        )

    async def get_health(self):
        """Get health - mock implementation."""
        return {"status": "healthy", "latency_ms": 100}


@pytest.fixture
def mock_adapter_with_failures() -> MockProviderAdapterWithFailures:
    """Create mock provider adapter with failure support."""
    return MockProviderAdapterWithFailures(provider_id="openai")


class TestFailureHandlingAndRetry:
    """Tests for failure handling and retry workflow."""

    @pytest.mark.asyncio
    async def test_failure_interpreted_correctly(
        self, api_key_router, mock_adapter_with_failures
    ):
        """Test failure interpreted correctly."""
        # Register provider and key that will fail
        await api_key_router.register_provider("openai", mock_adapter_with_failures)
        key = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )

        # Configure adapter to fail for this key
        mock_adapter_with_failures.failure_keys = {key.id}

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - should fail
        with pytest.raises(SystemError) as exc_info:
            await api_key_router.route(request_intent)

        # Verify error is correct
        assert exc_info.value.category == ErrorCategory.ProviderError
        assert "Mock failure" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_retry_with_different_key(
        self, api_key_router, mock_adapter_with_failures
    ):
        """Test retry with different key."""
        # Register provider and multiple keys
        await api_key_router.register_provider("openai", mock_adapter_with_failures)
        key1 = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )
        key2 = await api_key_router.register_key(
            key_material="sk-test-key-2", provider_id="openai"
        )

        # Configure adapter to fail for key1 but succeed for key2
        mock_adapter_with_failures.failure_keys = {key1.id}

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - should retry with key2 and succeed
        response = await api_key_router.route(request_intent)

        # Verify response succeeded with key2
        assert response is not None
        assert response.key_used == key2.id
        assert response.content == "Success response"

        # Verify key1 was tried (call_count > 0)
        assert mock_adapter_with_failures.call_count.get(key1.id, 0) > 0

    @pytest.mark.asyncio
    async def test_key_state_updated_on_failure(
        self, api_key_router, mock_adapter_with_failures
    ):
        """Test key state updated on failure."""
        # Register provider and key
        await api_key_router.register_provider("openai", mock_adapter_with_failures)
        key = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )

        # Get initial failure count
        initial_key = await api_key_router.key_manager.get_key(key.id)
        initial_failures = initial_key.failure_count if initial_key else 0

        # Configure adapter to fail
        mock_adapter_with_failures.failure_keys = {key.id}

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - should fail
        with pytest.raises(SystemError):
            await api_key_router.route(request_intent)

        # Verify failure count increased
        updated_key = await api_key_router.key_manager.get_key(key.id)
        assert updated_key is not None
        assert updated_key.failure_count > initial_failures

    @pytest.mark.asyncio
    async def test_non_retryable_error_stops_retries(
        self, api_key_router, mock_adapter_with_failures
    ):
        """Test non-retryable error stops retries."""
        # Register provider and multiple keys
        await api_key_router.register_provider("openai", mock_adapter_with_failures)
        key1 = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )
        key2 = await api_key_router.register_key(
            key_material="sk-test-key-2", provider_id="openai"
        )

        # Configure adapter to fail with non-retryable error for key1
        mock_adapter_with_failures.failure_keys = {key1.id}
        mock_adapter_with_failures.retryable_errors = False

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - should fail immediately without trying key2
        with pytest.raises(SystemError) as exc_info:
            await api_key_router.route(request_intent)

        # Verify error is non-retryable
        assert exc_info.value.retryable is False

        # Verify key2 was not tried
        assert mock_adapter_with_failures.call_count.get(key2.id, 0) == 0

    @pytest.mark.asyncio
    async def test_all_keys_fail_raises_error(
        self, api_key_router, mock_adapter_with_failures
    ):
        """Test that when all keys fail, error is raised."""
        # Register provider and multiple keys
        await api_key_router.register_provider("openai", mock_adapter_with_failures)
        key1 = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )
        key2 = await api_key_router.register_key(
            key_material="sk-test-key-2", provider_id="openai"
        )

        # Configure adapter to fail for all keys
        mock_adapter_with_failures.failure_keys = {key1.id, key2.id}
        mock_adapter_with_failures.retryable_errors = True

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - should fail after trying all keys
        with pytest.raises(SystemError):
            await api_key_router.route(request_intent)

        # Verify both keys were tried
        assert mock_adapter_with_failures.call_count.get(key1.id, 0) > 0
        assert mock_adapter_with_failures.call_count.get(key2.id, 0) > 0

    @pytest.mark.asyncio
    async def test_retry_with_alternative_key_succeeds(
        self, api_key_router, mock_adapter_with_failures
    ):
        """Test that retry with alternative key succeeds."""
        # Register provider and multiple keys
        await api_key_router.register_provider("openai", mock_adapter_with_failures)
        key1 = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )
        key2 = await api_key_router.register_key(
            key_material="sk-test-key-2", provider_id="openai"
        )
        key3 = await api_key_router.register_key(
            key_material="sk-test-key-3", provider_id="openai"
        )

        # Configure adapter to fail for key1 and key2, succeed for key3
        mock_adapter_with_failures.failure_keys = {key1.id, key2.id}

        # Create request intent
        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )

        # Route request - should retry and succeed with key3
        response = await api_key_router.route(request_intent)

        # Verify response succeeded with key3
        assert response is not None
        assert response.key_used == key3.id
        assert response.content == "Success response"

