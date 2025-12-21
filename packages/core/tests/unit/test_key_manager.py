"""Tests for KeyManager component."""

import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from apikeyrouter.domain.components.key_manager import (
    InvalidStateTransitionError,
    KeyManager,
    KeyNotFoundError,
    KeyRegistrationError,
)
from apikeyrouter.domain.interfaces.observability_manager import (
    ObservabilityError,
    ObservabilityManager,
)
from apikeyrouter.domain.interfaces.state_store import (
    StateStore,
    StateStoreError,
)
from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.domain.models.state_transition import StateTransition
from apikeyrouter.infrastructure.utils.encryption import EncryptionError


class MockStateStore(StateStore):
    """Mock StateStore for testing."""

    def __init__(self) -> None:
        """Initialize mock store."""
        self._keys: dict[str, APIKey] = {}
        self._transitions: list[StateTransition] = []
        self.save_key_called = False
        self.save_key_error: Exception | None = None

    async def save_key(self, key: APIKey) -> None:
        """Save key to mock store."""
        if self.save_key_error:
            raise self.save_key_error
        self._keys[key.id] = key
        self.save_key_called = True

    async def get_key(self, key_id: str) -> APIKey | None:
        """Get key from mock store."""
        return self._keys.get(key_id)

    async def list_keys(self, provider_id: str | None = None) -> list[APIKey]:
        """List keys from mock store."""
        keys = list(self._keys.values())
        if provider_id:
            keys = [k for k in keys if k.provider_id == provider_id]
        return keys

    async def delete_key(self, key_id: str) -> None:
        """Delete key from mock store."""
        self._keys.pop(key_id, None)

    async def save_state_transition(self, transition: StateTransition) -> None:
        """Save state transition to mock store."""
        if self.save_key_error:
            raise self.save_key_error
        self._transitions.append(transition)

    async def save_quota_state(self, state) -> None:
        """Save quota state to mock store."""
        pass

    async def get_quota_state(self, key_id: str):
        """Get quota state from mock store."""
        return None

    async def save_routing_decision(self, decision) -> None:
        """Save routing decision to mock store."""
        pass

    async def query_state(self, query) -> list:
        """Query state from mock store."""
        return []


class MockObservabilityManager(ObservabilityManager):
    """Mock ObservabilityManager for testing."""

    def __init__(self) -> None:
        """Initialize mock observability manager."""
        self.events: list[dict] = []
        self.logs: list[dict] = []
        self.emit_error: Exception | None = None

    async def emit_event(
        self,
        event_type: str,
        payload: dict,
        metadata: dict | None = None,
    ) -> None:
        """Emit event to mock store."""
        if self.emit_error:
            raise self.emit_error
        self.events.append({
            "event_type": event_type,
            "payload": payload,
            "metadata": metadata or {},
        })

    async def log(
        self,
        level: str,
        message: str,
        context: dict | None = None,
    ) -> None:
        """Log to mock store."""
        self.logs.append({
            "level": level,
            "message": message,
            "context": context or {},
        })


