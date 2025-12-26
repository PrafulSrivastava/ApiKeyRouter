"""
Dependency injection setup for the ApiKeyRouter Proxy.
"""

from functools import cache

from apikeyrouter.domain.components.key_manager import KeyManager
from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.state_store import StateStore
from apikeyrouter.infrastructure.observability.logger import (
    DefaultObservabilityManager,
)
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore


@cache
def get_state_store() -> StateStore:
    """Get a singleton instance of the StateStore."""
    return InMemoryStateStore()


@cache
def get_observability_manager() -> ObservabilityManager:
    """Get a singleton instance of the ObservabilityManager."""
    return DefaultObservabilityManager()


@cache
def get_key_manager(
    state_store: StateStore,
    observability_manager: ObservabilityManager,
) -> KeyManager:
    """Get a singleton instance of the KeyManager."""
    return KeyManager(
        state_store=state_store, observability_manager=observability_manager
    )
