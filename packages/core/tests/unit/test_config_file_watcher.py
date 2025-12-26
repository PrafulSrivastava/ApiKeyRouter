"""Tests for configuration file watcher."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
import yaml

from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.infrastructure.config.file_watcher import ConfigurationFileWatcher
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


class TestConfigurationFileWatcher:
    """Tests for ConfigurationFileWatcher."""

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
                }
            ],
            "policies": [],
            "providers": [],
        }
        config_file.write_text(yaml.dump(config_data))
        return config_file

    @pytest.fixture
    def config_manager(self, config_file: Path) -> ConfigurationManager:
        """Create a ConfigurationManager instance."""
        return ConfigurationManager(config_file_path=str(config_file))

    @pytest.fixture
    def observability_manager(self) -> MockObservabilityManager:
        """Create a mock observability manager."""
        return MockObservabilityManager()

    def test_start_stop(self, config_manager: ConfigurationManager, config_file: Path) -> None:
        """Test starting and stopping the watcher."""
        watcher = ConfigurationFileWatcher(
            config_manager=config_manager,
            config_file_path=str(config_file),
        )

        # Start watcher
        watcher.start()
        assert watcher.is_watching() is True

        # Stop watcher
        watcher.stop()
        assert watcher.is_watching() is False

    def test_context_manager(self, config_manager: ConfigurationManager, config_file: Path) -> None:
        """Test using watcher as context manager."""
        with ConfigurationFileWatcher(
            config_manager=config_manager,
            config_file_path=str(config_file),
        ) as watcher:
            assert watcher.is_watching() is True

        # Watcher should be stopped after context exit
        assert watcher.is_watching() is False

    def test_start_already_started(self, config_manager: ConfigurationManager, config_file: Path) -> None:
        """Test that starting an already started watcher raises error."""
        watcher = ConfigurationFileWatcher(
            config_manager=config_manager,
            config_file_path=str(config_file),
        )

        watcher.start()
        with pytest.raises(RuntimeError, match="already started"):
            watcher.start()

        watcher.stop()

    @pytest.mark.asyncio
    async def test_file_change_triggers_reload(
        self, config_manager: ConfigurationManager, config_file: Path, observability_manager: MockObservabilityManager
    ) -> None:
        """Test that file changes trigger configuration reload."""
        # Load initial configuration
        await config_manager.load_configuration()

        # Create watcher with short debounce for testing
        watcher = ConfigurationFileWatcher(
            config_manager=config_manager,
            config_file_path=str(config_file),
            debounce_seconds=0.1,
            observability_manager=observability_manager,
        )

        try:
            watcher.start()

            # Modify configuration file
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

            # Wait for debounce and reload
            await asyncio.sleep(0.5)

            # Verify configuration was reloaded
            current = config_manager.get_current_configuration()
            assert len(current["keys"]) == 1
            assert current["keys"][0]["key_id"] == "key-2"

            # Verify events were logged
            reload_logs = [
                log for log in observability_manager.logs if "reload" in log["message"].lower()
            ]
            assert len(reload_logs) >= 1

            reload_events = [
                event
                for event in observability_manager.events
                if event["event_type"] == "configuration_file_reloaded"
            ]
            assert len(reload_events) >= 1

        finally:
            watcher.stop()

    @pytest.mark.asyncio
    async def test_debouncing(
        self, config_manager: ConfigurationManager, config_file: Path, observability_manager: MockObservabilityManager
    ) -> None:
        """Test that rapid file changes are debounced."""
        await config_manager.load_configuration()

        watcher = ConfigurationFileWatcher(
            config_manager=config_manager,
            config_file_path=str(config_file),
            debounce_seconds=0.3,
            observability_manager=observability_manager,
        )

        try:
            watcher.start()

            # Make multiple rapid changes
            for i in range(3):
                config_data = {
                    "keys": [
                        {
                            "key_id": f"key-{i}",
                            "key_material": f"sk-test-{i}",
                            "provider_id": "openai",
                        }
                    ],
                    "policies": [],
                    "providers": [],
                }
                config_file.write_text(yaml.dump(config_data))
                await asyncio.sleep(0.1)  # Faster than debounce

            # Wait for debounce to complete
            await asyncio.sleep(0.5)

            # Should only have reloaded once (last change)
            current = config_manager.get_current_configuration()
            assert current["keys"][0]["key_id"] == "key-2"

            # Verify reload events (should be fewer than number of changes due to debouncing)
            reload_events = [
                event
                for event in observability_manager.events
                if event["event_type"] == "configuration_file_reloaded"
            ]
            # Due to debouncing, should have fewer reloads than changes
            assert len(reload_events) < 3

        finally:
            watcher.stop()

    @pytest.mark.asyncio
    async def test_invalid_file_change_handled(
        self, config_manager: ConfigurationManager, config_file: Path, observability_manager: MockObservabilityManager
    ) -> None:
        """Test that invalid file changes are handled gracefully."""
        await config_manager.load_configuration()

        watcher = ConfigurationFileWatcher(
            config_manager=config_manager,
            config_file_path=str(config_file),
            debounce_seconds=0.1,
            observability_manager=observability_manager,
        )

        try:
            watcher.start()

            # Write invalid YAML
            config_file.write_text("invalid: yaml: [syntax")

            # Wait for debounce and reload attempt
            await asyncio.sleep(0.3)

            # Verify error was logged
            error_logs = [
                log for log in observability_manager.logs if log["level"] == "ERROR"
            ]
            assert len(error_logs) >= 1

            # Configuration should not have changed
            current = config_manager.get_current_configuration()
            # Should still have the original key
            assert len(current["keys"]) == 1

        finally:
            watcher.stop()

    def test_ignores_other_files(
        self, config_manager: ConfigurationManager, config_file: Path, tmp_path: Path
    ) -> None:
        """Test that watcher ignores changes to other files."""
        watcher = ConfigurationFileWatcher(
            config_manager=config_manager,
            config_file_path=str(config_file),
        )

        try:
            watcher.start()

            # Create and modify another file in the same directory
            other_file = tmp_path / "other.yaml"
            other_file.write_text("test: data")

            # Modify the other file
            other_file.write_text("test: modified")

            # Watcher should still be running (no error from handling other file)
            assert watcher.is_watching() is True

        finally:
            watcher.stop()

    def test_ignores_directory_events(
        self, config_manager: ConfigurationManager, config_file: Path, tmp_path: Path
    ) -> None:
        """Test that watcher ignores directory events."""
        watcher = ConfigurationFileWatcher(
            config_manager=config_manager,
            config_file_path=str(config_file),
        )

        try:
            watcher.start()

            # Create a subdirectory (this would trigger a directory event)
            subdir = tmp_path / "subdir"
            subdir.mkdir()

            # Watcher should still be running
            assert watcher.is_watching() is True

        finally:
            watcher.stop()

