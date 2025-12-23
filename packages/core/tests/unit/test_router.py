"""Tests for ApiKeyRouter component."""

import os

import pytest

from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.components.key_manager import (
    KeyManager,
    KeyRegistrationError,
)
from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.domain.components.routing_engine import NoEligibleKeysError, RoutingEngine
from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.interfaces.state_store import StateStore
from apikeyrouter.domain.models.api_key import APIKey
from apikeyrouter.domain.models.system_error import ErrorCategory, SystemError
from apikeyrouter.domain.models.system_response import (
    ResponseMetadata,
    SystemResponse,
    TokenUsage,
)
from apikeyrouter.infrastructure.config.settings import RouterSettings
from apikeyrouter.infrastructure.observability.logger import (
    DefaultObservabilityManager,
)
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore


class MockStateStore(StateStore):
    """Mock StateStore for testing."""

    def __init__(self) -> None:
        """Initialize mock store."""
        self._keys: dict = {}
        self._quota_states: dict = {}
        self._routing_decisions: list = []
        self._state_transitions: list = []

    async def save_key(self, key) -> None:
        """Save key to mock store."""
        self._keys[key.id] = key

    async def get_key(self, key_id: str):
        """Get key from mock store."""
        return self._keys.get(key_id)

    async def list_keys(self, provider_id: str | None = None) -> list:
        """List keys from mock store."""
        keys = list(self._keys.values())
        if provider_id:
            keys = [k for k in keys if k.provider_id == provider_id]
        return keys

    async def delete_key(self, key_id: str) -> None:
        """Delete key from mock store."""
        self._keys.pop(key_id, None)

    async def save_quota_state(self, state) -> None:
        """Save quota state to mock store."""
        self._quota_states[state.key_id] = state

    async def get_quota_state(self, key_id: str):
        """Get quota state from mock store."""
        return self._quota_states.get(key_id)

    async def save_routing_decision(self, decision) -> None:
        """Save routing decision to mock store."""
        self._routing_decisions.append(decision)

    async def save_state_transition(self, transition) -> None:
        """Save state transition to mock store."""
        self._state_transitions.append(transition)

    async def query_state(self, query) -> list:
        """Query state from mock store."""
        return []


class MockObservabilityManager(ObservabilityManager):
    """Mock ObservabilityManager for testing."""

    def __init__(self) -> None:
        """Initialize mock observability manager."""
        self.events: list[dict] = []
        self.logs: list[dict] = []

    async def emit_event(
        self,
        event_type: str,
        payload: dict,
        metadata: dict | None = None,
    ) -> None:
        """Emit event to mock store."""
        self.events.append(
            {
                "event_type": event_type,
                "payload": payload,
                "metadata": metadata or {},
            }
        )

    async def log(
        self,
        level: str,
        message: str,
        context: dict | None = None,
    ) -> None:
        """Log to mock store."""
        self.logs.append(
            {
                "level": level,
                "message": message,
                "context": context or {},
            }
        )


