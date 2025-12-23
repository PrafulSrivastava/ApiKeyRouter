"""Tests for encryption utilities."""

import os

import pytest

from apikeyrouter.infrastructure.utils.encryption import (
    EncryptionError,
    EncryptionService,
    decrypt_key_material,
    encrypt_key_material,
)


class TestEncryption:
    """Tests for encryption utilities."""

    def setup_method(self) -> None:
        """Set up test environment."""
        # Generate a test encryption key
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key()
        os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = test_key.decode()

    def teardown_method(self) -> None:
        """Clean up test environment."""
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)
        os.environ.pop("APIKEYROUTER_ENCRYPTION_SALT", None)

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """Test that encryption and decryption work correctly."""
        original_key = "sk-test-1234567890abcdef"

        encrypted = encrypt_key_material(original_key)
        assert encrypted != original_key
        assert len(encrypted) > 0

        decrypted = decrypt_key_material(encrypted)
        assert decrypted == original_key

    def test_encrypt_different_keys_produce_different_output(self) -> None:
        """Test that encrypting different keys produces different output."""
        key1 = "sk-test-key-1"
        key2 = "sk-test-key-2"

        encrypted1 = encrypt_key_material(key1)
        encrypted2 = encrypt_key_material(key2)

        assert encrypted1 != encrypted2

    def test_encrypt_same_key_produces_different_output(self) -> None:
        """Test that encrypting the same key produces different output (due to IV)."""
        key = "sk-test-key"

        encrypted1 = encrypt_key_material(key)
        encrypted2 = encrypt_key_material(key)

        # Should be different due to random IV, but decrypt to same value
        assert encrypted1 != encrypted2
        assert decrypt_key_material(encrypted1) == decrypt_key_material(encrypted2)

    def test_encrypt_without_key_raises_error(self) -> None:
        """Test that encryption fails without encryption key."""
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)

        with pytest.raises(EncryptionError, match="APIKEYROUTER_ENCRYPTION_KEY"):
            encrypt_key_material("sk-test")

    def test_decrypt_without_key_raises_error(self) -> None:
        """Test that decryption fails without encryption key."""
        # First encrypt with a key
        original_key = "sk-test"
        encrypted = encrypt_key_material(original_key)

        # Remove the key
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)

        with pytest.raises(EncryptionError, match="APIKEYROUTER_ENCRYPTION_KEY"):
            decrypt_key_material(encrypted)

    def test_decrypt_invalid_data_raises_error(self) -> None:
        """Test that decrypting invalid data raises error."""
        with pytest.raises(EncryptionError, match="Failed to decrypt"):
            decrypt_key_material("invalid-encrypted-data")

    def test_encrypt_with_password_derived_key(self) -> None:
        """Test encryption with password-derived key."""
        # Use a password instead of a Fernet key
        os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = "my-secret-password"
        os.environ["APIKEYROUTER_ENCRYPTION_SALT"] = "test-salt"

        original_key = "sk-test-key"

        encrypted = encrypt_key_material(original_key)
        decrypted = decrypt_key_material(encrypted)

        assert decrypted == original_key

    def test_encrypt_empty_string(self) -> None:
        """Test encryption of empty string."""
        encrypted = encrypt_key_material("")
        decrypted = decrypt_key_material(encrypted)
        assert decrypted == ""

    def test_encrypt_long_key(self) -> None:
        """Test encryption of long key material."""
        long_key = "sk-" + "a" * 1000
        encrypted = encrypt_key_material(long_key)
        decrypted = decrypt_key_material(encrypted)
        assert decrypted == long_key

    def test_encryption_service_encrypt_decrypt_roundtrip(self) -> None:
        """Test EncryptionService encrypt/decrypt roundtrip."""
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key()
        service = EncryptionService(encryption_key=test_key.decode())

        original_key = "sk-test-1234567890abcdef"
        encrypted_bytes = service.encrypt(original_key)
        assert isinstance(encrypted_bytes, bytes)
        assert encrypted_bytes != original_key.encode()

        decrypted = service.decrypt(encrypted_bytes)
        assert decrypted == original_key

    def test_encryption_service_with_environment_key(self) -> None:
        """Test EncryptionService loads key from environment."""
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key()
        os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = test_key.decode()

        service = EncryptionService()  # Should load from environment
        original_key = "sk-test-key"
        encrypted_bytes = service.encrypt(original_key)
        decrypted = service.decrypt(encrypted_bytes)
        assert decrypted == original_key

    def test_encryption_service_without_key_raises_error_in_production(self) -> None:
        """Test EncryptionService raises error without encryption key in production."""
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)
        os.environ["ENVIRONMENT"] = "production"

        with pytest.raises(EncryptionError, match="APIKEYROUTER_ENCRYPTION_KEY"):
            EncryptionService()

        # Clean up
        os.environ.pop("ENVIRONMENT", None)

    def test_encryption_service_auto_generates_key_in_development(self) -> None:
        """Test EncryptionService auto-generates key in development mode."""
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)
        os.environ["ENVIRONMENT"] = "development"

        # Should not raise error, should auto-generate key
        service = EncryptionService()
        assert service is not None

        # Should be able to encrypt/decrypt
        encrypted = service.encrypt("sk-test")
        decrypted = service.decrypt(encrypted)
        assert decrypted == "sk-test"

        # Clean up
        os.environ.pop("ENVIRONMENT", None)
        os.environ.pop("APIKEYROUTER_ENCRYPTION_KEY", None)

    def test_encryption_service_with_password_key(self) -> None:
        """Test EncryptionService with password (non-Fernet key)."""
        # Password will be derived using PBKDF2
        service = EncryptionService(encryption_key="my-password-123")

        # Should work - password is derived to Fernet key
        original_key = "sk-test-key"
        encrypted_bytes = service.encrypt(original_key)
        decrypted = service.decrypt(encrypted_bytes)
        assert decrypted == original_key

    def test_encryption_service_encrypt_returns_bytes(self) -> None:
        """Test that EncryptionService.encrypt returns bytes."""
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key()
        service = EncryptionService(encryption_key=test_key.decode())

        encrypted = service.encrypt("sk-test")
        assert isinstance(encrypted, bytes)
        assert len(encrypted) > 0

    def test_encryption_service_decrypt_invalid_data(self) -> None:
        """Test that EncryptionService.decrypt raises error for invalid data."""
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key()
        service = EncryptionService(encryption_key=test_key.decode())

        with pytest.raises(EncryptionError, match="Failed to decrypt"):
            service.decrypt(b"invalid-encrypted-data")
