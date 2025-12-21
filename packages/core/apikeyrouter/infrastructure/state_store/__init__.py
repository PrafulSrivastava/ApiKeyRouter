"""State store implementations."""

from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore

# Lazy import for MongoStateStore to avoid requiring motor if not needed
try:
    from apikeyrouter.infrastructure.state_store.mongo_store import MongoStateStore
except ImportError:
    # motor/beanie not installed - MongoStateStore unavailable
    MongoStateStore = None  # type: ignore[assignment, misc]

__all__ = ["InMemoryStateStore", "MongoStateStore"]