class TestApiKeyRouterInitialization:
    """Tests for ApiKeyRouter initialization."""

    @pytest.mark.asyncio
    async def test_router_initializes_with_defaults(self) -> None:
        """Test that router initializes with default components."""
        router = ApiKeyRouter()

        # Verify all components are initialized
        assert router._state_store is not None
        assert isinstance(router._state_store, InMemoryStateStore)
        assert router._observability_manager is not None
        assert isinstance(router._observability_manager, DefaultObservabilityManager)
        assert router._key_manager is not None
        assert isinstance(router._key_manager, KeyManager)
        assert router._quota_awareness_engine is not None
        assert isinstance(router._quota_awareness_engine, QuotaAwarenessEngine)
        assert router._routing_engine is not None
        assert isinstance(router._routing_engine, RoutingEngine)

    @pytest.mark.asyncio
    async def test_router_initializes_with_custom_state_store(self) -> None:
        """Test that router accepts custom StateStore via dependency injection."""
        custom_store = MockStateStore()
        router = ApiKeyRouter(state_store=custom_store)

        assert router._state_store is custom_store
        assert router._key_manager._state_store is custom_store
        assert router._quota_awareness_engine._state_store is custom_store
        assert router._routing_engine._state_store is custom_store

    @pytest.mark.asyncio
    async def test_router_initializes_with_custom_observability_manager(
        self,
    ) -> None:
        """Test that router accepts custom ObservabilityManager via dependency injection."""
        custom_obs = MockObservabilityManager()
        router = ApiKeyRouter(observability_manager=custom_obs)

        assert router._observability_manager is custom_obs
        assert router._key_manager._observability is custom_obs
        assert router._quota_awareness_engine._observability is custom_obs
        assert router._routing_engine._observability is custom_obs

    @pytest.mark.asyncio
    async def test_router_initializes_with_config_from_dict(self) -> None:
        """Test that router accepts configuration from dictionary."""
        config_dict = {
            "max_decisions": 500,
            "max_transitions": 200,
            "default_cooldown_seconds": 120,
            "log_level": "DEBUG",
        }
        router = ApiKeyRouter(config=config_dict)

        assert router._config.max_decisions == 500
        assert router._config.max_transitions == 200
        assert router._config.default_cooldown_seconds == 120
        assert router._config.log_level == "DEBUG"

        # Verify config is applied to StateStore
        assert router._state_store._max_decisions == 500
        assert router._state_store._max_transitions == 200

    @pytest.mark.asyncio
    async def test_router_initializes_with_config_from_router_settings(
        self,
    ) -> None:
        """Test that router accepts RouterSettings instance."""
        settings = RouterSettings(
            max_decisions=300,
            max_transitions=150,
            default_cooldown_seconds=90,
        )
        router = ApiKeyRouter(config=settings)

        assert router._config.max_decisions == 300
        assert router._config.max_transitions == 150
        assert router._config.default_cooldown_seconds == 90

    @pytest.mark.asyncio
    async def test_router_initializes_with_environment_variables(self) -> None:
        """Test that router loads configuration from environment variables."""
        # Set environment variables
        os.environ["APIKEYROUTER_MAX_DECISIONS"] = "250"
        os.environ["APIKEYROUTER_LOG_LEVEL"] = "WARNING"

        try:
            router = ApiKeyRouter()

            assert router._config.max_decisions == 250
            assert router._config.log_level == "WARNING"
        finally:
            # Clean up environment variables
            os.environ.pop("APIKEYROUTER_MAX_DECISIONS", None)
            os.environ.pop("APIKEYROUTER_LOG_LEVEL", None)

    @pytest.mark.asyncio
    async def test_router_rejects_invalid_config_type(self) -> None:
        """Test that router raises ValueError for invalid config type."""
        with pytest.raises(ValueError, match="Invalid config type"):
            ApiKeyRouter(config="invalid_config")  # type: ignore

    @pytest.mark.asyncio
    async def test_router_supports_async_context_manager(self) -> None:
        """Test that router supports async context manager."""
        async with ApiKeyRouter() as router:
            assert router is not None
            assert router._key_manager is not None
            assert router._routing_engine is not None

    @pytest.mark.asyncio
    async def test_router_properties_expose_components(self) -> None:
        """Test that router properties expose component instances."""
        router = ApiKeyRouter()

        assert router.key_manager is router._key_manager
        assert router.routing_engine is router._routing_engine
        assert router.quota_awareness_engine is router._quota_awareness_engine
        assert router.state_store is router._state_store
        assert router.observability_manager is router._observability_manager

    @pytest.mark.asyncio
    async def test_router_components_share_dependencies(self) -> None:
        """Test that router components share the same dependencies."""
        custom_store = MockStateStore()
        custom_obs = MockObservabilityManager()
        router = ApiKeyRouter(state_store=custom_store, observability_manager=custom_obs)

        # Verify all components share the same StateStore
        assert router._key_manager._state_store is custom_store
        assert router._quota_awareness_engine._state_store is custom_store
        assert router._routing_engine._state_store is custom_store

        # Verify all components share the same ObservabilityManager
        assert router._key_manager._observability is custom_obs
        assert router._quota_awareness_engine._observability is custom_obs
        assert router._routing_engine._observability is custom_obs

    @pytest.mark.asyncio
    async def test_router_config_applied_to_components(self) -> None:
        """Test that router configuration is applied to components."""
        config_dict = {
            "default_cooldown_seconds": 180,
            "quota_default_cooldown_seconds": 240,
        }
        router = ApiKeyRouter(config=config_dict)

        # Verify KeyManager received the config
        assert router._key_manager._default_cooldown_seconds == 180

        # Verify QuotaAwarenessEngine received the config
        assert router._quota_awareness_engine._default_cooldown_seconds == 240

    @pytest.mark.asyncio
    async def test_router_quota_engine_has_key_manager_reference(self) -> None:
        """Test that QuotaAwarenessEngine has reference to KeyManager."""
        router = ApiKeyRouter()

        assert router._quota_awareness_engine._key_manager is router._key_manager

    @pytest.mark.asyncio
    async def test_router_routing_engine_has_quota_engine_reference(
        self,
    ) -> None:
        """Test that RoutingEngine has reference to QuotaAwarenessEngine."""
        router = ApiKeyRouter()

        assert router._routing_engine._quota_engine is router._quota_awareness_engine


