"""Configuration manager for dynamic configuration management."""

import asyncio
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.models.policy import PolicyScope, PolicyType
from apikeyrouter.infrastructure.config.file_loader import (
    ConfigurationError,
    ConfigurationFileLoader,
)


class ConfigurationSnapshot:
    """Represents a snapshot of configuration state for versioning and rollback."""

    def __init__(
        self,
        version: int,
        keys: list[dict[str, Any]],
        policies: list[dict[str, Any]],
        providers: list[dict[str, Any]],
        timestamp: datetime,
    ) -> None:
        """Initialize configuration snapshot.

        Args:
            version: Version number for this snapshot.
            keys: List of key configurations.
            policies: List of policy configurations.
            providers: List of provider configurations.
            timestamp: Timestamp when snapshot was created.
        """
        self.version = version
        self.keys = deepcopy(keys)
        self.policies = deepcopy(policies)
        self.providers = deepcopy(providers)
        self.timestamp = timestamp


class ConfigurationManager:
    """Manages dynamic configuration with hot reload, validation, and rollback.

    ConfigurationManager loads configuration from files, supports hot reload,
    validates configuration before applying, and provides rollback capabilities.
    """

    def __init__(
        self,
        config_file_path: str | Path | None = None,
        observability_manager: ObservabilityManager | None = None,
        max_history: int = 10,
    ) -> None:
        """Initialize ConfigurationManager.

        Args:
            config_file_path: Path to configuration file. If None, attempts to
                            load from APIKEYROUTER_CONFIG_FILE environment variable.
            observability_manager: Optional ObservabilityManager for logging and events.
            max_history: Maximum number of configuration snapshots to keep for rollback.

        Raises:
            ConfigurationError: If configuration file cannot be loaded.
        """
        self._file_loader = ConfigurationFileLoader(config_file_path=config_file_path)
        self._observability = observability_manager
        self._max_history = max_history

        # Current configuration state
        self._keys: dict[str, dict[str, Any]] = {}
        self._policies: dict[str, dict[str, Any]] = {}
        self._providers: dict[str, dict[str, Any]] = {}

        # Configuration history for rollback
        self._history: list[ConfigurationSnapshot] = []
        self._current_version = 0

        # Lock for thread-safety
        self._lock = asyncio.Lock()

    async def load_configuration(self) -> dict[str, Any]:
        """Load configuration from file.

        Loads configuration from the configured file, validates it, and applies it.
        Creates a snapshot for rollback.

        Returns:
            Dictionary containing loaded configuration:
            - keys: List of key configurations
            - policies: List of policy configurations
            - providers: List of provider configurations

        Raises:
            ConfigurationError: If configuration cannot be loaded or validated.
        """
        async with self._lock:
            try:
                # Load configuration from file
                config = self._file_loader.load()

                # Validate structure
                self._file_loader.validate_structure(config)

                # Parse configuration sections
                keys_config = self._file_loader.parse_keys(config)
                policies_config = self._file_loader.parse_policies(config)
                providers_config = self._file_loader.parse_providers(config)

                # Validate parsed configuration
                await self._validate_configuration(keys_config, policies_config, providers_config)

                # Create snapshot of current state before applying (if state is not empty)
                if self._keys or self._policies or self._providers:
                    snapshot = ConfigurationSnapshot(
                        version=self._current_version,
                        keys=list(self._keys.values()),
                        policies=list(self._policies.values()),
                        providers=list(self._providers.values()),
                        timestamp=datetime.utcnow(),
                    )
                    self._add_to_history(snapshot)

                # Apply configuration
                self._apply_keys(keys_config)
                self._apply_policies(policies_config)
                self._apply_providers(providers_config)

                self._current_version += 1

                # Create snapshot of loaded state after applying
                loaded_snapshot = ConfigurationSnapshot(
                    version=self._current_version,
                    keys=list(self._keys.values()),
                    policies=list(self._policies.values()),
                    providers=list(self._providers.values()),
                    timestamp=datetime.utcnow(),
                )
                self._add_to_history(loaded_snapshot)

                # Emit configuration loaded event
                if self._observability:
                    await self._observability.emit_event(
                        event_type="configuration_loaded",
                        payload={
                            "version": self._current_version,
                            "keys_count": len(self._keys),
                            "policies_count": len(self._policies),
                            "providers_count": len(self._providers),
                        },
                        metadata={"timestamp": datetime.utcnow().isoformat()},
                    )

                return {
                    "keys": keys_config,
                    "policies": policies_config,
                    "providers": providers_config,
                }

            except ConfigurationError:
                raise
            except Exception as e:
                raise ConfigurationError(f"Failed to load configuration: {e}") from e

    async def reload_configuration(self) -> dict[str, Any]:
        """Reload configuration from file (hot reload).

        Reloads configuration from the file and applies changes without restart.
        Validates configuration before applying and rolls back on failure.

        Returns:
            Dictionary containing reloaded configuration.

        Raises:
            ConfigurationError: If configuration cannot be reloaded or validated.
        """
        return await self.load_configuration()

    async def update_policy(
        self, policy_id: str, policy_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Update a policy configuration (hot reload).

        Updates a specific policy configuration and applies it immediately.
        Validates the policy before applying and rolls back on failure.

        Args:
            policy_id: Policy identifier to update.
            policy_config: Policy configuration dictionary.

        Returns:
            Updated policy configuration.

        Raises:
            ConfigurationError: If policy is invalid or update fails.
        """
        async with self._lock:
            try:
                # Validate policy configuration
                if "policy_id" not in policy_config:
                    policy_config["policy_id"] = policy_id
                elif policy_config["policy_id"] != policy_id:
                    raise ConfigurationError(
                        f"Policy ID mismatch: expected '{policy_id}', got '{policy_config['policy_id']}'"
                    )

                # Create temporary policies list for validation
                temp_policies = list(self._policies.values())
                # Update or add policy
                policy_found = False
                for idx, existing_policy in enumerate(temp_policies):
                    if existing_policy.get("policy_id") == policy_id:
                        temp_policies[idx] = policy_config
                        policy_found = True
                        break
                if not policy_found:
                    temp_policies.append(policy_config)

                # Validate updated configuration
                await self._validate_policies(temp_policies)

                # Create snapshot before applying
                snapshot = ConfigurationSnapshot(
                    version=self._current_version,
                    keys=list(self._keys.values()),
                    policies=list(self._policies.values()),
                    providers=list(self._providers.values()),
                    timestamp=datetime.utcnow(),
                )
                self._add_to_history(snapshot)

                # Apply policy update
                self._policies[policy_id] = policy_config
                self._current_version += 1

                # Emit policy updated event
                if self._observability:
                    await self._observability.emit_event(
                        event_type="policy_updated",
                        payload={
                            "policy_id": policy_id,
                            "version": self._current_version,
                        },
                        metadata={"timestamp": datetime.utcnow().isoformat()},
                    )

                return policy_config

            except ConfigurationError:
                raise
            except Exception as e:
                raise ConfigurationError(f"Failed to update policy: {e}") from e

    async def update_key_config(
        self, key_id: str, key_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Update a key configuration (hot reload).

        Updates a specific key configuration and applies it immediately.
        Validates the key before applying and rolls back on failure.

        Args:
            key_id: Key identifier to update.
            key_config: Key configuration dictionary.

        Returns:
            Updated key configuration.

        Raises:
            ConfigurationError: If key is invalid or update fails.
        """
        async with self._lock:
            try:
                # Validate key configuration
                if "key_id" not in key_config:
                    key_config["key_id"] = key_id
                elif key_config.get("key_id") != key_id:
                    raise ConfigurationError(
                        f"Key ID mismatch: expected '{key_id}', got '{key_config.get('key_id')}'"
                    )

                # Validate required fields
                if "key_material" not in key_config:
                    raise ConfigurationError("Key configuration missing required field 'key_material'")
                if "provider_id" not in key_config:
                    raise ConfigurationError("Key configuration missing required field 'provider_id'")

                # Create temporary keys list for validation
                temp_keys = list(self._keys.values())
                # Update or add key
                key_found = False
                for idx, existing_key in enumerate(temp_keys):
                    if existing_key.get("key_id") == key_id:
                        temp_keys[idx] = key_config
                        key_found = True
                        break
                if not key_found:
                    temp_keys.append(key_config)

                # Validate updated configuration
                await self._validate_keys(temp_keys)

                # Create snapshot before applying
                snapshot = ConfigurationSnapshot(
                    version=self._current_version,
                    keys=list(self._keys.values()),
                    policies=list(self._policies.values()),
                    providers=list(self._providers.values()),
                    timestamp=datetime.utcnow(),
                )
                self._add_to_history(snapshot)

                # Apply key update
                self._keys[key_id] = key_config
                self._current_version += 1

                # Emit key updated event
                if self._observability:
                    await self._observability.emit_event(
                        event_type="key_config_updated",
                        payload={
                            "key_id": key_id,
                            "version": self._current_version,
                        },
                        metadata={"timestamp": datetime.utcnow().isoformat()},
                    )

                return key_config

            except ConfigurationError:
                raise
            except Exception as e:
                raise ConfigurationError(f"Failed to update key config: {e}") from e

    async def rollback(self, version: int | None = None) -> dict[str, Any]:
        """Rollback to a previous configuration version.

        If version is None, rolls back to the previous version.

        Args:
            version: Version number to rollback to. If None, rolls back to previous version.

        Returns:
            Dictionary containing rolled back configuration.

        Raises:
            ConfigurationError: If version not found or rollback fails.
        """
        async with self._lock:
            if not self._history:
                raise ConfigurationError("No configuration history available for rollback")

            # Determine target version
            if version is None:
                if len(self._history) < 2:
                    raise ConfigurationError("No previous version available for rollback")
                target_version = self._history[-2].version
            else:
                target_version = version

            # Find snapshot with target version
            target_snapshot = None
            for snapshot in reversed(self._history):
                if snapshot.version == target_version:
                    target_snapshot = snapshot
                    break

            if target_snapshot is None:
                raise ConfigurationError(f"Configuration version {target_version} not found")

            try:
                # Create snapshot of current state
                current_snapshot = ConfigurationSnapshot(
                    version=self._current_version,
                    keys=list(self._keys.values()),
                    policies=list(self._policies.values()),
                    providers=list(self._providers.values()),
                    timestamp=datetime.utcnow(),
                )
                self._add_to_history(current_snapshot)

                # Restore from snapshot
                self._keys = {}
                for idx, key in enumerate(target_snapshot.keys):
                    key_id = key.get("key_id") or f"key-{idx}"
                    self._keys[key_id] = key

                self._policies = {}
                for policy in target_snapshot.policies:
                    # Policies should always have policy_id from validation
                    # But handle gracefully if missing
                    policy_id = policy.get("policy_id")
                    if not policy_id:
                        # Generate policy_id if missing (shouldn't happen, but handle gracefully)
                        policy_id = f"policy-{len(self._policies)}"
                        policy = {**policy, "policy_id": policy_id}  # Create new dict to avoid mutating original
                    self._policies[policy_id] = policy

                self._providers = {}
                for provider in target_snapshot.providers:
                    provider_id = provider.get("provider_id")
                    if provider_id:
                        self._providers[provider_id] = provider
                    else:
                        # If provider doesn't have provider_id, generate one
                        provider_id = f"provider-{len(self._providers)}"
                        provider["provider_id"] = provider_id
                        self._providers[provider_id] = provider

                self._current_version += 1

                # Emit rollback event
                if self._observability:
                    await self._observability.emit_event(
                        event_type="configuration_rollback",
                        payload={
                            "from_version": current_snapshot.version,
                            "to_version": target_version,
                            "new_version": self._current_version,
                        },
                        metadata={"timestamp": datetime.utcnow().isoformat()},
                    )

                return {
                    "keys": list(self._keys.values()),
                    "policies": list(self._policies.values()),
                    "providers": list(self._providers.values()),
                }

            except Exception as e:
                raise ConfigurationError(f"Failed to rollback configuration: {e}") from e

    def get_current_configuration(self) -> dict[str, Any]:
        """Get current configuration state.

        Returns:
            Dictionary containing current configuration.
        """
        return {
            "keys": list(self._keys.values()),
            "policies": list(self._policies.values()),
            "providers": list(self._providers.values()),
            "version": self._current_version,
        }

    def get_history(self) -> list[dict[str, Any]]:
        """Get configuration history.

        Returns:
            List of configuration snapshots with version and timestamp.
        """
        return [
            {
                "version": snapshot.version,
                "timestamp": snapshot.timestamp.isoformat(),
                "keys_count": len(snapshot.keys),
                "policies_count": len(snapshot.policies),
                "providers_count": len(snapshot.providers),
            }
            for snapshot in self._history
        ]

    def _apply_keys(self, keys_config: list[dict[str, Any]]) -> None:
        """Apply keys configuration.

        Args:
            keys_config: List of key configurations to apply.
        """
        self._keys = {}
        for key_config in keys_config:
            key_id = key_config.get("key_id") or f"key-{len(self._keys)}"
            self._keys[key_id] = key_config

    def _apply_policies(self, policies_config: list[dict[str, Any]]) -> None:
        """Apply policies configuration.

        Args:
            policies_config: List of policy configurations to apply.
        """
        self._policies = {}
        for policy_config in policies_config:
            policy_id = policy_config.get("policy_id")
            if policy_id:
                self._policies[policy_id] = policy_config

    def _apply_providers(self, providers_config: list[dict[str, Any]]) -> None:
        """Apply providers configuration.

        Args:
            providers_config: List of provider configurations to apply.
        """
        self._providers = {}
        for provider_config in providers_config:
            provider_id = provider_config.get("provider_id")
            if provider_id:
                self._providers[provider_id] = provider_config

    def _add_to_history(self, snapshot: ConfigurationSnapshot) -> None:
        """Add snapshot to history, maintaining max_history limit.

        Args:
            snapshot: Configuration snapshot to add.
        """
        self._history.append(snapshot)
        # Keep only last max_history snapshots
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

    async def _validate_configuration(
        self,
        keys_config: list[dict[str, Any]],
        policies_config: list[dict[str, Any]],
        providers_config: list[dict[str, Any]],
    ) -> None:
        """Validate configuration before applying.

        Args:
            keys_config: List of key configurations to validate.
            policies_config: List of policy configurations to validate.
            providers_config: List of provider configurations to validate.

        Raises:
            ConfigurationError: If validation fails.
        """
        await self._validate_keys(keys_config)
        await self._validate_policies(policies_config)
        await self._validate_providers(providers_config)

    async def _validate_keys(self, keys_config: list[dict[str, Any]]) -> None:
        """Validate keys configuration.

        Args:
            keys_config: List of key configurations to validate.

        Raises:
            ConfigurationError: If validation fails.
        """
        for idx, key_config in enumerate(keys_config):
            # Validate required fields
            if "key_material" not in key_config:
                raise ConfigurationError(
                    f"Key configuration at index {idx} missing required field 'key_material'",
                    field=f"keys[{idx}].key_material",
                )
            if "provider_id" not in key_config:
                raise ConfigurationError(
                    f"Key configuration at index {idx} missing required field 'provider_id'",
                    field=f"keys[{idx}].provider_id",
                )

            # Validate key_material is not empty
            if not key_config["key_material"] or not key_config["key_material"].strip():
                raise ConfigurationError(
                    f"Key configuration at index {idx} has empty 'key_material'",
                    field=f"keys[{idx}].key_material",
                )

    async def _validate_policies(self, policies_config: list[dict[str, Any]]) -> None:
        """Validate policies configuration.

        Args:
            policies_config: List of policy configurations to validate.

        Raises:
            ConfigurationError: If validation fails.
        """
        for idx, policy_config in enumerate(policies_config):
            # Validate required fields
            required_fields = ["policy_id", "name", "type", "scope"]
            for field in required_fields:
                if field not in policy_config:
                    raise ConfigurationError(
                        f"Policy configuration at index {idx} missing required field '{field}'",
                        field=f"policies[{idx}].{field}",
                    )

            # Validate policy type
            try:
                PolicyType(policy_config["type"])
            except ValueError as err:
                raise ConfigurationError(
                    f"Policy configuration at index {idx} has invalid 'type': {policy_config['type']}",
                    field=f"policies[{idx}].type",
                ) from err

            # Validate policy scope
            try:
                PolicyScope(policy_config["scope"])
            except ValueError as err:
                raise ConfigurationError(
                    f"Policy configuration at index {idx} has invalid 'scope': {policy_config['scope']}",
                    field=f"policies[{idx}].scope",
                ) from err

    async def _validate_providers(self, providers_config: list[dict[str, Any]]) -> None:
        """Validate providers configuration.

        Args:
            providers_config: List of provider configurations to validate.

        Raises:
            ConfigurationError: If validation fails.
        """
        for idx, provider_config in enumerate(providers_config):
            # Validate required fields
            if "provider_id" not in provider_config:
                raise ConfigurationError(
                    f"Provider configuration at index {idx} missing required field 'provider_id'",
                    field=f"providers[{idx}].provider_id",
                )
            if "adapter_type" not in provider_config:
                raise ConfigurationError(
                    f"Provider configuration at index {idx} missing required field 'adapter_type'",
                    field=f"providers[{idx}].adapter_type",
                )

