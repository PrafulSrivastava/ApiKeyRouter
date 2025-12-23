"""Integration tests for key registration and state management."""

from datetime import datetime
from decimal import Decimal

import pytest

from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.api_key import KeyState
from apikeyrouter.domain.models.cost_estimate import CostEstimate
from apikeyrouter.domain.models.request_intent import RequestIntent
from apikeyrouter.domain.models.system_response import ResponseMetadata, SystemResponse, TokenUsage
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore
from apikeyrouter.router import ApiKeyRouter


@pytest.fixture
async def api_key_router():
    """Create ApiKeyRouter instance for testing."""
    state_store = InMemoryStateStore(max_decisions=1000, max_transitions=1000)
    return ApiKeyRouter(state_store=state_store)


class MockProviderAdapter(ProviderAdapter):
    """Mock ProviderAdapter for integration testing."""

    def __init__(self, provider_id: str = "openai") -> None:
        """Initialize mock adapter."""
        self.provider_id = provider_id

    async def execute_request(self, intent: RequestIntent, key):
        """Execute request - mock implementation."""
        return SystemResponse(
            content="Mocked response content",
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
        return provider_error

    async def estimate_cost(self, intent: RequestIntent):
        """Estimate cost - mock implementation."""
        return CostEstimate(
            amount=Decimal("0.001"),
            currency="USD",
            confidence=0.9,
            estimation_method="mock",
            input_tokens_estimate=10,
            output_tokens_estimate=5,
        )

    async def get_capabilities(self):
        """Get capabilities - mock implementation."""
        from apikeyrouter.domain.models.provider_capabilities import ProviderCapabilities

        return ProviderCapabilities(
            supported_models=["mock-model"],
            supports_streaming=True,
            supports_function_calling=False,
            max_tokens=4096,
        )

    async def get_health(self):
        """Get health - mock implementation."""
        from apikeyrouter.domain.models.health_state import HealthState

        return HealthState(status="healthy", message="Mock adapter is healthy")


class TestKeyRegistrationAndStateManagement:
    """Tests for key registration and state management workflow."""

    @pytest.mark.asyncio
    async def test_key_registration_workflow(self, api_key_router):
        """Test key registration workflow."""
        # Register provider first

        adapter = MockProviderAdapter(provider_id="openai")
        await api_key_router.register_provider("openai", adapter)

        # Register a key
        key = await api_key_router.register_key(
            key_material="sk-test-key-1",
            provider_id="openai",
            metadata={"account_tier": "pro", "region": "us-east"},
        )

        # Verify key was registered
        assert key is not None
        assert key.provider_id == "openai"
        assert key.state == KeyState.Available
        assert key.metadata.get("account_tier") == "pro"
        assert key.metadata.get("region") == "us-east"

        # Verify key can be retrieved
        retrieved_key = await api_key_router.key_manager.get_key(key.id)
        assert retrieved_key is not None
        assert retrieved_key.id == key.id

    @pytest.mark.asyncio
    async def test_key_state_management_workflow(self, api_key_router):
        """Test key state management workflow."""
        # Register provider and key

        adapter = MockProviderAdapter(provider_id="openai")
        await api_key_router.register_provider("openai", adapter)
        key = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )

        # Verify initial state
        assert key.state == KeyState.Available

        # Update key state to Throttled
        await api_key_router.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Throttled,
            reason="Rate limit exceeded",
        )

        # Verify state was updated
        updated_key = await api_key_router.key_manager.get_key(key.id)
        assert updated_key is not None
        assert updated_key.state == KeyState.Throttled

        # Update back to Available
        await api_key_router.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Available,
            reason="Cooldown expired",
        )

        # Verify state was updated
        updated_key = await api_key_router.key_manager.get_key(key.id)
        assert updated_key is not None
        assert updated_key.state == KeyState.Available

    @pytest.mark.asyncio
    async def test_key_revocation_workflow(self, api_key_router):
        """Test key revocation workflow."""
        # Register provider and key

        adapter = MockProviderAdapter(provider_id="openai")
        await api_key_router.register_provider("openai", adapter)
        key = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )

        # Disable key (revocation equivalent)
        await api_key_router.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Disabled,
            reason="Key compromised",
        )

        # Verify key is disabled
        disabled_key = await api_key_router.key_manager.get_key(key.id)
        assert disabled_key is not None
        assert disabled_key.state == KeyState.Disabled

        # Verify revoked key is not eligible
        eligible_keys = await api_key_router.key_manager.get_eligible_keys(
            provider_id="openai"
        )
        assert key.id not in [k.id for k in eligible_keys]

    @pytest.mark.asyncio
    async def test_key_rotation_workflow(self, api_key_router):
        """Test key rotation workflow."""
        # Register provider and key

        adapter = MockProviderAdapter(provider_id="openai")
        await api_key_router.register_provider("openai", adapter)
        old_key = await api_key_router.register_key(
            key_material="sk-old-key", provider_id="openai"
        )

        # Register new key (rotation)
        new_key = await api_key_router.register_key(
            key_material="sk-new-key",
            provider_id="openai",
            metadata={"replaces": old_key.id},
        )

        # Disable old key (revocation equivalent)
        await api_key_router.key_manager.update_key_state(
            key_id=old_key.id,
            new_state=KeyState.Disabled,
            reason="Rotated to new key",
        )

        # Verify old key is disabled
        disabled_key = await api_key_router.key_manager.get_key(old_key.id)
        assert disabled_key is not None
        assert disabled_key.state == KeyState.Disabled

        # Verify new key is available
        new_key_retrieved = await api_key_router.key_manager.get_key(new_key.id)
        assert new_key_retrieved is not None
        assert new_key_retrieved.state == KeyState.Available

        # Verify only new key is eligible
        eligible_keys = await api_key_router.key_manager.get_eligible_keys(
            provider_id="openai"
        )
        eligible_key_ids = [k.id for k in eligible_keys]
        assert new_key.id in eligible_key_ids
        assert old_key.id not in eligible_key_ids

    @pytest.mark.asyncio
    async def test_multiple_keys_same_provider(self, api_key_router):
        """Test registering multiple keys for same provider."""
        # Register provider

        adapter = MockProviderAdapter(provider_id="openai")
        await api_key_router.register_provider("openai", adapter)

        # Register multiple keys
        keys = []
        for i in range(5):
            key = await api_key_router.register_key(
                key_material=f"sk-test-key-{i}",
                provider_id="openai",
                metadata={"index": i},
            )
            keys.append(key)

        # Verify all keys were registered
        assert len(keys) == 5
        for key in keys:
            assert key.provider_id == "openai"
            assert key.state == KeyState.Available

        # Verify all keys are eligible
        eligible_keys = await api_key_router.key_manager.get_eligible_keys(
            provider_id="openai"
        )
        eligible_key_ids = [k.id for k in eligible_keys]
        for key in keys:
            assert key.id in eligible_key_ids

    @pytest.mark.asyncio
    async def test_key_usage_statistics_tracking(self, api_key_router):
        """Test key usage statistics tracking."""
        # Register provider and key

        adapter = MockProviderAdapter(provider_id="openai")
        await api_key_router.register_provider("openai", adapter)
        key = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )

        # Get initial statistics
        initial_key = await api_key_router.key_manager.get_key(key.id)
        initial_usage = initial_key.usage_count if initial_key else 0

        # Make a request
        from apikeyrouter.domain.models.request_intent import Message, RequestIntent

        request_intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Test")],
            parameters={"provider_id": "openai"},
        )
        await api_key_router.route(request_intent)

        # Verify usage statistics updated
        updated_key = await api_key_router.key_manager.get_key(key.id)
        assert updated_key is not None
        assert updated_key.usage_count > initial_usage
        assert updated_key.last_used_at is not None

    @pytest.mark.asyncio
    async def test_key_cooldown_management(self, api_key_router):
        """Test key cooldown management."""
        # Register provider and key

        adapter = MockProviderAdapter(provider_id="openai")
        await api_key_router.register_provider("openai", adapter)
        key = await api_key_router.register_key(
            key_material="sk-test-key-1", provider_id="openai"
        )

        # Set key to Throttled with cooldown (5 minutes = 300 seconds)
        await api_key_router.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Throttled,
            reason="Rate limit",
            cooldown_seconds=300,  # 5 minutes
        )

        # Verify key is in cooldown
        throttled_key = await api_key_router.key_manager.get_key(key.id)
        assert throttled_key is not None
        assert throttled_key.state == KeyState.Throttled
        assert throttled_key.cooldown_until is not None

        # Verify key is not eligible during cooldown
        eligible_keys = await api_key_router.key_manager.get_eligible_keys(
            provider_id="openai"
        )
        assert key.id not in [k.id for k in eligible_keys]