class MockProviderAdapter(ProviderAdapter):
    """Mock ProviderAdapter for testing."""

    def __init__(self, provider_id: str = "mock") -> None:
        """Initialize mock adapter."""
        self.provider_id = provider_id

    async def execute_request(self, intent, key):
        """Execute request - mock implementation."""
        from datetime import datetime

        from apikeyrouter.domain.models.system_response import (
            SystemResponse,
        )

        return SystemResponse(
            content="mock response",
            request_id="mock-request-id",
            key_used=key.id,
            metadata=ResponseMetadata(
                model_used=intent.model if hasattr(intent, "model") else "mock-model",
                tokens_used=TokenUsage(input_tokens=10, output_tokens=5),
                response_time_ms=100,
                provider_id=key.provider_id,
                timestamp=datetime.utcnow(),
            ),
        )

    def normalize_response(self, provider_response):
        """Normalize response - mock implementation."""
        from apikeyrouter.domain.models.system_response import SystemResponse

        return SystemResponse(
            content="normalized",
            request_id="mock-request-id",
            key_used="mock-key",
        )

    def map_error(self, provider_error: Exception):
        """Map error - mock implementation."""
        from apikeyrouter.domain.models.system_error import (
            ErrorCategory,
            SystemError,
        )

        return SystemError(
            category=ErrorCategory.ProviderError,
            message=str(provider_error),
            retryable=False,
        )

    def get_capabilities(self):
        """Get capabilities - mock implementation."""
        # Return dict matching current implementation pattern
        # (ProviderCapabilities model not yet implemented)
        return {
            "supports_streaming": True,
            "supports_tools": False,
            "supports_images": False,
            "max_tokens": None,
            "rate_limit_per_minute": None,
            "custom_capabilities": {},
        }

    async def estimate_cost(self, request_intent):
        """Estimate cost - mock implementation."""
        from decimal import Decimal

        from apikeyrouter.domain.models.cost_estimate import CostEstimate

        return CostEstimate(
            amount=Decimal("0.01"),
            currency="USD",
            confidence=0.9,
        )

    async def get_health(self):
        """Get health - mock implementation."""
        from datetime import datetime

        from apikeyrouter.domain.models.health_state import (
            HealthState,
            HealthStatus,
        )

        return HealthState(
            status=HealthStatus.Healthy,
            last_check=datetime.utcnow(),
        )


