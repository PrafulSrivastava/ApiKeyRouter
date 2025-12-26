"""State store implementations."""

from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore

# Lazy import for MongoStateStore to avoid requiring motor if not needed
try:
    from apikeyrouter.infrastructure.state_store.mongo_store import MongoStateStore
except ImportError:
    # motor/beanie not installed - MongoStateStore unavailable
    MongoStateStore = None

# Lazy import for RedisStateStore to avoid requiring redis if not needed
try:
    from apikeyrouter.infrastructure.state_store.redis_store import RedisStateStore
except ImportError:
    # redis not installed - RedisStateStore unavailable
    RedisStateStore = None

__all__ = ["InMemoryStateStore", "MongoStateStore", "RedisStateStore"]
