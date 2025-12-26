"""Configuration file loader for YAML and JSON files."""

import json
import os
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(Exception):
    """Raised when configuration loading or validation fails."""

    def __init__(self, message: str, field: str | None = None) -> None:
        """Initialize ConfigurationError.

        Args:
            message: Human-readable error message.
            field: Optional field name that failed validation.
        """
        self.message = message
        self.field = field
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return error message with field name if available."""
        if self.field:
            return f"Configuration error in field '{self.field}': {self.message}"
        return self.message


class ConfigurationFileLoader:
    """Loads configuration from YAML or JSON files.

    Supports loading keys, policies, and provider configurations from
    configuration files. Validates file format and structure.
    """

    def __init__(self, config_file_path: str | Path | None = None) -> None:
        """Initialize ConfigurationFileLoader.

        Args:
            config_file_path: Path to configuration file. If None, attempts to
                            load from APIKEYROUTER_CONFIG_FILE environment variable.
                            If not set, raises ConfigurationError.

        Raises:
            ConfigurationError: If config_file_path is not provided and
                              APIKEYROUTER_CONFIG_FILE is not set.
        """
        if config_file_path is None:
            config_file_path = os.getenv("APIKEYROUTER_CONFIG_FILE")
            if not config_file_path:
                raise ConfigurationError(
                    "Configuration file path not provided and APIKEYROUTER_CONFIG_FILE "
                    "environment variable is not set"
                )

        self._config_path = Path(config_file_path)
        if not self._config_path.exists():
            raise ConfigurationError(f"Configuration file not found: {self._config_path}")

        # Validate file path to prevent directory traversal
        try:
            self._config_path.resolve().relative_to(Path.cwd().resolve())
        except ValueError:
            # If file is outside current directory, check if it's an absolute path
            if not self._config_path.is_absolute():
                raise ConfigurationError(
                    f"Configuration file path must be within current directory or absolute: {self._config_path}"
                ) from None

    def load(self) -> dict[str, Any]:
        """Load configuration from file.

        Automatically detects file format (YAML or JSON) based on file extension.

        Returns:
            Dictionary containing configuration data with keys:
            - keys: List of key configurations
            - policies: List of policy configurations
            - providers: List of provider configurations

        Raises:
            ConfigurationError: If file format is invalid or file cannot be parsed.
        """
        suffix = self._config_path.suffix.lower()

        if suffix in (".yaml", ".yml"):
            return self._load_yaml()
        elif suffix == ".json":
            return self._load_json()
        else:
            raise ConfigurationError(
                f"Unsupported configuration file format: {suffix}. "
                "Supported formats: .yaml, .yml, .json"
            )

    def _load_yaml(self) -> dict[str, Any]:
        """Load configuration from YAML file.

        Returns:
            Dictionary containing configuration data.

        Raises:
            ConfigurationError: If YAML file is invalid or cannot be parsed.
        """
        try:
            with self._config_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data is None:
                    return {}
                if not isinstance(data, dict):
                    raise ConfigurationError("YAML file must contain a dictionary/mapping")
                return data
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML format: {e}") from e
        except OSError as e:
            raise ConfigurationError(f"Failed to read configuration file: {e}") from e

    def _load_json(self) -> dict[str, Any]:
        """Load configuration from JSON file.

        Returns:
            Dictionary containing configuration data.

        Raises:
            ConfigurationError: If JSON file is invalid or cannot be parsed.
        """
        try:
            with self._config_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    raise ConfigurationError("JSON file must contain an object")
                return data
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON format: {e}") from e
        except OSError as e:
            raise ConfigurationError(f"Failed to read configuration file: {e}") from e

    def parse_keys(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse keys configuration from loaded configuration.

        Args:
            config: Configuration dictionary loaded from file.

        Returns:
            List of key configuration dictionaries. Each dictionary contains:
            - key_id: str (optional, will be generated if not provided)
            - key_material: str (required) - The actual API key
            - provider_id: str (required) - Provider identifier
            - metadata: dict (optional) - Key metadata

        Raises:
            ConfigurationError: If keys configuration is invalid.
        """
        keys_config = config.get("keys", [])
        if not isinstance(keys_config, list):
            raise ConfigurationError(
                "Configuration 'keys' must be a list", field="keys"
            )

        parsed_keys = []
        for idx, key_config in enumerate(keys_config):
            if not isinstance(key_config, dict):
                raise ConfigurationError(
                    f"Key configuration at index {idx} must be a dictionary",
                    field=f"keys[{idx}]",
                )

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

            # Validate field types
            if not isinstance(key_config["key_material"], str) or not key_config["key_material"].strip():
                raise ConfigurationError(
                    f"Key configuration at index {idx} has invalid 'key_material' (must be non-empty string)",
                    field=f"keys[{idx}].key_material",
                )
            if not isinstance(key_config["provider_id"], str) or not key_config["provider_id"].strip():
                raise ConfigurationError(
                    f"Key configuration at index {idx} has invalid 'provider_id' (must be non-empty string)",
                    field=f"keys[{idx}].provider_id",
                )

            # Validate metadata if present
            if "metadata" in key_config and not isinstance(key_config["metadata"], dict):
                raise ConfigurationError(
                    f"Key configuration at index {idx} has invalid 'metadata' (must be a dictionary)",
                    field=f"keys[{idx}].metadata",
                )

            parsed_keys.append({
                "key_id": key_config.get("key_id"),  # Optional
                "key_material": key_config["key_material"].strip(),
                "provider_id": key_config["provider_id"].strip(),
                "metadata": key_config.get("metadata", {}),
            })

        return parsed_keys

    def parse_policies(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse policies configuration from loaded configuration.

        Args:
            config: Configuration dictionary loaded from file.

        Returns:
            List of policy configuration dictionaries. Each dictionary contains:
            - policy_id: str (required) - Unique policy identifier
            - name: str (required) - Human-readable policy name
            - type: str (required) - Policy type (routing, cost_control, etc.)
            - scope: str (required) - Policy scope (global, per_provider, etc.)
            - scope_id: str (optional) - Specific entity ID if scoped
            - rules: dict (optional) - Policy rules
            - priority: int (optional) - Policy priority
            - enabled: bool (optional) - Whether policy is active

        Raises:
            ConfigurationError: If policies configuration is invalid.
        """
        policies_config = config.get("policies", [])
        if not isinstance(policies_config, list):
            raise ConfigurationError(
                "Configuration 'policies' must be a list", field="policies"
            )

        parsed_policies = []
        for idx, policy_config in enumerate(policies_config):
            if not isinstance(policy_config, dict):
                raise ConfigurationError(
                    f"Policy configuration at index {idx} must be a dictionary",
                    field=f"policies[{idx}]",
                )

            # Validate required fields
            required_fields = ["policy_id", "name", "type", "scope"]
            for field in required_fields:
                if field not in policy_config:
                    raise ConfigurationError(
                        f"Policy configuration at index {idx} missing required field '{field}'",
                        field=f"policies[{idx}].{field}",
                    )

            # Validate field types
            if not isinstance(policy_config["policy_id"], str) or not policy_config["policy_id"].strip():
                raise ConfigurationError(
                    f"Policy configuration at index {idx} has invalid 'policy_id' (must be non-empty string)",
                    field=f"policies[{idx}].policy_id",
                )
            if not isinstance(policy_config["name"], str) or not policy_config["name"].strip():
                raise ConfigurationError(
                    f"Policy configuration at index {idx} has invalid 'name' (must be non-empty string)",
                    field=f"policies[{idx}].name",
                )
            if not isinstance(policy_config["type"], str) or not policy_config["type"].strip():
                raise ConfigurationError(
                    f"Policy configuration at index {idx} has invalid 'type' (must be non-empty string)",
                    field=f"policies[{idx}].type",
                )
            if not isinstance(policy_config["scope"], str) or not policy_config["scope"].strip():
                raise ConfigurationError(
                    f"Policy configuration at index {idx} has invalid 'scope' (must be non-empty string)",
                    field=f"policies[{idx}].scope",
                )

            # Validate optional fields
            if "rules" in policy_config and not isinstance(policy_config["rules"], dict):
                raise ConfigurationError(
                    f"Policy configuration at index {idx} has invalid 'rules' (must be a dictionary)",
                    field=f"policies[{idx}].rules",
                )
            if "priority" in policy_config and not isinstance(policy_config["priority"], int):
                raise ConfigurationError(
                    f"Policy configuration at index {idx} has invalid 'priority' (must be an integer)",
                    field=f"policies[{idx}].priority",
                )
            if "enabled" in policy_config and not isinstance(policy_config["enabled"], bool):
                raise ConfigurationError(
                    f"Policy configuration at index {idx} has invalid 'enabled' (must be a boolean)",
                    field=f"policies[{idx}].enabled",
                )

            parsed_policies.append({
                "policy_id": policy_config["policy_id"].strip(),
                "name": policy_config["name"].strip(),
                "type": policy_config["type"].strip(),
                "scope": policy_config["scope"].strip(),
                "scope_id": policy_config.get("scope_id"),
                "rules": policy_config.get("rules", {}),
                "priority": policy_config.get("priority", 0),
                "enabled": policy_config.get("enabled", True),
            })

        return parsed_policies

    def parse_providers(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Parse provider configuration from loaded configuration.

        Args:
            config: Configuration dictionary loaded from file.

        Returns:
            List of provider configuration dictionaries. Each dictionary contains:
            - provider_id: str (required) - Provider identifier
            - adapter_type: str (required) - Adapter class name
            - config: dict (optional) - Provider-specific configuration

        Note:
            Provider adapters must be registered programmatically. This configuration
            only stores provider metadata, not the adapter instances themselves.

        Raises:
            ConfigurationError: If provider configuration is invalid.
        """
        providers_config = config.get("providers", [])
        if not isinstance(providers_config, list):
            raise ConfigurationError(
                "Configuration 'providers' must be a list", field="providers"
            )

        parsed_providers = []
        for idx, provider_config in enumerate(providers_config):
            if not isinstance(provider_config, dict):
                raise ConfigurationError(
                    f"Provider configuration at index {idx} must be a dictionary",
                    field=f"providers[{idx}]",
                )

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

            # Validate field types
            if not isinstance(provider_config["provider_id"], str) or not provider_config["provider_id"].strip():
                raise ConfigurationError(
                    f"Provider configuration at index {idx} has invalid 'provider_id' (must be non-empty string)",
                    field=f"providers[{idx}].provider_id",
                )
            if not isinstance(provider_config["adapter_type"], str) or not provider_config["adapter_type"].strip():
                raise ConfigurationError(
                    f"Provider configuration at index {idx} has invalid 'adapter_type' (must be non-empty string)",
                    field=f"providers[{idx}].adapter_type",
                )

            # Validate config if present
            if "config" in provider_config and not isinstance(provider_config["config"], dict):
                raise ConfigurationError(
                    f"Provider configuration at index {idx} has invalid 'config' (must be a dictionary)",
                    field=f"providers[{idx}].config",
                )

            parsed_providers.append({
                "provider_id": provider_config["provider_id"].strip(),
                "adapter_type": provider_config["adapter_type"].strip(),
                "config": provider_config.get("config", {}),
            })

        return parsed_providers

    def validate_structure(self, config: dict[str, Any]) -> None:
        """Validate configuration file structure.

        Ensures the configuration has the expected top-level structure.

        Args:
            config: Configuration dictionary to validate.

        Raises:
            ConfigurationError: If configuration structure is invalid.
        """
        if not isinstance(config, dict):
            raise ConfigurationError("Configuration must be a dictionary")

        # Validate top-level keys (keys, policies, providers are optional)
        allowed_keys = {"keys", "policies", "providers"}
        for key in config:
            if key not in allowed_keys:
                raise ConfigurationError(
                    f"Unknown configuration key: '{key}'. Allowed keys: {', '.join(sorted(allowed_keys))}",
                    field=key,
                )

        # Validate each section if present
        if "keys" in config:
            self.parse_keys(config)  # This will validate keys structure
        if "policies" in config:
            self.parse_policies(config)  # This will validate policies structure
        if "providers" in config:
            self.parse_providers(config)  # This will validate providers structure