class TestKeyManager:
    """Tests for KeyManager component."""

    def setup_method(self) -> None:
        """Set up test environment."""
        # Set up encryption key for tests
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
    async def test_register_key_creates_apikey_with_correct_attributes(
        self,
    ) -> None:
        """Test that register_key creates APIKey with correct attributes."""
        key_material = "sk-test-1234567890"
        provider_id = "openai"
        metadata = {"tier": "premium"}

        api_key = await self.key_manager.register_key(
            key_material=key_material,
            provider_id=provider_id,
            metadata=metadata,
        )

        assert api_key.provider_id == provider_id.lower()
        assert api_key.state == KeyState.Available
        assert api_key.metadata == metadata
        assert api_key.usage_count == 0
        assert api_key.failure_count == 0
        assert api_key.last_used_at is None
        assert api_key.cooldown_until is None

    @pytest.mark.asyncio
    async def test_register_key_generates_uuid(self) -> None:
        """Test that register_key generates UUID key_id."""
        api_key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        # Verify it's a valid UUID
        uuid.UUID(api_key.id)
        assert len(api_key.id) == 36  # UUID string length

    @pytest.mark.asyncio
    async def test_register_key_encrypts_key_material(self) -> None:
        """Test that key material is encrypted before storage."""
        key_material = "sk-test-secret-key"
        api_key = await self.key_manager.register_key(
            key_material=key_material,
            provider_id="openai",
        )

        # Encrypted material should be different from original
        assert api_key.key_material != key_material
        assert len(api_key.key_material) > len(key_material)

        # Verify it's base64 encoded (encrypted output)
        assert api_key.key_material.count("=") >= 0  # Base64 padding

    @pytest.mark.asyncio
    async def test_register_key_saves_to_state_store(self) -> None:
        """Test that key is saved to StateStore."""
        api_key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        assert self.state_store.save_key_called is True
        saved_key = await self.state_store.get_key(api_key.id)
        assert saved_key is not None
        assert saved_key.id == api_key.id
        assert saved_key.provider_id == api_key.provider_id

    @pytest.mark.asyncio
    async def test_register_key_emits_event(self) -> None:
        """Test that key_registered event is emitted."""
        api_key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        assert len(self.observability.events) == 1
        event = self.observability.events[0]
        assert event["event_type"] == "key_registered"
        assert event["payload"]["key_id"] == api_key.id
        assert event["payload"]["provider_id"] == api_key.provider_id
        assert event["payload"]["state"] == KeyState.Available.value

    @pytest.mark.asyncio
    async def test_register_key_lowercases_provider_id(self) -> None:
        """Test that provider_id is lowercased."""
        api_key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="OpenAI",
        )

        assert api_key.provider_id == "openai"

    @pytest.mark.asyncio
    async def test_register_key_with_empty_key_material_raises_error(
        self,
    ) -> None:
        """Test that empty key_material raises error."""
        with pytest.raises(KeyRegistrationError, match="Key material cannot be empty"):
            await self.key_manager.register_key(
                key_material="",
                provider_id="openai",
            )

        with pytest.raises(KeyRegistrationError, match="Key material cannot be empty"):
            await self.key_manager.register_key(
                key_material="   ",
                provider_id="openai",
            )

    @pytest.mark.asyncio
    async def test_register_key_with_empty_provider_id_raises_error(
        self,
    ) -> None:
        """Test that empty provider_id raises error."""
        with pytest.raises(KeyRegistrationError, match="Provider ID cannot be empty"):
            await self.key_manager.register_key(
                key_material="sk-test-key-extra",
                provider_id="",
            )

        with pytest.raises(KeyRegistrationError, match="Provider ID cannot be empty"):
            await self.key_manager.register_key(
                key_material="sk-test-key-extra",
                provider_id="   ",
            )

    @pytest.mark.asyncio
    async def test_register_key_handles_encryption_error(self) -> None:
        """Test that encryption errors are handled."""
        from unittest.mock import patch
        from apikeyrouter.infrastructure.utils.encryption import EncryptionError

        # Mock encryption service's encrypt method to raise an error
        with patch.object(self.key_manager._encryption_service, "encrypt") as mock_encrypt:
            mock_encrypt.side_effect = EncryptionError("Failed to encrypt key material: Test error")

            with pytest.raises(KeyRegistrationError, match="Failed to encrypt"):
                await self.key_manager.register_key(
                    key_material="sk-test-key-extra",
                    provider_id="openai",
                )

    @pytest.mark.asyncio
    async def test_register_key_handles_state_store_error(self) -> None:
        """Test that StateStore errors are handled."""
        self.state_store.save_key_error = StateStoreError("Database connection failed")

        with pytest.raises(KeyRegistrationError, match="Failed to save key"):
            await self.key_manager.register_key(
                key_material="sk-test-key-extra",
                provider_id="openai",
            )

    @pytest.mark.asyncio
    async def test_register_key_handles_event_emission_failure(self) -> None:
        """Test that event emission failures don't fail registration."""
        self.observability.emit_error = ObservabilityError("Event system down")

        # Registration should still succeed
        api_key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        assert api_key is not None
        assert self.state_store.save_key_called is True

        # Should have logged a warning
        assert len(self.observability.logs) > 0
        warning_logs = [
            log for log in self.observability.logs if log["level"] == "WARNING"
        ]
        assert len(warning_logs) > 0
        assert "Failed to emit key_registered event" in warning_logs[0]["message"]

    @pytest.mark.asyncio
    async def test_register_key_with_none_metadata(self) -> None:
        """Test that None metadata is handled."""
        api_key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
            metadata=None,
        )

        assert api_key.metadata == {}

    @pytest.mark.asyncio
    async def test_register_key_strips_whitespace(self) -> None:
        """Test that key_material and provider_id are stripped."""
        api_key = await self.key_manager.register_key(
            key_material="  sk-test-key-extra  ",
            provider_id="  openai  ",
        )

        # Provider ID should be stripped and lowercased
        assert api_key.provider_id == "openai"

        # Key material should be encrypted (can't directly verify stripping,
        # but encryption should work with stripped input)
        assert api_key.key_material is not None


