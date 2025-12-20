"""Tests for encryption utilities."""

import os

import pytest

from apikeyrouter.infrastructure.utils.encryption import (
    EncryptionError,
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




