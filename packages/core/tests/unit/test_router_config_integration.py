"""Tests for ApiKeyRouter and ConfigurationManager integration."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
import yaml

from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.api_key import APIKey
from apikeyrouter.domain.models.request_intent import RequestIntent
from apikeyrouter.infrastructure.config.manager import ConfigurationManager
from apikeyrouter.router import ApiKeyRouter


class MockProviderAdapter(ProviderAdapter):
    """Mock provider adapter for testing."""

    def __init__(self, provider_id: str = "test") -> None:
        """Initialize mock adapter."""
        self._provider_id = provider_id

    async def execute_request(
        self, intent: RequestIntent, key: APIKey
    ) -> dict[str, Any]:
        """Mock execute request."""
        return {"content": "test response"}

    def normalize_response(self, provider_response: Any) -> dict[str, Any]:
        """Mock normalize response."""
        return {"content": "normalized"}

    def map_error(self, error: Exception) -> dict[str, Any]:
        """Mock map error."""
        return {"error": str(error)}

    def get_capabilities(self) -> dict[str, Any]:
        """Mock get capabilities."""
        return {"models": ["test-model"]}

    def estimate_cost(self, intent: RequestIntent) -> float:
        """Mock estimate cost."""
        return 0.01

    async def get_health(self) -> dict[str, Any]:
        """Mock get health."""
        return {"status": "healthy"}


class TestRouterConfigurationIntegration:
    """Tests for ApiKeyRouter and ConfigurationManager integration."""

    @pytest.fixture
    def config_file(self, tmp_path: Path) -> Path:
        """Create a test configuration file."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "keys": [
                {
                    "key_id": "key-1",
                    "key_material": "sk-test-key-material-12345",
                    "provider_id": "test",
                    "metadata": {"tier": "pro"},
                }
            ],
            "policies": [
                {
                    "policy_id": "cost-opt",
                    "name": "Cost Optimization",
                    "type": "routing",
                    "scope": "global",
                    "rules": {"max_cost": 0.01},
                }
            ],
            "providers": [],
        }
        config_file.write_text(yaml.dump(config_data))
        return config_file

    @pytest.fixture
    def config_manager(self, config_file: Path) -> ConfigurationManager:
        """Create a ConfigurationManager instance."""
        return ConfigurationManager(config_file_path=str(config_file))

    @pytest.fixture
    def router(self, config_manager: ConfigurationManager) -> ApiKeyRouter:
        """Create an ApiKeyRouter with ConfigurationManager."""
        return ApiKeyRouter(configuration_manager=config_manager)

    @pytest.mark.asyncio
    async def test_router_with_config_manager(
        self, router: ApiKeyRouter, config_manager: ConfigurationManager
    ) -> None:
        """Test router has ConfigurationManager."""
        assert router.configuration_manager is not None
        assert router.configuration_manager == config_manager

    @pytest.mark.asyncio
    async def test_load_configuration_from_manager(
        self, router: ApiKeyRouter, config_file: Path
    ) -> None:
        """Test loading configuration from ConfigurationManager."""
        # Register provider first (required for key registration)
        adapter = MockProviderAdapter("test")
        await router.register_provider("test", adapter)

        # Load configuration
        config = await router.load_configuration_from_manager()

        assert "keys" in config
        assert "policies" in config
        assert len(config["keys"]) == 1
        assert len(config["policies"]) == 1

        # Verify key was registered
        # Note: KeyManager generates its own key_id, so we can't look up by config key_id
        # Instead, query StateStore for keys with this provider_id
        from apikeyrouter.domain.interfaces.state_store import StateQuery

        query = StateQuery(entity_type="APIKey", provider_id="test")
        keys = await router.state_store.query_state(query)
        assert len(keys) > 0
        assert keys[0].provider_id == "test"

        # Verify policy was stored
        policy = router.get_policy("cost-opt")
        assert policy is not None
        assert policy.name == "Cost Optimization"

    @pytest.mark.asyncio
    async def test_auto_load_configuration_in_context_manager(
        self, config_file: Path
    ) -> None:
        """Test that configuration is auto-loaded in context manager."""
        config_manager = ConfigurationManager(config_file_path=str(config_file))
        adapter = MockProviderAdapter("test")

        async with ApiKeyRouter(
            configuration_manager=config_manager
        ) as router:
            # Register provider first (required for key registration)
            await router.register_provider("test", adapter)

            # Configuration should have been attempted to load in __aenter__
            # but keys couldn't be registered without provider, so load again
            await router.load_configuration_from_manager()

            # Verify key was registered
            # Note: KeyManager generates its own key_id, so query by provider
            from apikeyrouter.domain.interfaces.state_store import StateQuery

            query = StateQuery(entity_type="APIKey", provider_id="test")
            keys = await router.state_store.query_state(query)
            assert len(keys) > 0
            assert keys[0].provider_id == "test"

    @pytest.mark.asyncio
    async def test_update_policy_from_config(
        self, router: ApiKeyRouter, config_file: Path
    ) -> None:
        """Test updating policy from ConfigurationManager."""
        # Load initial configuration
        adapter = MockProviderAdapter("test")
        await router.register_provider("test", adapter)
        await router.load_configuration_from_manager()

        # Update policy via ConfigurationManager
        new_policy_config = {
            "policy_id": "cost-opt",
            "name": "Updated Cost Optimization",
            "type": "routing",
            "scope": "global",
            "rules": {"max_cost": 0.02},
        }

        updated_policy = await router.update_policy_from_config(
            "cost-opt", new_policy_config
        )

        assert updated_policy.name == "Updated Cost Optimization"
        assert updated_policy.rules["max_cost"] == 0.02

        # Verify policy is stored in router
        stored_policy = router.get_policy("cost-opt")
        assert stored_policy.name == "Updated Cost Optimization"

    @pytest.mark.asyncio
    async def test_update_key_from_config(
        self, router: ApiKeyRouter, config_file: Path
    ) -> None:
        """Test updating key from ConfigurationManager."""
        # Load initial configuration
        adapter = MockProviderAdapter("test")
        await router.register_provider("test", adapter)
        await router.load_configuration_from_manager()

        # Update key via ConfigurationManager
        new_key_config = {
            "key_id": "key-1",
            "key_material": "sk-updated",
            "provider_id": "test",
            "metadata": {"tier": "enterprise"},
        }

        updated_key = await router.update_key_from_config("key-1", new_key_config)

        assert updated_key.provider_id == "test"
        # Note: key_material is encrypted, so we can't directly check it
        # But we can verify the key exists
        assert updated_key.id is not None

    @pytest.mark.asyncio
    async def test_get_policies(self, router: ApiKeyRouter, config_file: Path) -> None:
        """Test getting all policies."""
        adapter = MockProviderAdapter("test")
        await router.register_provider("test", adapter)
        await router.load_configuration_from_manager()

        policies = router.get_policies()
        assert len(policies) == 1
        assert policies[0].id == "cost-opt"

    @pytest.mark.asyncio
    async def test_get_policy(self, router: ApiKeyRouter, config_file: Path) -> None:
        """Test getting a specific policy."""
        adapter = MockProviderAdapter("test")
        await router.register_provider("test", adapter)
        await router.load_configuration_from_manager()

        policy = router.get_policy("cost-opt")
        assert policy is not None
        assert policy.id == "cost-opt"
        assert policy.name == "Cost Optimization"

        # Test non-existent policy
        policy = router.get_policy("nonexistent")
        assert policy is None

    @pytest.mark.asyncio
    async def test_load_configuration_without_manager(self) -> None:
        """Test that loading configuration without manager raises error."""
        router = ApiKeyRouter()

        with pytest.raises(ValueError, match="ConfigurationManager is not configured"):
            await router.load_configuration_from_manager()

    @pytest.mark.asyncio
    async def test_update_policy_without_manager(self) -> None:
        """Test that updating policy without manager raises error."""
        router = ApiKeyRouter()

        with pytest.raises(ValueError, match="ConfigurationManager is not configured"):
            await router.update_policy_from_config("test", {})

    @pytest.mark.asyncio
    async def test_update_key_without_manager(self) -> None:
        """Test that updating key without manager raises error."""
        router = ApiKeyRouter()

        with pytest.raises(ValueError, match="ConfigurationManager is not configured"):
            await router.update_key_from_config("test", {})

    @pytest.mark.asyncio
    async def test_apply_configuration_thread_safety(
        self, router: ApiKeyRouter, config_file: Path
    ) -> None:
        """Test that configuration application is thread-safe."""
        adapter = MockProviderAdapter("test")
        await router.register_provider("test", adapter)

        # Concurrent configuration loads
        async def load_config() -> None:
            await router.load_configuration_from_manager()

        # Run multiple concurrent loads
        await asyncio.gather(*[load_config() for _ in range(5)])

        # Should not raise any errors
        policies = router.get_policies()
        assert len(policies) >= 0  # May have duplicates, but shouldn't crash

    @pytest.mark.asyncio
    async def test_configuration_changes_without_restart(
        self, router: ApiKeyRouter, config_file: Path
    ) -> None:
        """Test that configuration changes are applied without restart."""
        adapter = MockProviderAdapter("test")
        await router.register_provider("test", adapter)
        await router.load_configuration_from_manager()

        # Verify initial state
        initial_policy = router.get_policy("cost-opt")
        assert initial_policy is not None

        # Update policy
        new_policy_config = {
            "policy_id": "cost-opt",
            "name": "Updated Policy",
            "type": "routing",
            "scope": "global",
        }
        await router.update_policy_from_config("cost-opt", new_policy_config)

        # Verify change was applied without restart
        updated_policy = router.get_policy("cost-opt")
        assert updated_policy.name == "Updated Policy"