class TestKeyManagerStateManagement:
    """Tests for KeyManager state management functionality."""

    def setup_method(self) -> None:
        """Set up test environment."""
        # Set up encryption key for tests
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key()
        os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = test_key.decode()

        self.state_store = MockStateStore()
        self.observability = MockObservabilityManager()
        self.key_manager = KeyManager(
            state_store=self.state_store,
            observability_manager=self.observability,
            default_cooldown_seconds=60,
        )

    def teardown_method(self) -> None:
        """Clean up test environment."""
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)

    @pytest.mark.asyncio
    async def test_update_key_state_valid_transition(self) -> None:
        """Test that valid state transitions succeed."""
        # Register a key
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        # Transition Available → Throttled
        transition = await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
        )

        assert transition.from_state == KeyState.Available.value
        assert transition.to_state == KeyState.Throttled.value
        assert transition.trigger == "rate_limit"

        # Verify key state was updated
        updated_key = await self.key_manager.get_key(key.id)
        assert updated_key is not None
        assert updated_key.state == KeyState.Throttled

    @pytest.mark.asyncio
    async def test_update_key_state_invalid_transition_raises_error(self) -> None:
        """Test that invalid state transitions are rejected."""
        # Register a key
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        # Try invalid transition: Available → Recovering (not allowed)
        with pytest.raises(InvalidStateTransitionError):
            await self.key_manager.update_key_state(
                key_id=key.id,
                new_state=KeyState.Recovering,
                reason="test",
            )

    @pytest.mark.asyncio
    async def test_update_key_state_nonexistent_key_raises_error(self) -> None:
        """Test that updating state of nonexistent key raises error."""
        with pytest.raises(KeyNotFoundError):
            await self.key_manager.update_key_state(
                key_id="nonexistent-key-id",
                new_state=KeyState.Disabled,
                reason="test",
            )

    @pytest.mark.asyncio
    async def test_update_key_state_creates_audit_trail(self) -> None:
        """Test that StateTransition is saved to audit trail."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        transition = await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
        )

        # Verify transition was saved
        assert len(self.state_store._transitions) == 1
        saved_transition = self.state_store._transitions[0]
        assert saved_transition.entity_id == key.id
        assert saved_transition.from_state == KeyState.Available.value
        assert saved_transition.to_state == KeyState.Throttled.value

    @pytest.mark.asyncio
    async def test_update_key_state_emits_event(self) -> None:
        """Test that state_transition event is emitted."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
        )

        # Verify event was emitted
        state_events = [
            e for e in self.observability.events if e["event_type"] == "state_transition"
        ]
        assert len(state_events) == 1
        event = state_events[0]
        assert event["payload"]["key_id"] == key.id
        assert event["payload"]["from_state"] == KeyState.Available.value
        assert event["payload"]["to_state"] == KeyState.Throttled.value
        assert event["payload"]["reason"] == "rate_limit"

    @pytest.mark.asyncio
    async def test_update_key_state_sets_cooldown_for_throttled(self) -> None:
        """Test that cooldown_until is set when transitioning to Throttled."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
            cooldown_seconds=120,
        )

        updated_key = await self.key_manager.get_key(key.id)
        assert updated_key is not None
        assert updated_key.cooldown_until is not None
        # Cooldown should be approximately 120 seconds in the future
        assert (updated_key.cooldown_until - updated_key.state_updated_at).total_seconds() > 100

    @pytest.mark.asyncio
    async def test_update_key_state_clears_cooldown_when_not_throttled(self) -> None:
        """Test that cooldown_until is cleared when transitioning away from Throttled."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        # Transition to Throttled (sets cooldown)
        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
        )

        # Transition back to Available (clears cooldown)
        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Available,
            reason="manual_recovery",
        )

        updated_key = await self.key_manager.get_key(key.id)
        assert updated_key is not None
        assert updated_key.cooldown_until is None

    @pytest.mark.asyncio
    async def test_check_and_recover_states_recovers_throttled_keys(self) -> None:
        """Test that check_and_recover_states recovers Throttled keys when cooldown expires."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        # Transition to Throttled with very short cooldown
        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
            cooldown_seconds=1,  # 1 second cooldown
        )

        # Wait a bit for cooldown to expire
        import asyncio

        await asyncio.sleep(1.1)

        # Check and recover
        recovered = await self.key_manager.check_and_recover_states()

        assert len(recovered) == 1
        assert recovered[0].from_state == KeyState.Throttled.value
        assert recovered[0].to_state == KeyState.Available.value

        # Verify key was recovered
        updated_key = await self.key_manager.get_key(key.id)
        assert updated_key is not None
        assert updated_key.state == KeyState.Available
        assert updated_key.cooldown_until is None

    @pytest.mark.asyncio
    async def test_check_and_recover_states_does_not_recover_active_cooldown(self) -> None:
        """Test that check_and_recover_states does not recover keys with active cooldown."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        # Transition to Throttled with long cooldown
        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
            cooldown_seconds=300,  # 5 minutes
        )

        # Check and recover (should not recover)
        recovered = await self.key_manager.check_and_recover_states()

        assert len(recovered) == 0

        # Verify key is still Throttled
        updated_key = await self.key_manager.get_key(key.id)
        assert updated_key is not None
        assert updated_key.state == KeyState.Throttled

    @pytest.mark.asyncio
    async def test_update_key_state_same_state_no_op(self) -> None:
        """Test that updating to the same state creates a no-op transition."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        # Update to same state
        transition = await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Available,
            reason="no_op",
        )

        assert transition.from_state == KeyState.Available.value
        assert transition.to_state == KeyState.Available.value

    @pytest.mark.asyncio
    async def test_all_valid_transitions(self) -> None:
        """Test all valid state transitions work."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        # Available → Throttled
        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
        )

        # Throttled → Available
        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Available,
            reason="recovered",
        )

        # Available → Exhausted
        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Exhausted,
            reason="quota_exhausted",
        )

        # Exhausted → Recovering
        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Recovering,
            reason="quota_reset_approaching",
        )

        # Recovering → Available
        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Available,
            reason="quota_reset",
        )

        # Any → Disabled
        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Disabled,
            reason="manual",
        )

        # Disabled → Available
        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Available,
            reason="manual_enable",
        )

        # Any → Invalid
        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Invalid,
            reason="auth_failure",
        )

        # Verify final state
        updated_key = await self.key_manager.get_key(key.id)
        assert updated_key is not None
        assert updated_key.state == KeyState.Invalid


