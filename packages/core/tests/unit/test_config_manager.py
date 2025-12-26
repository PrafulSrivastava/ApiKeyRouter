"""Tests for configuration manager."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
import yaml

from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.infrastructure.config.file_loader import ConfigurationError
from apikeyrouter.infrastructure.config.manager import ConfigurationManager


class MockObservabilityManager(ObservabilityManager):
    """Mock ObservabilityManager for testing."""

    def __init__(self) -> None:
        """Initialize mock observability manager."""
        self.events: list[dict[str, Any]] = []
        self.logs: list[dict[str, Any]] = []

    async def emit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record emitted event."""
        self.events.append({
            "event_type": event_type,
            "payload": payload,
            "metadata": metadata or {},
        })

    async def log(
        self,
        level: str,
        message: str,
        context: dict[str, any] | None = None,
    ) -> None:
        """Record log message."""
        self.logs.append({
            "level": level,
            "message": message,
            "context": context or {},
        })


class TestConfigurationManager:
    """Tests for ConfigurationManager."""

    @pytest.fixture
    def config_file(self, tmp_path: Path) -> Path:
        """Create a test configuration file."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "keys": [
                {
                    "key_id": "key-1",
                    "key_material": "sk-test-1",
                    "provider_id": "openai",
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
            "providers": [
                {
                    "provider_id": "openai",
                    "adapter_type": "OpenAIAdapter",
                    "config": {"base_url": "https://api.openai.com/v1"},
                }
            ],
        }
        config_file.write_text(yaml.dump(config_data))
        return config_file

    @pytest.fixture
    def observability_manager(self) -> MockObservabilityManager:
        """Create a mock observability manager."""
        return MockObservabilityManager()

    @pytest.mark.asyncio
    async def test_load_configuration(self, config_file: Path) -> None:
        """Test loading configuration from file."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        config = await manager.load_configuration()

        assert "keys" in config
        assert "policies" in config
        assert "providers" in config
        assert len(config["keys"]) == 1
        assert len(config["policies"]) == 1
        assert len(config["providers"]) == 1

    @pytest.mark.asyncio
    async def test_load_configuration_emits_event(
        self, config_file: Path, observability_manager: MockObservabilityManager
    ) -> None:
        """Test that loading configuration emits event."""
        manager = ConfigurationManager(
            config_file_path=str(config_file),
            observability_manager=observability_manager,
        )
        await manager.load_configuration()

        assert len(observability_manager.events) == 1
        assert observability_manager.events[0]["event_type"] == "configuration_loaded"
        assert "version" in observability_manager.events[0]["payload"]

    @pytest.mark.asyncio
    async def test_reload_configuration(self, config_file: Path) -> None:
        """Test reloading configuration."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        await manager.load_configuration()

        # Modify config file
        config_data = {
            "keys": [
                {
                    "key_id": "key-2",
                    "key_material": "sk-test-2",
                    "provider_id": "anthropic",
                }
            ],
            "policies": [],
            "providers": [],
        }
        config_file.write_text(yaml.dump(config_data))

        # Reload
        config = await manager.reload_configuration()
        assert len(config["keys"]) == 1
        assert config["keys"][0]["key_id"] == "key-2"

    @pytest.mark.asyncio
    async def test_update_policy(self, config_file: Path) -> None:
        """Test updating a policy."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        await manager.load_configuration()

        new_policy = {
            "policy_id": "cost-opt",
            "name": "Updated Cost Optimization",
            "type": "routing",
            "scope": "global",
            "rules": {"max_cost": 0.02},
        }

        updated = await manager.update_policy("cost-opt", new_policy)
        assert updated["name"] == "Updated Cost Optimization"
        assert updated["rules"]["max_cost"] == 0.02

        # Verify it's in current configuration
        current = manager.get_current_configuration()
        assert current["policies"][0]["name"] == "Updated Cost Optimization"

    @pytest.mark.asyncio
    async def test_update_policy_emits_event(
        self, config_file: Path, observability_manager: MockObservabilityManager
    ) -> None:
        """Test that updating policy emits event."""
        manager = ConfigurationManager(
            config_file_path=str(config_file),
            observability_manager=observability_manager,
        )
        await manager.load_configuration()

        new_policy = {
            "policy_id": "cost-opt",
            "name": "Updated Policy",
            "type": "routing",
            "scope": "global",
        }
        await manager.update_policy("cost-opt", new_policy)

        # Should have 2 events: load and update
        assert len(observability_manager.events) == 2
        assert observability_manager.events[1]["event_type"] == "policy_updated"

    @pytest.mark.asyncio
    async def test_update_policy_invalid(self, config_file: Path) -> None:
        """Test updating policy with invalid configuration."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        await manager.load_configuration()

        invalid_policy = {
            "policy_id": "cost-opt",
            "name": "Invalid",
            # Missing required fields: type, scope
        }

        with pytest.raises(ConfigurationError, match="missing required field"):
            await manager.update_policy("cost-opt", invalid_policy)

    @pytest.mark.asyncio
    async def test_update_key_config(self, config_file: Path) -> None:
        """Test updating a key configuration."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        await manager.load_configuration()

        new_key = {
            "key_id": "key-1",
            "key_material": "sk-updated",
            "provider_id": "openai",
            "metadata": {"tier": "enterprise"},
        }

        updated = await manager.update_key_config("key-1", new_key)
        assert updated["key_material"] == "sk-updated"
        assert updated["metadata"]["tier"] == "enterprise"

    @pytest.mark.asyncio
    async def test_update_key_config_emits_event(
        self, config_file: Path, observability_manager: MockObservabilityManager
    ) -> None:
        """Test that updating key config emits event."""
        manager = ConfigurationManager(
            config_file_path=str(config_file),
            observability_manager=observability_manager,
        )
        await manager.load_configuration()

        new_key = {
            "key_id": "key-1",
            "key_material": "sk-updated",
            "provider_id": "openai",
        }
        await manager.update_key_config("key-1", new_key)

        # Should have 2 events: load and update
        assert len(observability_manager.events) == 2
        assert observability_manager.events[1]["event_type"] == "key_config_updated"

    @pytest.mark.asyncio
    async def test_update_key_config_invalid(self, config_file: Path) -> None:
        """Test updating key config with invalid configuration."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        await manager.load_configuration()

        invalid_key = {
            "key_id": "key-1",
            # Missing required fields: key_material, provider_id
        }

        with pytest.raises(ConfigurationError, match="missing required field"):
            await manager.update_key_config("key-1", invalid_key)

    @pytest.mark.asyncio
    async def test_rollback_to_previous(self, config_file: Path) -> None:
        """Test rolling back to previous version."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        await manager.load_configuration()

        # Get initial state
        initial_config = manager.get_current_configuration()
        initial_policy_name = initial_config["policies"][0]["name"]

        # Update policy
        new_policy = {
            "policy_id": "cost-opt",
            "name": "Updated Policy",
            "type": "routing",
            "scope": "global",
        }
        await manager.update_policy("cost-opt", new_policy)

        # Rollback
        rolled_back = await manager.rollback()
        assert rolled_back["policies"][0]["name"] == initial_policy_name

    @pytest.mark.asyncio
    async def test_rollback_to_specific_version(self, config_file: Path) -> None:
        """Test rolling back to a specific version."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        await manager.load_configuration()

        # Get version after load
        history = manager.get_history()
        target_version = history[0]["version"]

        # Make some updates
        new_policy = {
            "policy_id": "cost-opt",
            "name": "Updated",
            "type": "routing",
            "scope": "global",
        }
        await manager.update_policy("cost-opt", new_policy)
        await manager.update_policy("cost-opt", new_policy)

        # Rollback to target version
        rolled_back = await manager.rollback(target_version)
        assert len(rolled_back["policies"]) == 1

    @pytest.mark.asyncio
    async def test_rollback_no_history(self, config_file: Path) -> None:
        """Test rollback fails when no history available."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        # Don't load configuration first

        with pytest.raises(ConfigurationError, match="No configuration history"):
            await manager.rollback()

    @pytest.mark.asyncio
    async def test_rollback_invalid_version(self, config_file: Path) -> None:
        """Test rollback fails with invalid version."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        await manager.load_configuration()

        with pytest.raises(ConfigurationError, match="not found"):
            await manager.rollback(999)

    @pytest.mark.asyncio
    async def test_rollback_emits_event(
        self, config_file: Path, observability_manager: MockObservabilityManager
    ) -> None:
        """Test that rollback emits event."""
        manager = ConfigurationManager(
            config_file_path=str(config_file),
            observability_manager=observability_manager,
        )
        await manager.load_configuration()
        # Make an update so we have a previous version to rollback to
        new_policy = {
            "policy_id": "cost-opt",
            "name": "Updated",
            "type": "routing",
            "scope": "global",
        }
        await manager.update_policy("cost-opt", new_policy)
        await manager.rollback()

        # Should have events: load, rollback
        assert len(observability_manager.events) >= 2
        rollback_events = [
            e for e in observability_manager.events if e["event_type"] == "configuration_rollback"
        ]
        assert len(rollback_events) == 1

    @pytest.mark.asyncio
    async def test_get_current_configuration(self, config_file: Path) -> None:
        """Test getting current configuration."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        await manager.load_configuration()

        current = manager.get_current_configuration()
        assert "keys" in current
        assert "policies" in current
        assert "providers" in current
        assert "version" in current

    @pytest.mark.asyncio
    async def test_get_history(self, config_file: Path) -> None:
        """Test getting configuration history."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        await manager.load_configuration()

        history = manager.get_history()
        assert len(history) == 1
        assert "version" in history[0]
        assert "timestamp" in history[0]

    @pytest.mark.asyncio
    async def test_history_limit(self, config_file: Path) -> None:
        """Test that history is limited to max_history."""
        manager = ConfigurationManager(config_file_path=str(config_file), max_history=3)
        await manager.load_configuration()

        # Make multiple updates
        new_policy = {
            "policy_id": "cost-opt",
            "name": "Updated",
            "type": "routing",
            "scope": "global",
        }
        for _ in range(5):
            await manager.update_policy("cost-opt", new_policy)

        history = manager.get_history()
        assert len(history) <= 3

    @pytest.mark.asyncio
    async def test_thread_safety(self, config_file: Path) -> None:
        """Test that ConfigurationManager is thread-safe."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        await manager.load_configuration()

        # Concurrent updates
        async def update_policy_task() -> None:
            new_policy = {
                "policy_id": "cost-opt",
                "name": "Updated",
                "type": "routing",
                "scope": "global",
            }
            await manager.update_policy("cost-opt", new_policy)

        # Run multiple concurrent updates
        await asyncio.gather(*[update_policy_task() for _ in range(10)])

        # Should not raise any errors
        current = manager.get_current_configuration()
        assert len(current["policies"]) == 1

    @pytest.mark.asyncio
    async def test_validate_keys_empty_key_material(self, config_file: Path) -> None:
        """Test validation fails for empty key_material."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        await manager.load_configuration()

        invalid_key = {
            "key_id": "key-1",
            "key_material": "",
            "provider_id": "openai",
        }

        with pytest.raises(ConfigurationError, match="empty 'key_material'"):
            await manager.update_key_config("key-1", invalid_key)

    @pytest.mark.asyncio
    async def test_validate_policies_invalid_type(self, config_file: Path) -> None:
        """Test validation fails for invalid policy type."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        await manager.load_configuration()

        invalid_policy = {
            "policy_id": "test",
            "name": "Test",
            "type": "invalid_type",
            "scope": "global",
        }

        with pytest.raises(ConfigurationError, match="invalid 'type'"):
            await manager.update_policy("test", invalid_policy)

    @pytest.mark.asyncio
    async def test_validate_policies_invalid_scope(self, config_file: Path) -> None:
        """Test validation fails for invalid policy scope."""
        manager = ConfigurationManager(config_file_path=str(config_file))
        await manager.load_configuration()

        invalid_policy = {
            "policy_id": "test",
            "name": "Test",
            "type": "routing",
            "scope": "invalid_scope",
        }

        with pytest.raises(ConfigurationError, match="invalid 'scope'"):
            await manager.update_policy("test", invalid_policy)

