"""Tests for secure key storage practices."""

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from apikeyrouter.domain.components.key_manager import KeyManager, KeyNotFoundError
from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.state_store import StateStore
from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.infrastructure.observability.logger import sanitize_for_logging
from apikeyrouter.infrastructure.utils.encryption import EncryptionError


class MockStateStore(StateStore):
    """Mock StateStore for testing."""

    def __init__(self) -> None:
        """Initialize mock store."""
        self._keys: dict[str, APIKey] = {}

    async def save_key(self, key: APIKey) -> None:
        """Save key to mock store."""
        self._keys[key.id] = key

    async def get_key(self, key_id: str) -> APIKey | None:
        """Get key from mock store."""
        return self._keys.get(key_id)

    async def list_keys(self, provider_id: str | None = None) -> list[APIKey]:
        """List keys from mock store."""
        if provider_id:
            return [k for k in self._keys.values() if k.provider_id == provider_id]
        return list(self._keys.values())

    async def save_state_transition(self, transition: Any) -> None:
        """Mock implementation."""
        pass

    async def save_routing_decision(self, decision: Any) -> None:
        """Mock implementation."""
        pass

    async def save_quota_state(self, quota_state: Any) -> None:
        """Mock implementation."""
        pass

    async def get_quota_state(self, key_id: str) -> Any:
        """Mock implementation."""
        return None

    async def query_state(self, query: Any) -> list[Any]:
        """Mock implementation."""
        return []


class MockObservabilityManager(ObservabilityManager):
    """Mock ObservabilityManager for testing."""

    def __init__(self) -> None:
        """Initialize mock observability manager."""
        self.logs: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []

    async def emit_event(
        self, event_type: str, payload: dict[str, Any], metadata: dict[str, Any] | None = None
    ) -> None:
        """Record event."""
        self.events.append({"event_type": event_type, "payload": payload, "metadata": metadata or {}})

    async def log(self, level: str, message: str, context: dict[str, Any] | None = None) -> None:
        """Record log."""
        self.logs.append({"level": level, "message": message, "context": context or {}})