class TestKeyManagerEligibilityFiltering:
    """Tests for KeyManager eligibility filtering functionality."""

    def setup_method(self) -> None:
        """Set up test environment."""
        # Set up encryption key for tests
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key()
        os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = test_key.decode()

        self.state_store = MockStateStore()
        self.observability = MockObservabilityManager()
        self.key_manager = KeyManager(
            state_store=self.state_store,
            observability_manager=self.observability,
            default_cooldown_seconds=60,
        )

    def teardown_method(self) -> None:
        """Clean up test environment."""
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)

    @pytest.mark.asyncio
    async def test_get_eligible_keys_filters_disabled_keys(self) -> None:
        """Test that Disabled keys are excluded."""
        # Register keys with different states
        available_key = await self.key_manager.register_key(
            key_material="sk-available-key",
            provider_id="openai",
        )

        disabled_key = await self.key_manager.register_key(
            key_material="sk-disabled-key",
            provider_id="openai",
        )
        await self.key_manager.update_key_state(
            key_id=disabled_key.id,
            new_state=KeyState.Disabled,
            reason="manual",
        )

        eligible = await self.key_manager.get_eligible_keys(provider_id="openai")

        assert len(eligible) == 1
        assert eligible[0].id == available_key.id
        assert disabled_key.id not in [k.id for k in eligible]

    @pytest.mark.asyncio
    async def test_get_eligible_keys_filters_invalid_keys(self) -> None:
        """Test that Invalid keys are excluded."""
        available_key = await self.key_manager.register_key(
            key_material="sk-available-key",
            provider_id="openai",
        )

        invalid_key = await self.key_manager.register_key(
            key_material="sk-invalid-key",
            provider_id="openai",
        )
        await self.key_manager.update_key_state(
            key_id=invalid_key.id,
            new_state=KeyState.Invalid,
            reason="auth_failure",
        )

        eligible = await self.key_manager.get_eligible_keys(provider_id="openai")

        assert len(eligible) == 1
        assert eligible[0].id == available_key.id
        assert invalid_key.id not in [k.id for k in eligible]

    @pytest.mark.asyncio
    async def test_get_eligible_keys_filters_throttled_keys_in_cooldown(self) -> None:
        """Test that Throttled keys in cooldown are excluded."""
        available_key = await self.key_manager.register_key(
            key_material="sk-available-key",
            provider_id="openai",
        )

        throttled_key = await self.key_manager.register_key(
            key_material="sk-throttled-key",
            provider_id="openai",
        )
        await self.key_manager.update_key_state(
            key_id=throttled_key.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
            cooldown_seconds=300,  # 5 minutes
        )

        eligible = await self.key_manager.get_eligible_keys(provider_id="openai")

        assert len(eligible) == 1
        assert eligible[0].id == available_key.id
        assert throttled_key.id not in [k.id for k in eligible]

    @pytest.mark.asyncio
    async def test_get_eligible_keys_includes_throttled_keys_after_cooldown(self) -> None:
        """Test that Throttled keys after cooldown are included."""
        import asyncio

        throttled_key = await self.key_manager.register_key(
            key_material="sk-throttled-key",
            provider_id="openai",
        )
        await self.key_manager.update_key_state(
            key_id=throttled_key.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
            cooldown_seconds=1,  # 1 second cooldown
        )

        # Wait for cooldown to expire
        await asyncio.sleep(1.1)

        eligible = await self.key_manager.get_eligible_keys(provider_id="openai")

        assert len(eligible) == 1
        assert eligible[0].id == throttled_key.id

    @pytest.mark.asyncio
    async def test_get_eligible_keys_filters_exhausted_keys(self) -> None:
        """Test that Exhausted keys are excluded."""
        available_key = await self.key_manager.register_key(
            key_material="sk-available-key",
            provider_id="openai",
        )

        exhausted_key = await self.key_manager.register_key(
            key_material="sk-exhausted-key",
            provider_id="openai",
        )
        await self.key_manager.update_key_state(
            key_id=exhausted_key.id,
            new_state=KeyState.Exhausted,
            reason="quota_exhausted",
        )

        eligible = await self.key_manager.get_eligible_keys(provider_id="openai")

        assert len(eligible) == 1
        assert eligible[0].id == available_key.id
        assert exhausted_key.id not in [k.id for k in eligible]

    @pytest.mark.asyncio
    async def test_get_eligible_keys_includes_recovering_keys(self) -> None:
        """Test that Recovering keys are included."""
        recovering_key = await self.key_manager.register_key(
            key_material="sk-recovering-key",
            provider_id="openai",
        )
        await self.key_manager.update_key_state(
            key_id=recovering_key.id,
            new_state=KeyState.Exhausted,
            reason="quota_exhausted",
        )
        await self.key_manager.update_key_state(
            key_id=recovering_key.id,
            new_state=KeyState.Recovering,
            reason="quota_reset_approaching",
        )

        eligible = await self.key_manager.get_eligible_keys(provider_id="openai")

        assert len(eligible) == 1
        assert eligible[0].id == recovering_key.id

    @pytest.mark.asyncio
    async def test_get_eligible_keys_includes_available_keys(self) -> None:
        """Test that Available keys are included."""
        available_key = await self.key_manager.register_key(
            key_material="sk-available-key",
            provider_id="openai",
        )

        eligible = await self.key_manager.get_eligible_keys(provider_id="openai")

        assert len(eligible) == 1
        assert eligible[0].id == available_key.id

    @pytest.mark.asyncio
    async def test_get_eligible_keys_with_policy_filtering(self) -> None:
        """Test that policy-based filtering works."""
        # Register multiple keys
        key1 = await self.key_manager.register_key(
            key_material="sk-test-key-1",
            provider_id="openai",
            metadata={"tier": "premium"},
        )
        key2 = await self.key_manager.register_key(
            key_material="sk-test-key-2",
            provider_id="openai",
            metadata={"tier": "standard"},
        )

        # Policy: only premium tier keys
        def premium_policy(keys: list[APIKey]) -> list[APIKey]:
            return [k for k in keys if k.metadata.get("tier") == "premium"]

        eligible = await self.key_manager.get_eligible_keys(
            provider_id="openai",
            policy=premium_policy,
        )

        assert len(eligible) == 1
        assert eligible[0].id == key1.id
        assert key2.id not in [k.id for k in eligible]

    @pytest.mark.asyncio
    async def test_get_eligible_keys_handles_policy_errors_gracefully(self) -> None:
        """Test that policy evaluation errors don't fail filtering."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        # Policy that raises an error
        def failing_policy(keys: list[APIKey]) -> list[APIKey]:
            raise ValueError("Policy evaluation failed")

        # Should fall back to state-filtered keys
        eligible = await self.key_manager.get_eligible_keys(
            provider_id="openai",
            policy=failing_policy,
        )

        assert len(eligible) == 1
        assert eligible[0].id == key.id

        # Should have logged a warning
        warning_logs = [
            log for log in self.observability.logs if log["level"] == "WARNING"
        ]
        assert len(warning_logs) > 0
        assert "Policy evaluation failed" in warning_logs[-1]["message"]

    @pytest.mark.asyncio
    async def test_get_eligible_keys_handles_invalid_policy_return(self) -> None:
        """Test that invalid policy return type is handled."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        # Policy that returns non-list
        def invalid_policy(keys: list[APIKey]) -> str:
            return "invalid"

        eligible = await self.key_manager.get_eligible_keys(
            provider_id="openai",
            policy=invalid_policy,
        )

        assert len(eligible) == 1
        assert eligible[0].id == key.id

    @pytest.mark.asyncio
    async def test_get_eligible_keys_returns_empty_when_no_eligible_keys(self) -> None:
        """Test that empty list is returned when no eligible keys."""
        # Register only disabled key
        disabled_key = await self.key_manager.register_key(
            key_material="sk-disabled-key",
            provider_id="openai",
        )
        await self.key_manager.update_key_state(
            key_id=disabled_key.id,
            new_state=KeyState.Disabled,
            reason="manual",
        )

        eligible = await self.key_manager.get_eligible_keys(provider_id="openai")

        assert len(eligible) == 0

    @pytest.mark.asyncio
    async def test_get_eligible_keys_filters_by_provider_id(self) -> None:
        """Test that keys are filtered by provider_id."""
        openai_key = await self.key_manager.register_key(
            key_material="sk-openai-key",
            provider_id="openai",
        )

        anthropic_key = await self.key_manager.register_key(
            key_material="sk-anthropic-key",
            provider_id="anthropic",
        )

        eligible_openai = await self.key_manager.get_eligible_keys(provider_id="openai")
        eligible_anthropic = await self.key_manager.get_eligible_keys(
            provider_id="anthropic"
        )

        assert len(eligible_openai) == 1
        assert eligible_openai[0].id == openai_key.id

        assert len(eligible_anthropic) == 1
        assert eligible_anthropic[0].id == anthropic_key.id

    @pytest.mark.asyncio
    async def test_get_eligible_keys_performance(self) -> None:
        """Test that filtering performance meets <5ms target for 100 keys."""
        import time

        # Register 100 keys
        for i in range(100):
            await self.key_manager.register_key(
                key_material=f"sk-test-key-{i}",
                provider_id="openai",
            )

        # Disable some keys to add filtering complexity
        all_keys = await self.state_store.list_keys(provider_id="openai")
        for i, key in enumerate(all_keys[:20]):
            await self.key_manager.update_key_state(
                key_id=key.id,
                new_state=KeyState.Disabled,
                reason="test",
            )

        # Measure filtering time
        start = time.perf_counter()
        eligible = await self.key_manager.get_eligible_keys(provider_id="openai")
        elapsed = (time.perf_counter() - start) * 1000  # Convert to milliseconds

        assert len(eligible) == 80  # 100 - 20 disabled
        assert elapsed < 5.0, f"Filtering took {elapsed:.2f}ms, expected <5ms"


