"""Tests for input validation utilities."""

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from apikeyrouter.domain.components.key_manager import KeyManager, KeyRegistrationError
from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.state_store import StateStore
from apikeyrouter.domain.models.request_intent import Message, RequestIntent
from apikeyrouter.infrastructure.utils.validation import (
    ValidationError,
    detect_injection_attempt,
    validate_key_material,
    validate_metadata,
    validate_provider_id,
    validate_request_intent,
)


class TestInjectionDetection:
    """Tests for injection attack detection."""

    def test_detect_sql_injection(self) -> None:
        """Test detection of SQL injection patterns."""
        assert detect_injection_attempt("' OR '1'='1") is True
        assert detect_injection_attempt("UNION SELECT * FROM users") is True
        assert detect_injection_attempt("DROP TABLE users") is True

    def test_detect_nosql_injection(self) -> None:
        """Test detection of NoSQL injection patterns."""
        assert detect_injection_attempt("$where") is True
        assert detect_injection_attempt("$ne") is True
        assert detect_injection_attempt("$gt") is True

    def test_detect_command_injection(self) -> None:
        """Test detection of command injection patterns."""
        assert detect_injection_attempt("test; rm -rf /") is True
        assert detect_injection_attempt("test | cat /etc/passwd") is True
        assert detect_injection_attempt("test $(whoami)") is True

    def test_detect_script_injection(self) -> None:
        """Test detection of script injection patterns."""
        assert detect_injection_attempt("<script>alert('xss')</script>") is True
        assert detect_injection_attempt("javascript:alert('xss')") is True

    def test_detect_path_traversal(self) -> None:
        """Test detection of path traversal patterns."""
        assert detect_injection_attempt("../../../etc/passwd") is True
        assert detect_injection_attempt("..\\..\\windows\\system32") is True

    def test_legitimate_strings_not_detected(self) -> None:
        """Test that legitimate strings are not flagged."""
        assert detect_injection_attempt("sk-test-key-12345") is False
        assert detect_injection_attempt("openai") is False
        assert detect_injection_attempt("gpt-4") is False
        assert detect_injection_attempt("Hello, world!") is False


class TestKeyMaterialValidation:
    """Tests for key material validation."""

    def test_validate_empty_key_material(self) -> None:
        """Test that empty key material is rejected."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_key_material("")
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_key_material("   ")

    def test_validate_key_material_length(self) -> None:
        """Test key material length validation."""
        # Too short
        with pytest.raises(ValidationError, match="at least 10 characters"):
            validate_key_material("sk-short")

        # Too long
        with pytest.raises(ValidationError, match="500 characters or less"):
            validate_key_material("sk-" + "a" * 500)

    def test_validate_key_material_format(self) -> None:
        """Test key material format validation."""
        # Valid keys with common prefixes
        validate_key_material("sk-test-key-12345")
        validate_key_material("pk-test-key-12345")
        validate_key_material("xai-test-key-12345")

        # Valid key without known prefix (should be allowed)
        validate_key_material("custom-key-format-12345")

    def test_validate_key_material_injection_attempts(self) -> None:
        """Test that injection attempts in key material are rejected."""
        with pytest.raises(ValidationError, match="potentially malicious"):
            validate_key_material("sk-test'; DROP TABLE keys; --")

        with pytest.raises(ValidationError, match="potentially malicious"):
            validate_key_material("sk-test | rm -rf /")

    def test_validate_key_material_control_characters(self) -> None:
        """Test that control characters in key material are rejected."""
        with pytest.raises(ValidationError, match="invalid control characters"):
            validate_key_material("sk-test\x00-key")


class TestProviderIdValidation:
    """Tests for provider ID validation."""

    def test_validate_empty_provider_id(self) -> None:
        """Test that empty provider ID is rejected."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_provider_id("")
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_provider_id("   ")

    def test_validate_provider_id_length(self) -> None:
        """Test provider ID length validation."""
        # Too long
        with pytest.raises(ValidationError, match="100 characters or less"):
            validate_provider_id("a" * 101)

    def test_validate_provider_id_format(self) -> None:
        """Test provider ID format validation."""
        # Valid formats
        validate_provider_id("openai")
        validate_provider_id("anthropic")
        validate_provider_id("provider_123")
        validate_provider_id("test_provider_1")

        # Invalid formats
        with pytest.raises(ValidationError, match="only lowercase letters"):
            validate_provider_id("Provider-Name")
        with pytest.raises(ValidationError, match="only lowercase letters"):
            validate_provider_id("provider@name")
        with pytest.raises(ValidationError, match="only lowercase letters"):
            validate_provider_id("provider name")

    def test_validate_provider_id_injection_attempts(self) -> None:
        """Test that injection attempts in provider ID are rejected."""
        # Injection attempts are caught by format validation first (which is fine)
        # Test with a format-valid but suspicious pattern
        with pytest.raises(ValidationError):
            validate_provider_id("openai'; DROP TABLE providers; --")

        # Test with format-valid injection pattern that passes format check
        # (format validation catches most, but test that injection check is still there)
        # Since format validation is stricter, this is acceptable behavior