class TestSecureStorage:
    """Tests for secure key storage practices."""

    def setup_method(self) -> None:
        """Set up test environment."""
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key()
        os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = test_key.decode()

        self.state_store = MockStateStore()
        self.observability = MockObservabilityManager()
        self.key_manager = KeyManager(
            state_store=self.state_store,
            observability_manager=self.observability,
        )

    def teardown_method(self) -> None:
        """Clean up test environment."""
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)

    @pytest.mark.asyncio
    async def test_key_material_not_in_logs(self) -> None:
        """Test that key material never appears in logs."""
        secret_key = "sk-super-secret-test-key-12345"

        # Register key
        key = await self.key_manager.register_key(
            key_material=secret_key,
            provider_id="openai",
        )

        # Perform operations that generate logs
        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Throttled,
            reason="test",
        )

        # Check all logs and events
        all_log_text = " ".join(
            [
                str(log.get("message", "")) + " " + str(log.get("context", {}))
                for log in self.observability.logs
            ]
        )
        all_event_text = " ".join(
            [
                str(event.get("event_type", "")) + " " + str(event.get("payload", {}))
                for event in self.observability.events
            ]
        )
        all_text = all_log_text + " " + all_event_text

        # Verify secret key never appears
        assert secret_key not in all_text

    @pytest.mark.asyncio
    async def test_key_material_not_in_error_messages(self) -> None:
        """Test that key material is not exposed in error messages."""
        secret_key = "sk-secret-error-test-key-67890"

        # Register key
        key = await self.key_manager.register_key(
            key_material=secret_key,
            provider_id="openai",
        )

        # Try to get non-existent key (should raise error)
        try:
            await self.key_manager.get_key_material("non-existent-key-id")
            assert False, "Should have raised KeyNotFoundError"
        except KeyNotFoundError as e:
            error_message = str(e)
            # Error message should not contain key material
            assert secret_key not in error_message
            # But should contain key_id reference
            assert "non-existent-key-id" in error_message or "Key not found" in error_message

    @pytest.mark.asyncio
    async def test_api_key_to_safe_dict_excludes_key_material(self) -> None:
        """Test that to_safe_dict() excludes key_material."""
        secret_key = "sk-test-safe-dict-key"

        # Register key
        key = await self.key_manager.register_key(
            key_material=secret_key,
            provider_id="openai",
        )

        # Get safe dict representation
        safe_dict = key.to_safe_dict()

        # Verify key_material is not in the dict
        assert "key_material" not in safe_dict
        # Verify other fields are present
        assert "id" in safe_dict
        assert "provider_id" in safe_dict
        assert "state" in safe_dict
        # Verify secret key is not in any value
        assert secret_key not in str(safe_dict.values())

    @pytest.mark.asyncio
    async def test_secure_key_rotation_preserves_encryption(self) -> None:
        """Test that key rotation encrypts new key material."""
        old_key_material = "sk-old-key-material"
        new_key_material = "sk-new-key-material"

        # Register key
        key = await self.key_manager.register_key(
            key_material=old_key_material,
            provider_id="openai",
        )

        # Rotate key
        rotated_key = await self.key_manager.rotate_key(
            old_key_id=key.id,
            new_key_material=new_key_material,
        )

        # Verify rotated key has same ID
        assert rotated_key.id == key.id

        # Verify new key material is encrypted (not plaintext)
        assert rotated_key.key_material != new_key_material
        assert rotated_key.key_material != old_key_material
        assert len(rotated_key.key_material) > len(new_key_material)  # Encrypted is longer

        # Verify we can decrypt it
        decrypted = await self.key_manager.get_key_material(rotated_key.id)
        assert decrypted == new_key_material

    @pytest.mark.asyncio
    async def test_audit_trail_captures_key_access(self) -> None:
        """Test that audit trail captures key access (decryption) events."""
        secret_key = "sk-audit-test-key"

        # Register key
        key = await self.key_manager.register_key(
            key_material=secret_key,
            provider_id="openai",
        )

        # Clear events
        self.observability.events.clear()

        # Get key material (triggers decryption and audit event)
        decrypted = await self.key_manager.get_key_material(key.id)

        # Verify audit event was emitted
        key_access_events = [
            e for e in self.observability.events if e.get("event_type") == "key_access"
        ]
        assert len(key_access_events) > 0

        # Verify event details
        event = key_access_events[0]
        assert event["payload"]["key_id"] == key.id
        assert event["payload"]["operation"] == "decrypt"
        assert event["payload"]["result"] == "success"
        # Verify key_material field is not in payload (only access_type in metadata is OK)
        assert "key_material" not in event["payload"]
        # Verify secret key value is not in event
        assert secret_key not in str(event["payload"])
        assert secret_key not in str(event.get("metadata", {}))

    @pytest.mark.asyncio
    async def test_audit_trail_captures_failed_access(self) -> None:
        """Test that audit trail captures failed key access attempts."""
        # Create a key with invalid encrypted material
        invalid_key = APIKey(
            id="invalid-key",
            key_material="invalid-encrypted-data",
            provider_id="openai",
        )
        await self.state_store.save_key(invalid_key)

        # Clear events
        self.observability.events.clear()

        # Try to get key material (should fail)
        try:
            await self.key_manager.get_key_material("invalid-key")
            assert False, "Should have raised EncryptionError"
        except EncryptionError:
            pass

        # Verify audit event was emitted for failed access
        key_access_events = [
            e for e in self.observability.events if e.get("event_type") == "key_access"
        ]
        assert len(key_access_events) > 0

        # Verify event details
        event = key_access_events[0]
        assert event["payload"]["key_id"] == "invalid-key"
        assert event["payload"]["operation"] == "decrypt"
        assert event["payload"]["result"] == "failure"

    @pytest.mark.asyncio
    async def test_sanitize_for_logging_removes_key_material(self) -> None:
        """Test that sanitize_for_logging removes key_material from data structures."""
        data = {
            "key_id": "key-123",
            "key_material": "sk-secret-key",
            "provider_id": "openai",
            "nested": {
                "key_material": "sk-another-secret",
                "other_field": "value",
            },
        }

        sanitized = sanitize_for_logging(data)

        # Verify key_material is redacted
        assert sanitized["key_material"] == "[REDACTED]"
        assert sanitized["nested"]["key_material"] == "[REDACTED]"
        # Verify other fields are preserved
        assert sanitized["key_id"] == "key-123"
        assert sanitized["provider_id"] == "openai"
        assert sanitized["nested"]["other_field"] == "value"

    @pytest.mark.asyncio
    async def test_sanitize_for_logging_handles_lists(self) -> None:
        """Test that sanitize_for_logging handles lists correctly."""
        data = [
            {"key_id": "key-1", "key_material": "sk-secret-1"},
            {"key_id": "key-2", "key_material": "sk-secret-2"},
        ]

        sanitized = sanitize_for_logging(data)

        assert len(sanitized) == 2
        assert sanitized[0]["key_material"] == "[REDACTED]"
        assert sanitized[1]["key_material"] == "[REDACTED]"
        assert sanitized[0]["key_id"] == "key-1"
        assert sanitized[1]["key_id"] == "key-2"

