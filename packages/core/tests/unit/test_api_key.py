"""Tests for APIKey data model."""

from datetime import datetime, timedelta

import pytest

from apikeyrouter.domain.models.api_key import APIKey, KeyState


class TestKeyState:
    """Tests for KeyState enum."""

    def test_keystate_enum_values(self) -> None:
        """Test that all KeyState enum values are defined."""
        assert KeyState.Available == "available"
        assert KeyState.Throttled == "throttled"
        assert KeyState.Exhausted == "exhausted"
        assert KeyState.Disabled == "disabled"
        assert KeyState.Invalid == "invalid"

    def test_keystate_enum_membership(self) -> None:
        """Test KeyState enum membership."""
        assert "available" in [state.value for state in KeyState]
        assert "throttled" in [state.value for state in KeyState]
        assert "exhausted" in [state.value for state in KeyState]
        assert "disabled" in [state.value for state in KeyState]
        assert "invalid" in [state.value for state in KeyState]


class TestAPIKey:
    """Tests for APIKey model."""

    def test_apikey_creation_with_minimal_fields(self) -> None:
        """Test APIKey creation with only required fields."""
        key = APIKey(
            id="test_key_1",
            key_material="encrypted_key_material",
            provider_id="openai",
        )

        assert key.id == "test_key_1"
        assert key.key_material == "encrypted_key_material"
        assert key.provider_id == "openai"
        assert key.state == KeyState.Available
        assert key.usage_count == 0
        assert key.failure_count == 0
        assert key.last_used_at is None
        assert key.cooldown_until is None
        assert key.metadata == {}
        assert isinstance(key.created_at, datetime)
        assert isinstance(key.state_updated_at, datetime)

    def test_apikey_creation_with_all_fields(self) -> None:
        """Test APIKey creation with all fields."""
        now = datetime.utcnow()
        cooldown = now + timedelta(minutes=5)

        key = APIKey(
            id="test_key_2",
            key_material="encrypted_key_material",
            provider_id="anthropic",
            state=KeyState.Throttled,
            created_at=now,
            state_updated_at=now,
            last_used_at=now,
            usage_count=100,
            failure_count=5,
            cooldown_until=cooldown,
            metadata={"tier": "premium", "account": "test_account"},
        )

        assert key.id == "test_key_2"
        assert key.provider_id == "anthropic"
        assert key.state == KeyState.Throttled
        assert key.usage_count == 100
        assert key.failure_count == 5
        assert key.last_used_at == now
        assert key.cooldown_until == cooldown
        assert key.metadata == {"tier": "premium", "account": "test_account"}

    def test_apikey_default_values(self) -> None:
        """Test that APIKey has correct default values."""
        key = APIKey(
            id="test_key_3",
            key_material="encrypted_key_material",
            provider_id="openai",
        )

        assert key.state == KeyState.Available
        assert key.usage_count == 0
        assert key.failure_count == 0
        assert key.last_used_at is None
        assert key.cooldown_until is None
        assert key.metadata == {}

    def test_apikey_id_validation(self) -> None:
        """Test APIKey ID validation."""
        # Valid ID
        key = APIKey(
            id="valid-key-id-123",
            key_material="encrypted_key_material",
            provider_id="openai",
        )
        assert key.id == "valid-key-id-123"

        # Empty ID should raise error (Pydantic Field validation)
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            APIKey(
                id="",
                key_material="encrypted_key_material",
                provider_id="openai",
            )

        # Whitespace-only ID should be stripped and then raise error
        with pytest.raises(ValidationError):
            APIKey(
                id="   ",
                key_material="encrypted_key_material",
                provider_id="openai",
            )

        # ID too long should raise error
        long_id = "a" * 256
        with pytest.raises(ValueError, match="Key ID must be 255 characters or less"):
            APIKey(
                id=long_id,
                key_material="encrypted_key_material",
                provider_id="openai",
            )

    def test_apikey_provider_id_validation(self) -> None:
        """Test APIKey provider_id validation."""
        # Valid provider ID
        key = APIKey(
            id="test_key",
            key_material="encrypted_key_material",
            provider_id="openai",
        )
        assert key.provider_id == "openai"

        # Provider ID should be lowercased
        key = APIKey(
            id="test_key",
            key_material="encrypted_key_material",
            provider_id="OpenAI",
        )
        assert key.provider_id == "openai"

        # Empty provider ID should raise error (Pydantic Field validation)
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            APIKey(
                id="test_key",
                key_material="encrypted_key_material",
                provider_id="",
            )

        # Provider ID too long should raise error
        long_provider = "a" * 101
        with pytest.raises(ValueError, match="Provider ID must be 100 characters or less"):
            APIKey(
                id="test_key",
                key_material="encrypted_key_material",
                provider_id=long_provider,
            )

    def test_apikey_usage_count_validation(self) -> None:
        """Test APIKey usage_count validation."""
        # Valid usage count
        key = APIKey(
            id="test_key",
            key_material="encrypted_key_material",
            provider_id="openai",
            usage_count=100,
        )
        assert key.usage_count == 100

        # Negative usage count should raise error
        with pytest.raises(ValueError):
            APIKey(
                id="test_key",
                key_material="encrypted_key_material",
                provider_id="openai",
                usage_count=-1,
            )

    def test_apikey_failure_count_validation(self) -> None:
        """Test APIKey failure_count validation."""
        # Valid failure count
        key = APIKey(
            id="test_key",
            key_material="encrypted_key_material",
            provider_id="openai",
            failure_count=5,
        )
        assert key.failure_count == 5

        # Negative failure count should raise error
        with pytest.raises(ValueError):
            APIKey(
                id="test_key",
                key_material="encrypted_key_material",
                provider_id="openai",
                failure_count=-1,
            )

    def test_apikey_state_transition_validation(self) -> None:
        """Test APIKey state transition validation."""
        # Key with Throttled state and cooldown_until set
        cooldown = datetime.utcnow() + timedelta(minutes=5)
        key = APIKey(
            id="test_key",
            key_material="encrypted_key_material",
            provider_id="openai",
            state=KeyState.Throttled,
            cooldown_until=cooldown,
        )
        assert key.state == KeyState.Throttled
        assert key.cooldown_until == cooldown

        # Key with non-Throttled state should clear cooldown_until
        key = APIKey(
            id="test_key",
            key_material="encrypted_key_material",
            provider_id="openai",
            state=KeyState.Available,
            cooldown_until=cooldown,
        )
        assert key.state == KeyState.Available
        assert key.cooldown_until is None

    def test_apikey_repr_no_key_material(self) -> None:
        """Test that APIKey __repr__ never exposes key material."""
        key = APIKey(
            id="test_key",
            key_material="sensitive-key-material",
            provider_id="openai",
            usage_count=10,
            failure_count=2,
        )

        repr_str = repr(key)
        assert "sensitive-key-material" not in repr_str
        assert "test_key" in repr_str
        assert "openai" in repr_str
        assert "10" in repr_str
        assert "2" in repr_str

    def test_apikey_all_states(self) -> None:
        """Test APIKey with all possible states."""
        states = [
            KeyState.Available,
            KeyState.Throttled,
            KeyState.Exhausted,
            KeyState.Disabled,
            KeyState.Invalid,
        ]

        for state in states:
            key = APIKey(
                id=f"test_key_{state.value}",
                key_material="encrypted_key_material",
                provider_id="openai",
                state=state,
            )
            assert key.state == state
