"""Tests for configuration file loader."""

import json
from pathlib import Path

import pytest
import yaml

from apikeyrouter.infrastructure.config.file_loader import (
    ConfigurationError,
    ConfigurationFileLoader,
)


class TestConfigurationFileLoader:
    """Tests for ConfigurationFileLoader."""

    def test_init_with_path(self, tmp_path: Path) -> None:
        """Test initialization with explicit file path."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("keys: []")

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        assert loader._config_path == config_file

    def test_init_with_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test initialization with environment variable."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("keys: []")

        monkeypatch.setenv("APIKEYROUTER_CONFIG_FILE", str(config_file))
        loader = ConfigurationFileLoader()
        assert loader._config_path == config_file

    def test_init_no_path_no_env(self) -> None:
        """Test initialization fails when no path provided and env var not set."""
        with pytest.raises(ConfigurationError, match="Configuration file path not provided"):
            ConfigurationFileLoader()

    def test_init_file_not_found(self, tmp_path: Path) -> None:
        """Test initialization fails when file does not exist."""
        config_file = tmp_path / "nonexistent.yaml"
        with pytest.raises(ConfigurationError, match="Configuration file not found"):
            ConfigurationFileLoader(config_file_path=str(config_file))

    def test_load_yaml(self, tmp_path: Path) -> None:
        """Test loading YAML configuration file."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "keys": [{"key_material": "sk-test", "provider_id": "openai"}],
            "policies": [],
            "providers": [],
        }
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        loaded = loader.load()

        assert loaded == config_data

    def test_load_yaml_yml_extension(self, tmp_path: Path) -> None:
        """Test loading YAML file with .yml extension."""
        config_file = tmp_path / "config.yml"
        config_data = {"keys": []}
        config_file.write_text(yaml.dump(config_data))

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        loaded = loader.load()

        assert loaded == config_data

    def test_load_json(self, tmp_path: Path) -> None:
        """Test loading JSON configuration file."""
        config_file = tmp_path / "config.json"
        config_data = {
            "keys": [{"key_material": "sk-test", "provider_id": "openai"}],
            "policies": [],
            "providers": [],
        }
        config_file.write_text(json.dumps(config_data))

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        loaded = loader.load()

        assert loaded == config_data

    def test_load_unsupported_format(self, tmp_path: Path) -> None:
        """Test loading unsupported file format raises error."""
        config_file = tmp_path / "config.txt"
        config_file.write_text("keys: []")

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="Unsupported configuration file format"):
            loader.load()

    def test_load_invalid_yaml(self, tmp_path: Path) -> None:
        """Test loading invalid YAML raises error."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("keys: [invalid: yaml: syntax")

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="Invalid YAML format"):
            loader.load()

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        """Test loading invalid JSON raises error."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"keys": [invalid json}')

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="Invalid JSON format"):
            loader.load()

    def test_load_yaml_not_dict(self, tmp_path: Path) -> None:
        """Test loading YAML that is not a dictionary raises error."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("- item1\n- item2")

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="YAML file must contain a dictionary"):
            loader.load()

    def test_load_json_not_dict(self, tmp_path: Path) -> None:
        """Test loading JSON that is not an object raises error."""
        config_file = tmp_path / "config.json"
        config_file.write_text('["item1", "item2"]')

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="JSON file must contain an object"):
            loader.load()

    def test_parse_keys_valid(self, tmp_path: Path) -> None:
        """Test parsing valid keys configuration."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("keys: []")

        config = {
            "keys": [
                {
                    "key_id": "key-1",
                    "key_material": "sk-test-1",
                    "provider_id": "openai",
                    "metadata": {"tier": "pro"},
                },
                {
                    "key_material": "sk-test-2",
                    "provider_id": "anthropic",
                },
            ]
        }

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        keys = loader.parse_keys(config)

        assert len(keys) == 2
        assert keys[0]["key_id"] == "key-1"
        assert keys[0]["key_material"] == "sk-test-1"
        assert keys[0]["provider_id"] == "openai"
        assert keys[0]["metadata"] == {"tier": "pro"}
        assert keys[1]["key_id"] is None
        assert keys[1]["key_material"] == "sk-test-2"
        assert keys[1]["provider_id"] == "anthropic"
        assert keys[1]["metadata"] == {}

    def test_parse_keys_not_list(self, tmp_path: Path) -> None:
        """Test parsing keys that is not a list raises error."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("keys: []")

        config = {"keys": {"key-1": "value"}}

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="Configuration 'keys' must be a list"):
            loader.parse_keys(config)

    def test_parse_keys_missing_key_material(self, tmp_path: Path) -> None:
        """Test parsing keys with missing key_material raises error."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("keys: []")

        config = {"keys": [{"provider_id": "openai"}]}

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="missing required field 'key_material'"):
            loader.parse_keys(config)

    def test_parse_keys_missing_provider_id(self, tmp_path: Path) -> None:
        """Test parsing keys with missing provider_id raises error."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("keys: []")

        config = {"keys": [{"key_material": "sk-test"}]}

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="missing required field 'provider_id'"):
            loader.parse_keys(config)

    def test_parse_keys_invalid_key_material(self, tmp_path: Path) -> None:
        """Test parsing keys with invalid key_material raises error."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("keys: []")

        config = {"keys": [{"key_material": "", "provider_id": "openai"}]}

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="invalid 'key_material'"):
            loader.parse_keys(config)

    def test_parse_keys_invalid_metadata(self, tmp_path: Path) -> None:
        """Test parsing keys with invalid metadata raises error."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("keys: []")

        config = {"keys": [{"key_material": "sk-test", "provider_id": "openai", "metadata": "invalid"}]}

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="invalid 'metadata'"):
            loader.parse_keys(config)

    def test_parse_policies_valid(self, tmp_path: Path) -> None:
        """Test parsing valid policies configuration."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("policies: []")

        config = {
            "policies": [
                {
                    "policy_id": "cost-opt",
                    "name": "Cost Optimization",
                    "type": "routing",
                    "scope": "global",
                    "rules": {"max_cost": 0.01},
                    "priority": 10,
                    "enabled": True,
                },
                {
                    "policy_id": "reliability",
                    "name": "Reliability Policy",
                    "type": "cost_control",
                    "scope": "per_provider",
                    "scope_id": "openai",
                },
            ]
        }

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        policies = loader.parse_policies(config)

        assert len(policies) == 2
        assert policies[0]["policy_id"] == "cost-opt"
        assert policies[0]["name"] == "Cost Optimization"
        assert policies[0]["type"] == "routing"
        assert policies[0]["scope"] == "global"
        assert policies[0]["rules"] == {"max_cost": 0.01}
        assert policies[0]["priority"] == 10
        assert policies[0]["enabled"] is True
        assert policies[1]["scope_id"] == "openai"
        assert policies[1]["priority"] == 0  # Default
        assert policies[1]["enabled"] is True  # Default

    def test_parse_policies_not_list(self, tmp_path: Path) -> None:
        """Test parsing policies that is not a list raises error."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("policies: []")

        config = {"policies": {"policy-1": "value"}}

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="Configuration 'policies' must be a list"):
            loader.parse_policies(config)

    def test_parse_policies_missing_required_field(self, tmp_path: Path) -> None:
        """Test parsing policies with missing required field raises error."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("policies: []")

        config = {"policies": [{"policy_id": "test", "name": "Test", "type": "routing"}]}

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="missing required field 'scope'"):
            loader.parse_policies(config)

    def test_parse_policies_invalid_rules(self, tmp_path: Path) -> None:
        """Test parsing policies with invalid rules raises error."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("policies: []")

        config = {
            "policies": [
                {
                    "policy_id": "test",
                    "name": "Test",
                    "type": "routing",
                    "scope": "global",
                    "rules": "invalid",
                }
            ]
        }

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="invalid 'rules'"):
            loader.parse_policies(config)

    def test_parse_providers_valid(self, tmp_path: Path) -> None:
        """Test parsing valid providers configuration."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("providers: []")

        config = {
            "providers": [
                {
                    "provider_id": "openai",
                    "adapter_type": "OpenAIAdapter",
                    "config": {"base_url": "https://api.openai.com/v1"},
                },
                {"provider_id": "anthropic", "adapter_type": "AnthropicAdapter"},
            ]
        }

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        providers = loader.parse_providers(config)

        assert len(providers) == 2
        assert providers[0]["provider_id"] == "openai"
        assert providers[0]["adapter_type"] == "OpenAIAdapter"
        assert providers[0]["config"] == {"base_url": "https://api.openai.com/v1"}
        assert providers[1]["provider_id"] == "anthropic"
        assert providers[1]["config"] == {}  # Default

    def test_parse_providers_not_list(self, tmp_path: Path) -> None:
        """Test parsing providers that is not a list raises error."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("providers: []")

        config = {"providers": {"openai": "value"}}

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="Configuration 'providers' must be a list"):
            loader.parse_providers(config)

    def test_parse_providers_missing_provider_id(self, tmp_path: Path) -> None:
        """Test parsing providers with missing provider_id raises error."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("providers: []")

        config = {"providers": [{"adapter_type": "OpenAIAdapter"}]}

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="missing required field 'provider_id'"):
            loader.parse_providers(config)

    def test_parse_providers_invalid_config(self, tmp_path: Path) -> None:
        """Test parsing providers with invalid config raises error."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("providers: []")

        config = {
            "providers": [
                {"provider_id": "openai", "adapter_type": "OpenAIAdapter", "config": "invalid"}
            ]
        }

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="invalid 'config'"):
            loader.parse_providers(config)

    def test_validate_structure_valid(self, tmp_path: Path) -> None:
        """Test validating valid configuration structure."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("keys: []")

        config = {
            "keys": [{"key_material": "sk-test", "provider_id": "openai"}],
            "policies": [],
            "providers": [],
        }

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        # Should not raise
        loader.validate_structure(config)

    def test_validate_structure_unknown_key(self, tmp_path: Path) -> None:
        """Test validating structure with unknown key raises error."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("keys: []")

        config = {"keys": [], "unknown_key": "value"}

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="Unknown configuration key"):
            loader.validate_structure(config)

    def test_validate_structure_empty_config(self, tmp_path: Path) -> None:
        """Test validating empty configuration."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("{}")

        config = {}

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        # Should not raise
        loader.validate_structure(config)

    def test_validate_structure_invalid_keys(self, tmp_path: Path) -> None:
        """Test validating structure with invalid keys raises error."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("keys: []")

        config = {"keys": "invalid"}

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        with pytest.raises(ConfigurationError, match="Configuration 'keys' must be a list"):
            loader.validate_structure(config)

    def test_whitespace_stripping(self, tmp_path: Path) -> None:
        """Test that whitespace is stripped from string fields."""
        config_file = tmp_path / "test.yaml"
        config_file.write_text("keys: []")

        config = {
            "keys": [
                {
                    "key_material": "  sk-test  ",
                    "provider_id": "  openai  ",
                }
            ],
            "policies": [
                {
                    "policy_id": "  test  ",
                    "name": "  Test Policy  ",
                    "type": "  routing  ",
                    "scope": "  global  ",
                }
            ],
            "providers": [
                {
                    "provider_id": "  openai  ",
                    "adapter_type": "  OpenAIAdapter  ",
                }
            ],
        }

        loader = ConfigurationFileLoader(config_file_path=str(config_file))
        keys = loader.parse_keys(config)
        policies = loader.parse_policies(config)
        providers = loader.parse_providers(config)

        assert keys[0]["key_material"] == "sk-test"
        assert keys[0]["provider_id"] == "openai"
        assert policies[0]["policy_id"] == "test"
        assert policies[0]["name"] == "Test Policy"
        assert providers[0]["provider_id"] == "openai"
        assert providers[0]["adapter_type"] == "OpenAIAdapter"

