"""Pytest configuration and shared fixtures."""
import os
from contextlib import suppress
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load .env file from project root before running tests
project_root = Path(__file__).parent.parent.parent.parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    # Also try loading from packages/core directory
    core_env_path = project_root / "packages" / "core" / ".env"
    if core_env_path.exists():
        load_dotenv(core_env_path, override=False)
else:
    # Fallback: try loading from packages/core
    core_env_path = project_root / "packages" / "core" / ".env"
    if core_env_path.exists():
        load_dotenv(core_env_path)

# Ensure encryption key is set for all tests
# If not set in .env, generate a test key
if not os.getenv("APIKEYROUTER_ENCRYPTION_KEY"):
    from cryptography.fernet import Fernet

    test_key = Fernet.generate_key()
    os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = test_key.decode()
    print("Warning: APIKEYROUTER_ENCRYPTION_KEY not found in .env, using generated test key")


@pytest.fixture(scope="session", autouse=True)
def ensure_encryption_key():
    """Ensure encryption key is available for all tests."""
    if not os.getenv("APIKEYROUTER_ENCRYPTION_KEY"):
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key()
        os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = test_key.decode()


# Import test fixtures to make them available globally (optional - may fail if optional deps missing)
with suppress(ImportError):
    from .fixtures import test_data  # noqa: F401, E402
    # Fixtures may not be available if optional dependencies (motor, etc.) are missing
    # This is fine - tests that need fixtures can import them directly