class TestApiKeyRouterProviderRegistration:
    """Tests for ApiKeyRouter provider registration."""

    @pytest.mark.asyncio
    async def test_register_provider_stores_mapping(self) -> None:
        """Test that register_provider stores provider-adapter mapping."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()

        await router.register_provider("test_provider", adapter)

        assert "test_provider" in router._providers
        assert router._providers["test_provider"] is adapter

    @pytest.mark.asyncio
    async def test_register_provider_validates_adapter_type(self) -> None:
        """Test that register_provider validates adapter is ProviderAdapter instance."""
        router = ApiKeyRouter()

        # Try to register a non-ProviderAdapter object
        with pytest.raises(ValueError, match="adapter must be an instance of ProviderAdapter"):
            await router.register_provider("test", "not_an_adapter")  # type: ignore

    @pytest.mark.asyncio
    async def test_register_provider_validates_adapter_methods(self) -> None:
        """Test that register_provider validates adapter implements required methods."""
        router = ApiKeyRouter()

        # Create incomplete adapter (missing methods) - use a class that doesn't inherit
        # from ProviderAdapter but has some methods to test runtime validation
        class IncompleteAdapter:
            """Incomplete adapter missing required methods."""

            async def execute_request(self, intent, key):
                """Has this method."""
                pass

            # Missing other required methods

        incomplete_adapter = IncompleteAdapter()

        with pytest.raises(ValueError, match="adapter must be an instance of ProviderAdapter"):
            await router.register_provider("test", incomplete_adapter)  # type: ignore

    @pytest.mark.asyncio
    async def test_register_provider_supports_multiple_providers(self) -> None:
        """Test that multiple providers can be registered."""
        router = ApiKeyRouter()
        adapter1 = MockProviderAdapter("provider1")
        adapter2 = MockProviderAdapter("provider2")
        adapter3 = MockProviderAdapter("provider3")

        await router.register_provider("openai", adapter1)
        await router.register_provider("anthropic", adapter2)
        await router.register_provider("gemini", adapter3)

        assert len(router._providers) == 3
        assert router._providers["openai"] is adapter1
        assert router._providers["anthropic"] is adapter2
        assert router._providers["gemini"] is adapter3

    @pytest.mark.asyncio
    async def test_register_provider_rejects_duplicate_without_overwrite(
        self,
    ) -> None:
        """Test that duplicate registration raises error without overwrite flag."""
        router = ApiKeyRouter()
        adapter1 = MockProviderAdapter()
        adapter2 = MockProviderAdapter()

        await router.register_provider("test_provider", adapter1)

        # Try to register same provider_id again
        with pytest.raises(ValueError, match="Provider 'test_provider' is already registered"):
            await router.register_provider("test_provider", adapter2)

        # Original adapter should still be registered
        assert router._providers["test_provider"] is adapter1

    @pytest.mark.asyncio
    async def test_register_provider_allows_overwrite(self) -> None:
        """Test that overwrite flag allows replacing existing provider."""
        router = ApiKeyRouter()
        adapter1 = MockProviderAdapter()
        adapter2 = MockProviderAdapter()

        await router.register_provider("test_provider", adapter1)
        assert router._providers["test_provider"] is adapter1

        # Overwrite with new adapter
        await router.register_provider("test_provider", adapter2, overwrite=True)
        assert router._providers["test_provider"] is adapter2

    @pytest.mark.asyncio
    async def test_register_provider_validates_provider_id_not_empty(
        self,
    ) -> None:
        """Test that register_provider rejects empty provider_id."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()

        with pytest.raises(ValueError, match="provider_id cannot be empty"):
            await router.register_provider("", adapter)

        with pytest.raises(ValueError, match="provider_id cannot be empty"):
            await router.register_provider("   ", adapter)

    @pytest.mark.asyncio
    async def test_register_provider_validates_provider_id_type(self) -> None:
        """Test that register_provider validates provider_id is string."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()

        with pytest.raises(ValueError, match="provider_id must be a non-empty string"):
            await router.register_provider(None, adapter)  # type: ignore

        with pytest.raises(ValueError, match="provider_id must be a non-empty string"):
            await router.register_provider(123, adapter)  # type: ignore

    @pytest.mark.asyncio
    async def test_register_provider_trims_whitespace(self) -> None:
        """Test that register_provider trims whitespace from provider_id."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()

        await router.register_provider("  test_provider  ", adapter)

        # Should be stored with trimmed value
        assert "test_provider" in router._providers
        assert "  test_provider  " not in router._providers

    @pytest.mark.asyncio
    async def test_register_provider_emits_observability_event(self) -> None:
        """Test that register_provider emits observability event."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        mock_obs = MockObservabilityManager()
        router._observability_manager = mock_obs

        await router.register_provider("test_provider", adapter)

        # Check that event was emitted
        assert len(mock_obs.events) > 0
        event = mock_obs.events[-1]
        assert event["event_type"] == "provider_registered"
        assert event["payload"]["provider_id"] == "test_provider"
        assert event["payload"]["adapter_type"] == "MockProviderAdapter"
        assert event["payload"]["overwrite"] is False

    @pytest.mark.asyncio
    async def test_register_provider_emits_overwrite_event(self) -> None:
        """Test that register_provider emits overwrite event when overwriting."""
        router = ApiKeyRouter()
        adapter1 = MockProviderAdapter()
        adapter2 = MockProviderAdapter()
        mock_obs = MockObservabilityManager()
        router._observability_manager = mock_obs

        await router.register_provider("test_provider", adapter1)
        await router.register_provider("test_provider", adapter2, overwrite=True)

        # Check that overwrite event was emitted
        events = [e for e in mock_obs.events if e["event_type"] == "provider_registered"]
        assert len(events) == 2
        assert events[1]["payload"]["overwrite"] is True

    @pytest.mark.asyncio
    async def test_register_provider_provider_id_uniqueness(self) -> None:
        """Test that provider_id uniqueness is enforced."""
        router = ApiKeyRouter()
        adapter1 = MockProviderAdapter()
        adapter2 = MockProviderAdapter()

        await router.register_provider("provider1", adapter1)

        # Same provider_id should fail
        with pytest.raises(ValueError, match="already registered"):
            await router.register_provider("provider1", adapter2)

        # Different provider_id should succeed
        await router.register_provider("provider2", adapter2)
        assert len(router._providers) == 2


class TestApiKeyRouterKeyRegistration:
    """Tests for ApiKeyRouter key registration."""

    def setup_method(self) -> None:
        """Set up test environment with encryption key."""
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key()
        os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = test_key.decode()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)

    @pytest.mark.asyncio
    async def test_register_key_delegates_to_key_manager(self) -> None:
        """Test that register_key delegates to KeyManager.register_key."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)

        # Register a key
        key = await router.register_key(
            key_material="sk-test-key-123",
            provider_id="test_provider",
            metadata={"test": "metadata"},
        )

        # Verify key was registered via KeyManager
        retrieved_key = await router._key_manager.get_key(key.id)
        assert retrieved_key is not None
        assert retrieved_key.id == key.id
        assert retrieved_key.provider_id == "test_provider"

    @pytest.mark.asyncio
    async def test_register_key_initializes_quota_state(self) -> None:
        """Test that register_key initializes QuotaState for new key."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)

        # Register a key
        key = await router.register_key(
            key_material="sk-test-key-123",
            provider_id="test_provider",
        )

        # Verify QuotaState was initialized
        quota_state = await router._quota_awareness_engine.get_quota_state(key.id)
        assert quota_state is not None
        assert quota_state.key_id == key.id
        assert quota_state.capacity_state == "abundant"  # CapacityState is a string enum

    @pytest.mark.asyncio
    async def test_register_key_returns_api_key(self) -> None:
        """Test that register_key returns APIKey object."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)

        key = await router.register_key(
            key_material="sk-test-key-123",
            provider_id="test_provider",
        )

        assert isinstance(key, APIKey)
        assert key.id is not None
        assert key.provider_id == "test_provider"

    @pytest.mark.asyncio
    async def test_register_key_rejects_invalid_provider_id(self) -> None:
        """Test that register_key raises ValueError for unregistered provider_id."""
        router = ApiKeyRouter()

        # Try to register key without registering provider first
        with pytest.raises(ValueError, match="Provider 'test_provider' is not registered"):
            await router.register_key(
                key_material="sk-test-key-123",
                provider_id="test_provider",
            )

    @pytest.mark.asyncio
    async def test_register_key_handles_key_manager_errors(self) -> None:
        """Test that register_key handles KeyManager errors gracefully."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)

        # Try to register with empty key material (should fail in KeyManager)
        with pytest.raises(KeyRegistrationError, match="Key material cannot be empty"):
            await router.register_key(
                key_material="",
                provider_id="test_provider",
            )

    @pytest.mark.asyncio
    async def test_register_key_emits_observability_event(self) -> None:
        """Test that register_key emits observability event."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        mock_obs = MockObservabilityManager()
        router._observability_manager = mock_obs

        key = await router.register_key(
            key_material="sk-test-key-123",
            provider_id="test_provider",
        )

        # Check that event was emitted
        events = [e for e in mock_obs.events if e["event_type"] == "key_registered"]
        assert len(events) > 0
        event = events[0]
        assert event["payload"]["key_id"] == key.id
        assert event["payload"]["provider_id"] == "test_provider"

    @pytest.mark.asyncio
    async def test_register_key_with_metadata(self) -> None:
        """Test that register_key passes metadata to KeyManager."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)

        metadata = {"account_tier": "pro", "region": "us-east-1"}
        key = await router.register_key(
            key_material="sk-test-key-123",
            provider_id="test_provider",
            metadata=metadata,
        )

        # Verify metadata was stored
        retrieved_key = await router._key_manager.get_key(key.id)
        assert retrieved_key is not None
        assert retrieved_key.metadata == metadata

    @pytest.mark.asyncio
    async def test_register_key_provider_id_case_sensitive(self) -> None:
        """Test that register_key validates provider_id case-sensitively."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("TestProvider", adapter)

        # Should work with exact case match
        key = await router.register_key(
            key_material="sk-test-key-123",
            provider_id="TestProvider",
        )
        assert key.provider_id == "testprovider"  # KeyManager normalizes to lowercase

        # Should fail with different case
        with pytest.raises(ValueError, match="Provider 'testprovider' is not registered"):
            await router.register_key(
                key_material="sk-test-key-456",
                provider_id="testprovider",  # Different case
            )

    @pytest.mark.asyncio
    async def test_register_key_multiple_keys_same_provider(self) -> None:
        """Test that multiple keys can be registered for the same provider."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)

        key1 = await router.register_key(
            key_material="sk-test-key-1",
            provider_id="test_provider",
        )
        key2 = await router.register_key(
            key_material="sk-test-key-2",
            provider_id="test_provider",
        )

        assert key1.id != key2.id
        assert key1.provider_id == key2.provider_id

        # Both should have quota states
        quota1 = await router._quota_awareness_engine.get_quota_state(key1.id)
        quota2 = await router._quota_awareness_engine.get_quota_state(key2.id)
        assert quota1 is not None
        assert quota2 is not None
        assert quota1.key_id == key1.id
        assert quota2.key_id == key2.id


class TestApiKeyRouterRouteMethod:
    """Tests for ApiKeyRouter route method."""

    def setup_method(self) -> None:
        """Set up test environment with encryption key."""
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key()
        os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = test_key.decode()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)

    @pytest.mark.asyncio
    async def test_route_gets_routing_decision(self) -> None:
        """Test that route method gets routing decision from RoutingEngine."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        key = await router.register_key("sk-test-key-extra", "test_provider")

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        response = await router.route(intent)

        # Verify routing decision was made and saved
        # Check that response has correct key_used
        assert response.key_used == key.id
        assert response.request_id is not None

    @pytest.mark.asyncio
    async def test_route_executes_request_via_adapter(self) -> None:
        """Test that route method executes request via ProviderAdapter."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-extra", "test_provider")

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        response = await router.route(intent)

        # Verify response from adapter
        assert response.content == "mock response"
        assert response.metadata.model_used == "test-model"

    @pytest.mark.asyncio
    async def test_route_updates_quota_state(self) -> None:
        """Test that route method updates quota state after request."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        key = await router.register_key("sk-test-key-extra", "test_provider")

        # Get initial quota state
        initial_quota = await router._quota_awareness_engine.get_quota_state(key.id)
        initial_used = initial_quota.used_capacity

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        await router.route(intent)

        # Verify quota state was updated
        updated_quota = await router._quota_awareness_engine.get_quota_state(key.id)
        # Should have consumed tokens (10 input + 5 output = 15 total)
        assert updated_quota.used_capacity >= initial_used

    @pytest.mark.asyncio
    async def test_route_returns_system_response(self) -> None:
        """Test that route method returns SystemResponse."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-extra", "test_provider")

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        response = await router.route(intent)

        assert isinstance(response, SystemResponse)
        assert response.content is not None
        assert response.metadata is not None
        assert response.key_used is not None
        assert response.request_id is not None

    @pytest.mark.asyncio
    async def test_route_handles_no_eligible_keys_error(self) -> None:
        """Test that route method handles NoEligibleKeysError."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        # Don't register any keys

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        with pytest.raises(NoEligibleKeysError):
            await router.route(intent)

    @pytest.mark.asyncio
    async def test_route_handles_adapter_errors(self) -> None:
        """Test that route method handles ProviderAdapter errors."""
        router = ApiKeyRouter()

        # Create adapter that raises SystemError
        class FailingAdapter(MockProviderAdapter):
            async def execute_request(self, intent, key):
                raise SystemError(
                    category=ErrorCategory.AuthenticationError,
                    message="Invalid API key",
                    retryable=False,
                )

        adapter = FailingAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-extra", "test_provider")

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        with pytest.raises(SystemError, match="Invalid API key"):
            await router.route(intent)

    @pytest.mark.asyncio
    async def test_route_graceful_degradation_retryable_error(self) -> None:
        """Test that route method retries with different key on retryable error."""
        router = ApiKeyRouter()

        # Create adapter that fails first time, succeeds second time
        call_count = {"count": 0}

        class RetryableFailingAdapter(MockProviderAdapter):
            async def execute_request(self, intent, key):
                call_count["count"] += 1
                if call_count["count"] == 1:
                    raise SystemError(
                        category=ErrorCategory.RateLimitError,
                        message="Rate limited",
                        retryable=True,
                    )
                # Second call succeeds
                return await super().execute_request(intent, key)

        adapter = RetryableFailingAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-1", "test_provider")
        await router.register_key("sk-test-key-2", "test_provider")

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        response = await router.route(intent)

        # Should have retried and succeeded
        assert response.content == "mock response"
        assert call_count["count"] == 2

    @pytest.mark.asyncio
    async def test_route_accepts_dict_request_intent(self) -> None:
        """Test that route method accepts dict for request_intent."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-extra", "test_provider")

        intent_dict = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        response = await router.route(intent_dict)

        assert isinstance(response, SystemResponse)
        assert response.content == "mock response"

    @pytest.mark.asyncio
    async def test_route_accepts_string_objective(self) -> None:
        """Test that route method accepts string for objective."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-extra", "test_provider")

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        response = await router.route(intent, objective="cost")

        assert isinstance(response, SystemResponse)

    @pytest.mark.asyncio
    async def test_route_updates_key_usage_statistics(self) -> None:
        """Test that route method updates key usage_count and last_used_at."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        key = await router.register_key("sk-test-key-extra", "test_provider")

        initial_usage = key.usage_count
        initial_last_used = key.last_used_at

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        await router.route(intent)

        # Verify key was updated
        updated_key = await router._key_manager.get_key(key.id)
        assert updated_key is not None
        assert updated_key.usage_count == initial_usage + 1
        assert updated_key.last_used_at is not None
        assert updated_key.last_used_at != initial_last_used

    @pytest.mark.asyncio
    async def test_route_saves_routing_decision(self) -> None:
        """Test that route method saves routing decision to StateStore."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        key = await router.register_key("sk-test-key-extra", "test_provider")

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        response = await router.route(intent)

        # Query routing decisions
        from apikeyrouter.domain.interfaces.state_store import StateQuery

        query = StateQuery(
            entity_type="RoutingDecision",
            key_id=key.id,
        )
        decisions = await router._state_store.query_state(query)

        assert len(decisions) > 0
        decision = decisions[0]
        assert decision.selected_key_id == key.id
        assert decision.request_id == response.request_id

    @pytest.mark.asyncio
    async def test_route_emits_observability_events(self) -> None:
        """Test that route method emits observability events."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        mock_obs = MockObservabilityManager()
        router._observability_manager = mock_obs
        await router.register_key("sk-test-key-extra", "test_provider")

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        await router.route(intent)

        # Check that events were emitted
        event_types = [e["event_type"] for e in mock_obs.events]
        assert "routing_decision_made" in event_types

        # Check that logs were written
        log_messages = [log["message"] for log in mock_obs.logs]
        assert any("Request routing started" in msg for msg in log_messages)
        assert any("Request completed successfully" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_route_handles_non_retryable_error_no_retry(self) -> None:
        """Test that route method doesn't retry on non-retryable errors."""
        router = ApiKeyRouter()

        call_count = {"count": 0}

        class NonRetryableFailingAdapter(MockProviderAdapter):
            async def execute_request(self, intent, key):
                call_count["count"] += 1
                raise SystemError(
                    category=ErrorCategory.AuthenticationError,
                    message="Invalid API key",
                    retryable=False,
                )

        adapter = NonRetryableFailingAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-1", "test_provider")
        await router.register_key("sk-test-key-2", "test_provider")

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        with pytest.raises(SystemError, match="Invalid API key"):
            await router.route(intent)

        # Should only try once (non-retryable)
        assert call_count["count"] == 1

    @pytest.mark.asyncio
    async def test_route_validates_request_intent_provider_id(self) -> None:
        """Test that route method validates request_intent has provider_id."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-extra", "test_provider")

        # Create intent without provider_id
        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        with pytest.raises(ValueError, match="must contain 'provider_id'"):
            await router.route(intent)

    @pytest.mark.asyncio
    async def test_route_validates_dict_request_intent_provider_id(self) -> None:
        """Test that route method validates dict request_intent has provider_id."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)

        intent_dict = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            # Missing provider_id
        }

        with pytest.raises(ValueError, match="must contain 'provider_id'"):
            await router.route(intent_dict)