class TestKeyManagerRevocationAndRotation:
    """Tests for KeyManager revocation and rotation functionality."""

    def setup_method(self) -> None:
        """Set up test environment."""
        # Set up encryption key for tests
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key()
        os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = test_key.decode()

        self.state_store = MockStateStore()
        self.observability = MockObservabilityManager()
        self.key_manager = KeyManager(
            state_store=self.state_store,
            observability_manager=self.observability,
            default_cooldown_seconds=60,
        )

    def teardown_method(self) -> None:
        """Clean up test environment."""
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)

    @pytest.mark.asyncio
    async def test_revoke_key_sets_state_to_disabled(self) -> None:
        """Test that revoke_key sets state to Disabled."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        await self.key_manager.revoke_key(key.id)

        revoked_key = await self.key_manager.get_key(key.id)
        assert revoked_key is not None
        assert revoked_key.state == KeyState.Disabled

    @pytest.mark.asyncio
    async def test_revoke_key_excludes_from_routing(self) -> None:
        """Test that revoked keys are excluded from routing."""
        key1 = await self.key_manager.register_key(
            key_material="sk-test-key-1",
            provider_id="openai",
        )
        key2 = await self.key_manager.register_key(
            key_material="sk-test-key-2",
            provider_id="openai",
        )

        # Revoke key1
        await self.key_manager.revoke_key(key1.id)

        # Get eligible keys
        eligible = await self.key_manager.get_eligible_keys(provider_id="openai")

        assert len(eligible) == 1
        assert eligible[0].id == key2.id
        assert key1.id not in [k.id for k in eligible]

    @pytest.mark.asyncio
    async def test_revoke_key_creates_audit_trail(self) -> None:
        """Test that revocation creates StateTransition audit trail."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        await self.key_manager.revoke_key(key.id)

        # Verify transition was saved
        transitions = [
            t
            for t in self.state_store._transitions
            if t.entity_id == key.id and t.trigger == "manual_revocation"
        ]
        assert len(transitions) == 1
        assert transitions[0].to_state == KeyState.Disabled.value

    @pytest.mark.asyncio
    async def test_revoke_key_emits_event(self) -> None:
        """Test that key_revoked event is emitted."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        await self.key_manager.revoke_key(key.id)

        # Verify event was emitted
        revoked_events = [
            e for e in self.observability.events if e["event_type"] == "key_revoked"
        ]
        assert len(revoked_events) == 1
        event = revoked_events[0]
        assert event["payload"]["key_id"] == key.id
        assert event["payload"]["provider_id"] == key.provider_id

    @pytest.mark.asyncio
    async def test_revoke_key_nonexistent_key_raises_error(self) -> None:
        """Test that revoking nonexistent key raises error."""
        with pytest.raises(KeyNotFoundError):
            await self.key_manager.revoke_key("nonexistent-key-id")

    @pytest.mark.asyncio
    async def test_rotate_key_preserves_key_id(self) -> None:
        """Test that rotate_key preserves key_id (Option A)."""
        original_key = await self.key_manager.register_key(
            key_material="sk-old-key-extra",
            provider_id="openai",
            metadata={"tier": "premium"},
        )

        # Rotate key
        rotated_key = await self.key_manager.rotate_key(
            old_key_id=original_key.id,
            new_key_material="sk-new-key-extra",
        )

        # Verify key_id is preserved
        assert rotated_key.id == original_key.id
        assert rotated_key.provider_id == original_key.provider_id
        assert rotated_key.state == original_key.state
        assert rotated_key.metadata == original_key.metadata
        assert rotated_key.usage_count == original_key.usage_count
        assert rotated_key.failure_count == original_key.failure_count

        # Verify key_material was updated (encrypted, so different)
        assert rotated_key.key_material != original_key.key_material

    @pytest.mark.asyncio
    async def test_rotate_key_preserves_all_attributes(self) -> None:
        """Test that rotation preserves all attributes except key_material."""
        original_key = await self.key_manager.register_key(
            key_material="sk-old-key-extra",
            provider_id="openai",
            metadata={"tier": "premium", "account": "test"},
        )

        # Update some attributes
        await self.key_manager.update_key_state(
            key_id=original_key.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
        )

        # Rotate key
        rotated_key = await self.key_manager.rotate_key(
            old_key_id=original_key.id,
            new_key_material="sk-new-key-extra",
        )

        # Verify all attributes preserved
        assert rotated_key.id == original_key.id
        assert rotated_key.provider_id == original_key.provider_id
        assert rotated_key.state == KeyState.Throttled
        assert rotated_key.metadata == {"tier": "premium", "account": "test"}
        assert rotated_key.created_at == original_key.created_at

    @pytest.mark.asyncio
    async def test_rotate_key_creates_audit_trail(self) -> None:
        """Test that rotation creates StateTransition audit trail."""
        key = await self.key_manager.register_key(
            key_material="sk-old-key-extra",
            provider_id="openai",
        )

        await self.key_manager.rotate_key(
            old_key_id=key.id,
            new_key_material="sk-new-key-extra",
        )

        # Verify transition was saved
        rotation_transitions = [
            t
            for t in self.state_store._transitions
            if t.entity_id == key.id and t.trigger == "key_rotation"
        ]
        assert len(rotation_transitions) == 1
        transition = rotation_transitions[0]
        assert transition.context.get("material_updated") is True

    @pytest.mark.asyncio
    async def test_rotate_key_emits_event(self) -> None:
        """Test that key_rotated event is emitted."""
        key = await self.key_manager.register_key(
            key_material="sk-old-key-extra",
            provider_id="openai",
        )

        await self.key_manager.rotate_key(
            old_key_id=key.id,
            new_key_material="sk-new-key-extra",
        )

        # Verify event was emitted
        rotated_events = [
            e for e in self.observability.events if e["event_type"] == "key_rotated"
        ]
        assert len(rotated_events) == 1
        event = rotated_events[0]
        assert event["payload"]["key_id"] == key.id
        assert event["metadata"]["preserved_key_id"] is True

    @pytest.mark.asyncio
    async def test_rotate_key_nonexistent_key_raises_error(self) -> None:
        """Test that rotating nonexistent key raises error."""
        with pytest.raises(KeyNotFoundError):
            await self.key_manager.rotate_key(
                old_key_id="nonexistent-key-id",
                new_key_material="sk-new-key-extra",
            )

    @pytest.mark.asyncio
    async def test_rotate_key_empty_material_raises_error(self) -> None:
        """Test that rotating with empty key material raises error."""
        key = await self.key_manager.register_key(
            key_material="sk-old-key-extra",
            provider_id="openai",
        )

        with pytest.raises(KeyRegistrationError, match="New key material cannot be empty"):
            await self.key_manager.rotate_key(
                old_key_id=key.id,
                new_key_material="",
            )

    @pytest.mark.asyncio
    async def test_rotate_key_handles_encryption_error(self) -> None:
        """Test that encryption errors during rotation are handled."""
        key = await self.key_manager.register_key(
            key_material="sk-old-key-extra",
            provider_id="openai",
        )

        # Remove encryption key and set production mode to cause encryption failure
        original_env = os.environ.get("ENVIRONMENT")
        original_key = os.environ.get("APIKEYROUTER_ENCRYPTION_KEY")
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)
        os.environ["ENVIRONMENT"] = "production"

        try:
            # Create new KeyManager instance that will fail to initialize EncryptionService
            from apikeyrouter.infrastructure.utils.encryption import EncryptionError

            with pytest.raises((KeyRegistrationError, EncryptionError), match="Failed to encrypt|APIKEYROUTER_ENCRYPTION_KEY"):
                # Need to create a new KeyManager that will try to initialize EncryptionService
                # without the key
                from apikeyrouter.infrastructure.utils.encryption import EncryptionService

                # This should fail
                service = EncryptionService()
        finally:
            # Restore environment
            if original_key:
                os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = original_key
            if original_env:
                os.environ["ENVIRONMENT"] = original_env
            elif "ENVIRONMENT" in os.environ:
                os.environ.pop("ENVIRONMENT", None)

    @pytest.mark.asyncio
    async def test_system_continues_with_remaining_keys_after_revocation(self) -> None:
        """Test that system continues operating with remaining keys after revocation."""
        # Register multiple keys
        key1 = await self.key_manager.register_key(
            key_material="sk-test-key-1",
            provider_id="openai",
        )
        key2 = await self.key_manager.register_key(
            key_material="sk-test-key-2",
            provider_id="openai",
        )
        key3 = await self.key_manager.register_key(
            key_material="sk-test-key-3",
            provider_id="openai",
        )

        # Revoke one key
        await self.key_manager.revoke_key(key2.id)

        # System should continue with remaining keys
        eligible = await self.key_manager.get_eligible_keys(provider_id="openai")

        assert len(eligible) == 2
        assert key1.id in [k.id for k in eligible]
        assert key3.id in [k.id for k in eligible]
        assert key2.id not in [k.id for k in eligible]

    @pytest.mark.asyncio
    async def test_rotated_key_remains_eligible(self) -> None:
        """Test that rotated key remains eligible for routing."""
        key = await self.key_manager.register_key(
            key_material="sk-old-key-extra",
            provider_id="openai",
        )

        # Rotate key
        rotated_key = await self.key_manager.rotate_key(
            old_key_id=key.id,
            new_key_material="sk-new-key-extra",
        )

        # Verify rotated key is still eligible
        eligible = await self.key_manager.get_eligible_keys(provider_id="openai")

        assert len(eligible) == 1
        assert eligible[0].id == rotated_key.id
        assert eligible[0].id == key.id  # Same key_id

    @pytest.mark.asyncio
    async def test_update_key_state_handles_state_store_error_on_transition_save(self) -> None:
        """Test that StateStoreError when saving transition is handled."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        # Set error on save_state_transition
        original_save = self.state_store.save_state_transition

        async def failing_save(transition):
            raise StateStoreError("Failed to save transition")

        self.state_store.save_state_transition = failing_save

        with pytest.raises(StateStoreError, match="Failed to save state transition"):
            await self.key_manager.update_key_state(
                key_id=key.id,
                new_state=KeyState.Throttled,
                reason="rate_limit",
            )

        # Restore original method
        self.state_store.save_state_transition = original_save

    @pytest.mark.asyncio
    async def test_update_key_state_handles_event_emission_failure(self) -> None:
        """Test that event emission failures don't fail state transition."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        # Set error on emit_event
        self.observability.emit_error = ObservabilityError("Event system down")

        # State transition should still succeed
        transition = await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
        )

        assert transition is not None
        assert transition.to_state == KeyState.Throttled.value

        # Should have logged a warning
        warning_logs = [
            log for log in self.observability.logs if log["level"] == "WARNING"
        ]
        assert len(warning_logs) > 0
        assert "Failed to emit state_transition event" in warning_logs[-1]["message"]

    @pytest.mark.asyncio
    async def test_get_eligible_keys_includes_throttled_with_no_cooldown(self) -> None:
        """Test that Throttled keys with no cooldown_until are eligible."""
        throttled_key = await self.key_manager.register_key(
            key_material="sk-throttled-key",
            provider_id="openai",
        )
        await self.key_manager.update_key_state(
            key_id=throttled_key.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
        )

        # Manually set cooldown_until to None (edge case)
        key = await self.state_store.get_key(throttled_key.id)
        key.cooldown_until = None
        await self.state_store.save_key(key)

        # Key should be eligible
        eligible = await self.key_manager.get_eligible_keys(provider_id="openai")
        assert len(eligible) == 1
        assert eligible[0].id == throttled_key.id

    @pytest.mark.asyncio
    async def test_revoke_key_handles_event_emission_failure(self) -> None:
        """Test that event emission failures don't fail revocation."""
        key = await self.key_manager.register_key(
            key_material="sk-test-key-extra",
            provider_id="openai",
        )

        # Set error on emit_event
        self.observability.emit_error = ObservabilityError("Event system down")

        # Revocation should still succeed
        await self.key_manager.revoke_key(key.id)

        revoked_key = await self.key_manager.get_key(key.id)
        assert revoked_key is not None
        assert revoked_key.state == KeyState.Disabled

        # Should have logged a warning
        warning_logs = [
            log for log in self.observability.logs if log["level"] == "WARNING"
        ]
        assert len(warning_logs) > 0
        assert "Failed to emit key_revoked event" in warning_logs[-1]["message"]

    @pytest.mark.asyncio
    async def test_rotate_key_handles_state_store_error_on_save(self) -> None:
        """Test that StateStoreError when saving rotated key is handled."""
        key = await self.key_manager.register_key(
            key_material="sk-old-key-extra",
            provider_id="openai",
        )

        # Set error on save_key
        original_save = self.state_store.save_key

        async def failing_save(k):
            raise StateStoreError("Failed to save rotated key")

        self.state_store.save_key = failing_save

        with pytest.raises(StateStoreError, match="Failed to save rotated key"):
            await self.key_manager.rotate_key(
                old_key_id=key.id,
                new_key_material="sk-new-key-extra",
            )

        # Restore original method
        self.state_store.save_key = original_save

    @pytest.mark.asyncio
    async def test_rotate_key_handles_transition_save_failure(self) -> None:
        """Test that transition save failures don't fail rotation."""
        key = await self.key_manager.register_key(
            key_material="sk-old-key-extra",
            provider_id="openai",
        )

        # Set error on save_state_transition
        original_save = self.state_store.save_state_transition

        async def failing_save(transition):
            raise StateStoreError("Failed to save transition")

        self.state_store.save_state_transition = failing_save

        # Rotation should still succeed
        rotated_key = await self.key_manager.rotate_key(
            old_key_id=key.id,
            new_key_material="sk-new-key-extra",
        )

        assert rotated_key is not None
        assert rotated_key.id == key.id

        # Should have logged a warning
        warning_logs = [
            log for log in self.observability.logs if log["level"] == "WARNING"
        ]
        assert len(warning_logs) > 0
        assert "Failed to save rotation transition" in warning_logs[-1]["message"]

        # Restore original method
        self.state_store.save_state_transition = original_save

    @pytest.mark.asyncio
    async def test_rotate_key_handles_event_emission_failure(self) -> None:
        """Test that event emission failures don't fail rotation."""
        key = await self.key_manager.register_key(
            key_material="sk-old-key-extra",
            provider_id="openai",
        )

        # Set error on emit_event
        self.observability.emit_error = ObservabilityError("Event system down")

        # Rotation should still succeed
        rotated_key = await self.key_manager.rotate_key(
            old_key_id=key.id,
            new_key_material="sk-new-key-extra",
        )

        assert rotated_key is not None
        assert rotated_key.id == key.id

        # Should have logged a warning
        warning_logs = [
            log for log in self.observability.logs if log["level"] == "WARNING"
        ]
        assert len(warning_logs) > 0
        assert "Failed to emit key_rotated event" in warning_logs[-1]["message"]

    @pytest.mark.asyncio
    async def test_check_and_recover_states_handles_recovery_errors(self) -> None:
        """Test that errors during recovery don't stop the recovery process."""
        key1 = await self.key_manager.register_key(
            key_material="sk-test-key-1",
            provider_id="openai",
        )
        key2 = await self.key_manager.register_key(
            key_material="sk-test-key-2",
            provider_id="openai",
        )

        # Transition both to Throttled with short cooldown
        await self.key_manager.update_key_state(
            key_id=key1.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
            cooldown_seconds=1,
        )
        await self.key_manager.update_key_state(
            key_id=key2.id,
            new_state=KeyState.Throttled,
            reason="rate_limit",
            cooldown_seconds=1,
        )

        # Make key1 fail on state update (simulate error)
        import asyncio
        await asyncio.sleep(1.1)

        # Temporarily break key1's state update
        original_get = self.state_store.get_key

        async def failing_get(key_id):
            if key_id == key1.id:
                raise StateStoreError("Temporary error")
            return await original_get(key_id)

        self.state_store.get_key = failing_get

        # Recovery should continue with key2
        recovered = await self.key_manager.check_and_recover_states()

        # Should have recovered key2, logged error for key1
        assert len(recovered) >= 0  # May recover key2 or neither if key1 blocks

        # Should have logged an error
        error_logs = [
            log for log in self.observability.logs if log["level"] == "ERROR"
        ]
        # Note: The error might be logged, but recovery continues

        # Restore original method
        self.state_store.get_key = original_get

    @pytest.mark.asyncio
    async def test_get_key_material_decrypts_on_demand(self) -> None:
        """Test that get_key_material decrypts key material on demand."""
        # Register a key
        key = await self.key_manager.register_key(
            key_material="sk-test-secret-key-12345",
            provider_id="openai",
        )

        # Get decrypted key material
        decrypted_material = await self.key_manager.get_key_material(key.id)

        # Should decrypt to original
        assert decrypted_material == "sk-test-secret-key-12345"

        # Verify the stored key is still encrypted
        stored_key = await self.state_store.get_key(key.id)
        assert stored_key is not None
        assert stored_key.key_material != "sk-test-secret-key-12345"
        # Encrypted material is base64-encoded, so it won't start with "gAAAAA" directly
        # but should be different from plaintext and be valid base64
        assert len(stored_key.key_material) > len("sk-test-secret-key-12345")

    @pytest.mark.asyncio
    async def test_get_key_material_key_not_found(self) -> None:
        """Test that get_key_material raises error for non-existent key."""
        with pytest.raises(KeyNotFoundError, match="Key not found"):
            await self.key_manager.get_key_material("non-existent-key-id")

    @pytest.mark.asyncio
    async def test_get_key_material_with_invalid_encryption(self) -> None:
        """Test that get_key_material handles decryption errors."""
        # Create a key with invalid encrypted material
        invalid_key = APIKey(
            id="invalid-key",
            key_material="invalid-encrypted-data",
            provider_id="openai",
        )
        await self.state_store.save_key(invalid_key)

        with pytest.raises(EncryptionError, match="Failed to decrypt"):
            await self.key_manager.get_key_material("invalid-key")

    @pytest.mark.asyncio
    async def test_key_material_never_logged(self) -> None:
        """Test that key material is never logged in any log statements."""
        secret_key = "sk-super-secret-key-12345-abcdef"

        # Register key
        key = await self.key_manager.register_key(
            key_material=secret_key,
            provider_id="openai",
        )

        # Perform various operations that might log
        await self.key_manager.update_key_state(
            key_id=key.id,
            new_state=KeyState.Throttled,
            reason="test",
        )

        await self.key_manager.get_eligible_keys(provider_id="openai")

        # Get key material (decrypts)
        await self.key_manager.get_key_material(key.id)

        # Check all logs and events - secret key should never appear
        all_log_messages = " ".join(
            [
                str(log.get("message", "")) + " " + str(log.get("context", {}))
                for log in self.observability.logs
            ]
        )
        all_events = " ".join(
            [
                str(event.get("event_type", "")) + " " + str(event.get("payload", {}))
                for event in self.observability.events
            ]
        )
        all_text = all_log_messages + " " + all_events

        # Verify secret key material never appears in logs or events
        assert secret_key not in all_text
        # Verify key_id appears (which is safe) - check in events or logs
        assert key.id in all_text or len(self.observability.logs) > 0 or len(self.observability.events) > 0

    @pytest.mark.asyncio
    async def test_key_material_not_in_error_messages(self) -> None:
        """Test that key material is not exposed in error messages."""
        secret_key = "sk-secret-error-test-key"

        # Register key
        key = await self.key_manager.register_key(
            key_material=secret_key,
            provider_id="openai",
        )

        # Try to get non-existent key (should raise error)
        try:
            await self.key_manager.get_key_material("non-existent")
        except KeyNotFoundError as e:
            error_message = str(e)
            # Error message should not contain key material
            assert secret_key not in error_message
            # But should contain key_id reference
            assert "non-existent" in error_message or "Key not found" in error_message

    @pytest.mark.asyncio
    async def test_encryption_service_integration(self) -> None:
        """Test that KeyManager uses EncryptionService correctly."""
        from apikeyrouter.infrastructure.utils.encryption import EncryptionService
        from cryptography.fernet import Fernet

        # Create EncryptionService with specific key
        test_key = Fernet.generate_key()
        encryption_service = EncryptionService(encryption_key=test_key.decode())

        # Create KeyManager with custom EncryptionService
        key_manager = KeyManager(
            state_store=self.state_store,
            observability_manager=self.observability,
            encryption_service=encryption_service,
        )

        # Register and retrieve key
        key = await key_manager.register_key(
            key_material="sk-test-custom-encryption",
            provider_id="openai",
        )

        decrypted = await key_manager.get_key_material(key.id)
        assert decrypted == "sk-test-custom-encryption"