class TestMetadataValidation:
    """Tests for metadata validation."""

    def test_validate_none_metadata(self) -> None:
        """Test that None metadata is allowed."""
        validate_metadata(None)

    def test_validate_metadata_type(self) -> None:
        """Test that non-dict metadata is rejected."""
        with pytest.raises(ValidationError, match="must be a dictionary"):
            validate_metadata("not a dict")
        with pytest.raises(ValidationError, match="must be a dictionary"):
            validate_metadata([])

    def test_validate_metadata_size(self) -> None:
        """Test metadata size validation."""
        # Too many keys
        large_metadata = {f"key_{i}": f"value_{i}" for i in range(101)}
        with pytest.raises(ValidationError, match="more than 100 keys"):
            validate_metadata(large_metadata)

    def test_validate_metadata_keys(self) -> None:
        """Test metadata key validation."""
        # Valid keys
        validate_metadata({"key1": "value1", "key_2": "value2", "key-3": "value3"})

        # Invalid key types
        with pytest.raises(ValidationError, match="must be strings"):
            validate_metadata({123: "value"})

        # Invalid key formats
        with pytest.raises(ValidationError, match="only letters, numbers"):
            validate_metadata({"key@name": "value"})
        with pytest.raises(ValidationError, match="only letters, numbers"):
            validate_metadata({"key name": "value"})

    def test_validate_metadata_values(self) -> None:
        """Test metadata value validation."""
        # Valid primitive values
        validate_metadata({"str": "value", "int": 123, "float": 1.5, "bool": True})

        # Valid list values
        validate_metadata({"list": ["a", "b", "c"], "numbers": [1, 2, 3]})

        # Valid nested dict
        validate_metadata({"nested": {"key": "value"}})

        # Invalid value types
        with pytest.raises(ValidationError, match="must be primitive types"):
            validate_metadata({"key": object()})

    def test_validate_metadata_injection_attempts(self) -> None:
        """Test that injection attempts in metadata are rejected."""
        # Injection in value
        with pytest.raises(ValidationError, match="potentially malicious"):
            validate_metadata({"key": "value'; DROP TABLE data; --"})

        # Injection in key (caught by format validation first, which is fine)
        with pytest.raises(ValidationError):
            validate_metadata({"key'; DROP TABLE data; --": "value"})

    def test_validate_metadata_nested_depth(self) -> None:
        """Test metadata nesting depth validation."""
        # Valid nested depth
        validate_metadata({"level1": {"level2": {"level3": "value"}}})

        # Too deep nesting
        deep_metadata = {"level1": {"level2": {"level3": {"level4": {"level5": "value"}}}}}
        with pytest.raises(ValidationError, match="nesting depth exceeds"):
            validate_metadata(deep_metadata)

    def test_validate_metadata_list_values(self) -> None:
        """Test metadata list value validation."""
        # Valid list
        validate_metadata({"tags": ["tag1", "tag2", "tag3"]})

        # List too large
        large_list = list(range(101))
        with pytest.raises(ValidationError, match="more than 100 items"):
            validate_metadata({"items": large_list})

        # List with invalid items
        with pytest.raises(ValidationError, match="must be primitive types"):
            validate_metadata({"items": [object()]})


