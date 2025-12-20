"""Encryption utilities for secure key material storage."""

import os
from base64 import b64decode, b64encode

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptionError(Exception):
    """Raised when encryption/decryption operations fail."""

    pass


def _get_encryption_key() -> bytes:
    """Get encryption key from environment variable.

    Returns:
        Encryption key as bytes.

    Raises:
        EncryptionError: If encryption key is not set or invalid.
    """
    key_str = os.getenv("APIKEYROUTER_ENCRYPTION_KEY")
    if not key_str:
        raise EncryptionError(
            "APIKEYROUTER_ENCRYPTION_KEY environment variable is required for encryption"
        )

    # If key is already a Fernet key (44 chars base64), use it directly
    if len(key_str) == 44:
        try:
            return key_str.encode()
        except Exception as e:
            raise EncryptionError(f"Invalid encryption key format: {e}") from e

    # Otherwise, derive a key from the password using PBKDF2
    # This allows using a simpler password as the encryption key
    salt = os.getenv("APIKEYROUTER_ENCRYPTION_SALT", "apikeyrouter-salt").encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = kdf.derive(key_str.encode())
    return b64encode(key)


def encrypt_key_material(key_material: str) -> str:
    """Encrypt API key material using AES-256.

    Args:
        key_material: Plain text API key to encrypt.

    Returns:
        Encrypted key material as base64-encoded string.

    Raises:
        EncryptionError: If encryption fails.
    """
    try:
        encryption_key = _get_encryption_key()
        fernet = Fernet(encryption_key)
        encrypted = fernet.encrypt(key_material.encode())
        return b64encode(encrypted).decode()
    except Exception as e:
        raise EncryptionError(f"Failed to encrypt key material: {e}") from e


def decrypt_key_material(encrypted_key_material: str) -> str:
    """Decrypt API key material.

    Args:
        encrypted_key_material: Base64-encoded encrypted key material.

    Returns:
        Decrypted plain text API key.

    Raises:
        EncryptionError: If decryption fails.
    """
    try:
        encryption_key = _get_encryption_key()
        fernet = Fernet(encryption_key)
        encrypted_bytes = b64decode(encrypted_key_material.encode())
        decrypted = fernet.decrypt(encrypted_bytes)
        return decrypted.decode()
    except Exception as e:
        raise EncryptionError(f"Failed to decrypt key material: {e}") from e




