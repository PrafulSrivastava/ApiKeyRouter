"""Encryption utilities for secure key material storage."""

import os
from base64 import b64decode, b64encode

from cryptography import fernet
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class EncryptionError(Exception):
    """Raised when encryption/decryption operations fail."""

    pass


class EncryptionService:
    """Service for encrypting and decrypting API key material using AES-256.

    Uses Fernet (symmetric encryption) for secure key material storage.
    Encryption key is loaded from environment variable or pydantic-settings.
    """

    def __init__(self, encryption_key: str | None = None) -> None:
        """Initialize EncryptionService with encryption key.

        Args:
            encryption_key: Optional encryption key string. If None, loads from
                environment variable APIKEYROUTER_ENCRYPTION_KEY. In development mode
                (ENVIRONMENT != 'production'), generates a key if not provided.

        Raises:
            EncryptionError: If encryption key is not provided and not in environment,
                and we're in production mode.
        """
        if encryption_key is None:
            encryption_key = os.getenv("APIKEYROUTER_ENCRYPTION_KEY")
            if not encryption_key:
                # Check if we're in production mode
                environment = os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower()
                if environment == "production":
                    raise EncryptionError(
                        "APIKEYROUTER_ENCRYPTION_KEY environment variable is required for encryption in production"
                    )
                # Development mode: generate a key
                generated_key = Fernet.generate_key()
                encryption_key = generated_key.decode()
                # Store in environment for this session (but warn it's not persistent)
                os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = encryption_key

        # Get the actual Fernet key bytes
        fernet_key = self._get_fernet_key(encryption_key)
        self._fernet = Fernet(fernet_key)

    def _get_fernet_key(self, key_str: str) -> bytes:
        """Get Fernet key from string (either direct Fernet key or password).

        Args:
            key_str: Encryption key string (Fernet key or password).

        Returns:
            Fernet key as bytes.

        Raises:
            EncryptionError: If key format is invalid.
        """
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

    def encrypt(self, key_material: str) -> bytes:
        """Encrypt API key material using AES-256.

        Args:
            key_material: Plain text API key to encrypt.

        Returns:
            Encrypted key material as bytes.

        Raises:
            EncryptionError: If encryption fails.
        """
        try:
            encrypted = self._fernet.encrypt(key_material.encode())
            return encrypted
        except Exception as e:
            raise EncryptionError(f"Failed to encrypt key material: {e}") from e

    def decrypt(self, encrypted_data: bytes) -> str:
        """Decrypt API key material.

        Args:
            encrypted_data: Encrypted key material as bytes.

        Returns:
            Decrypted plain text API key.

        Raises:
            EncryptionError: If decryption fails.
        """
        try:
            decrypted = self._fernet.decrypt(encrypted_data)
            return decrypted.decode()
        except Exception as e:
            raise EncryptionError(f"Failed to decrypt key material: {e}") from e


# Backward compatibility functions (deprecated, use EncryptionService)
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