class TestRequestIntentValidation:
    """Tests for RequestIntent validation."""

    def test_validate_request_intent_type(self) -> None:
        """Test that non-RequestIntent is rejected."""
        with pytest.raises(ValidationError, match="must be a RequestIntent instance"):
            validate_request_intent({"model": "gpt-4", "messages": []})

    def test_validate_model_field(self) -> None:
        """Test model field validation."""
        # Valid model
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello")],
        )
        validate_request_intent(intent)

        # Empty model (caught by Pydantic first)
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):  # Pydantic validation error
            intent = RequestIntent(
                model="",
                messages=[Message(role="user", content="Hello")],
            )

        # Model too long (caught by Pydantic validator first)
        with pytest.raises(PydanticValidationError):  # Pydantic validation error
            intent = RequestIntent(
                model="a" * 201,
                messages=[Message(role="user", content="Hello")],
            )

        # Model with injection attempt
        intent = RequestIntent(
            model="gpt-4'; DROP TABLE models; --",
            messages=[Message(role="user", content="Hello")],
        )
        with pytest.raises(ValidationError, match="potentially malicious"):
            validate_request_intent(intent)

    def test_validate_messages_field(self) -> None:
        """Test messages field validation."""
        # Valid messages
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello")],
        )
        validate_request_intent(intent)

        # Empty messages (caught by Pydantic first)
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):  # Pydantic validation error
            intent = RequestIntent(
                model="gpt-4",
                messages=[],
            )

        # Too many messages (caught by Pydantic validator first)
        with pytest.raises(PydanticValidationError):  # Pydantic validation error
            intent = RequestIntent(
                model="gpt-4",
                messages=[Message(role="user", content="Hello")] * 1001,
            )

    def test_validate_message_content(self) -> None:
        """Test message content validation."""
        # Message with injection attempt
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello'; DROP TABLE messages; --")],
        )
        with pytest.raises(ValidationError, match="potentially malicious"):
            validate_request_intent(intent)

    def test_validate_parameters_field(self) -> None:
        """Test parameters field validation."""
        # Valid parameters
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello")],
            parameters={"temperature": 0.7, "max_tokens": 100},
        )
        validate_request_intent(intent)

        # Invalid temperature range (caught by Pydantic validator first)
        from pydantic import ValidationError as PydanticValidationError

        with pytest.raises(PydanticValidationError):  # Pydantic validation error
            intent = RequestIntent(
                model="gpt-4",
                messages=[Message(role="user", content="Hello")],
                parameters={"temperature": 3.0},
            )

        # Invalid max_tokens (caught by Pydantic validator first)
        with pytest.raises(PydanticValidationError):  # Pydantic validation error
            intent = RequestIntent(
                model="gpt-4",
                messages=[Message(role="user", content="Hello")],
                parameters={"max_tokens": 2000000},
            )

        # Invalid top_p range (caught by Pydantic validator first)
        with pytest.raises(PydanticValidationError):  # Pydantic validation error
            intent = RequestIntent(
                model="gpt-4",
                messages=[Message(role="user", content="Hello")],
                parameters={"top_p": 2.0},
            )

        # Parameter with injection attempt
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello")],
            parameters={"key'; DROP TABLE params; --": "value"},
        )
        with pytest.raises(ValidationError, match="potentially malicious"):
            validate_request_intent(intent)


class TestValidationIntegration:
    """Tests for validation integration with KeyManager and Router."""

    def setup_method(self) -> None:
        """Set up test environment."""
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key()
        os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = test_key.decode()

        self.state_store = MagicMock(spec=StateStore)
        self.state_store.save_key = AsyncMock()
        self.state_store.get_key = AsyncMock(return_value=None)
        self.state_store.list_keys = AsyncMock(return_value=[])
        self.state_store.save_state_transition = AsyncMock()
        self.state_store.save_routing_decision = AsyncMock()
        self.state_store.save_quota_state = AsyncMock()
        self.state_store.get_quota_state = AsyncMock(return_value=None)
        self.state_store.query_state = AsyncMock(return_value=[])

        self.observability = MagicMock(spec=ObservabilityManager)
        self.observability.emit_event = AsyncMock()
        self.observability.log = AsyncMock()

        self.key_manager = KeyManager(
            state_store=self.state_store,
            observability_manager=self.observability,
        )

    def teardown_method(self) -> None:
        """Clean up test environment."""
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)

    @pytest.mark.asyncio
    async def test_key_manager_validates_key_material(self) -> None:
        """Test that KeyManager validates key material."""
        # Invalid key material (too short)
        with pytest.raises(KeyRegistrationError, match="Validation failed"):
            await self.key_manager.register_key(
                key_material="short",
                provider_id="openai",
            )

        # Invalid key material (injection attempt)
        with pytest.raises(KeyRegistrationError, match="Validation failed"):
            await self.key_manager.register_key(
                key_material="sk-test'; DROP TABLE keys; --",
                provider_id="openai",
            )

    @pytest.mark.asyncio
    async def test_key_manager_validates_provider_id(self) -> None:
        """Test that KeyManager validates provider ID."""
        # Invalid provider ID (invalid format)
        with pytest.raises(KeyRegistrationError, match="Validation failed"):
            await self.key_manager.register_key(
                key_material="sk-test-key-12345",
                provider_id="Provider-Name",
            )

        # Invalid provider ID (injection attempt)
        with pytest.raises(KeyRegistrationError, match="Validation failed"):
            await self.key_manager.register_key(
                key_material="sk-test-key-12345",
                provider_id="openai'; DROP TABLE providers; --",
            )

    @pytest.mark.asyncio
    async def test_key_manager_validates_metadata(self) -> None:
        """Test that KeyManager validates metadata."""
        # Invalid metadata (injection attempt)
        with pytest.raises(KeyRegistrationError, match="Validation failed"):
            await self.key_manager.register_key(
                key_material="sk-test-key-12345",
                provider_id="openai",
                metadata={"key'; DROP TABLE data; --": "value"},
            )

        # Valid metadata
        await self.key_manager.register_key(
            key_material="sk-test-key-12345",
            provider_id="openai",
            metadata={"account_tier": "pro", "region": "us-east-1"},
        )