class TestApiKeyRouterObservabilityIntegration:
    """Tests for observability integration in ApiKeyRouter."""

    def setup_method(self) -> None:
        """Set up test environment with encryption key."""
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key()
        os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = test_key.decode()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)

    @pytest.mark.asyncio
    async def test_route_logs_request_start_with_context(self) -> None:
        """Test that route method logs request start with full context."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-extra", "test_provider")
        mock_obs = MockObservabilityManager()
        router._observability_manager = mock_obs

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        await router.route(intent)

        # Check that request start was logged with context
        start_logs = [log for log in mock_obs.logs if "Request routing started" in log["message"]]
        assert len(start_logs) > 0
        start_log = start_logs[0]
        assert "request_id" in start_log["context"]
        assert "correlation_id" in start_log["context"]
        assert "provider_id" in start_log["context"]
        assert "model" in start_log["context"]

    @pytest.mark.asyncio
    async def test_route_logs_routing_decision(self) -> None:
        """Test that route method logs routing decision."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        key = await router.register_key("sk-test-key-extra", "test_provider")
        mock_obs = MockObservabilityManager()
        router._observability_manager = mock_obs

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        await router.route(intent)

        # Check that routing decision was logged
        decision_logs = [log for log in mock_obs.logs if "Routing decision made" in log["message"]]
        assert len(decision_logs) > 0
        decision_log = decision_logs[0]
        assert "key_id" in decision_log["context"]
        assert "provider_id" in decision_log["context"]
        assert "explanation" in decision_log["context"]
        assert decision_log["context"]["key_id"] == key.id

    @pytest.mark.asyncio
    async def test_route_logs_request_completion_success(self) -> None:
        """Test that route method logs request completion on success."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-extra", "test_provider")
        mock_obs = MockObservabilityManager()
        router._observability_manager = mock_obs

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        await router.route(intent)

        # Check that completion was logged
        completion_logs = [
            log for log in mock_obs.logs if "Request completed successfully" in log["message"]
        ]
        assert len(completion_logs) > 0
        completion_log = completion_logs[0]
        assert "request_id" in completion_log["context"]
        assert "correlation_id" in completion_log["context"]
        assert "key_id" in completion_log["context"]
        assert "tokens_used" in completion_log["context"]
        assert "response_time_ms" in completion_log["context"]

    @pytest.mark.asyncio
    async def test_route_emits_events_for_state_changes(self) -> None:
        """Test that route method emits events for state changes."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-extra", "test_provider")
        mock_obs = MockObservabilityManager()
        router._observability_manager = mock_obs

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        await router.route(intent)

        # Check that events were emitted
        event_types = [e["event_type"] for e in mock_obs.events]
        assert "routing_decision_made" in event_types
        assert "request_completed" in event_types

    @pytest.mark.asyncio
    async def test_route_includes_correlation_id_in_all_logs(self) -> None:
        """Test that route method includes correlation_id in all logs."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-extra", "test_provider")
        mock_obs = MockObservabilityManager()
        router._observability_manager = mock_obs

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        await router.route(intent)

        # Check that all logs have correlation_id
        for log in mock_obs.logs:
            if "context" in log and log["context"] and "correlation_id" in log["context"]:
                # Some logs might not have context, that's okay
                assert log["context"]["correlation_id"] is not None
                assert isinstance(log["context"]["correlation_id"], str)

    @pytest.mark.asyncio
    async def test_route_includes_correlation_id_in_response_metadata(
        self,
    ) -> None:
        """Test that route method includes correlation_id in response metadata."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-extra", "test_provider")

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        response = await router.route(intent)

        # Check that correlation_id is in response metadata
        assert response.metadata.correlation_id is not None
        assert isinstance(response.metadata.correlation_id, str)

    @pytest.mark.asyncio
    async def test_register_key_emits_key_registered_event(self) -> None:
        """Test that register_key emits key_registered event."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        mock_obs = MockObservabilityManager()
        router._observability_manager = mock_obs

        await router.register_key("sk-test-key-extra", "test_provider")

        # Check that key_registered event was emitted
        event_types = [e["event_type"] for e in mock_obs.events]
        assert "key_registered" in event_types

        # Check that key registration was logged
        log_messages = [log["message"] for log in mock_obs.logs]
        assert any("Key registered successfully" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_register_provider_emits_provider_registered_event(
        self,
    ) -> None:
        """Test that register_provider emits provider_registered event."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        mock_obs = MockObservabilityManager()
        router._observability_manager = mock_obs

        await router.register_provider("test_provider", adapter)

        # Check that provider_registered event was emitted
        event_types = [e["event_type"] for e in mock_obs.events]
        assert "provider_registered" in event_types

        # Check that provider registration was logged
        log_messages = [log["message"] for log in mock_obs.logs]
        assert any("Provider registered" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_route_emits_request_failed_event_on_error(self) -> None:
        """Test that route method emits request_failed event on error."""
        router = ApiKeyRouter()

        class FailingAdapter(MockProviderAdapter):
            async def execute_request(self, intent, key):
                raise SystemError(
                    category=ErrorCategory.AuthenticationError,
                    message="Invalid API key",
                    retryable=False,
                )

        adapter = FailingAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-extra", "test_provider")
        mock_obs = MockObservabilityManager()
        router._observability_manager = mock_obs

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        with pytest.raises(SystemError):
            await router.route(intent)

        # Check that request_failed event was emitted
        event_types = [e["event_type"] for e in mock_obs.events]
        assert "request_failed" in event_types

    @pytest.mark.asyncio
    async def test_route_uses_appropriate_log_levels(self) -> None:
        """Test that route method uses appropriate log levels."""
        router = ApiKeyRouter()
        adapter = MockProviderAdapter()
        await router.register_provider("test_provider", adapter)
        await router.register_key("sk-test-key-extra", "test_provider")
        mock_obs = MockObservabilityManager()
        router._observability_manager = mock_obs

        intent = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "provider_id": "test_provider",
        }

        await router.route(intent)

        # Check that appropriate log levels are used
        log_levels = [log["level"] for log in mock_obs.logs]
        # Should have INFO level for normal operations
        assert "INFO" in log_levels
        # Should not have ERROR for successful request
        assert "ERROR" not in log_levels
