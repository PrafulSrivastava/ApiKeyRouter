"""Domain interfaces for dependency injection."""

from apikeyrouter.domain.interfaces.provider_adapter import (
    ProviderAdapter,
    ProviderAdapterProtocol,
)
from apikeyrouter.domain.interfaces.state_store import (
    StateQuery,
    StateStore,
    StateStoreError,
)

__all__ = [
    "ProviderAdapter",
    "ProviderAdapterProtocol",
    "StateQuery",
    "StateStore",
    "StateStoreError",
]
