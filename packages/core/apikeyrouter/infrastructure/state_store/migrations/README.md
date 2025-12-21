# MongoDB Migrations

This directory contains migration scripts for MongoDB schema changes.

## Migration Process

Migrations are used to update the database schema when the Beanie document models change. Beanie supports automatic index creation, but manual migrations may be needed for:

- Data transformations
- Index modifications
- Collection renames
- Schema versioning

## Running Migrations

Migrations should be run before starting the application:

```python
from apikeyrouter.infrastructure.state_store.migrations import run_migrations
from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient("mongodb://localhost:27017")
database = client["apikeyrouter"]
await run_migrations(database)
```

## Schema Versioning

The database maintains a `schema_version` document in the `_migrations` collection to track the current schema version.

## Migration Scripts

- `v1_initial_schema.py`: Initial schema setup (indexes, TTL indexes if enabled)

## TTL (Time-To-Live) Configuration

TTL indexes can be enabled for automatic cleanup of old audit trail records. By default, TTL indexes are disabled (commented out) in the document models.

### Enabling TTL for Routing Decisions

To enable automatic cleanup of routing decisions after 90 days:

1. Edit `packages/core/apikeyrouter/infrastructure/state_store/mongo_models.py`
2. In `RoutingDecisionDocument.Settings.indexes`, uncomment the TTL index:
   ```python
   IndexModel([("decision_timestamp", 1)], expireAfterSeconds=7776000),  # 90 days in seconds
   ```
3. Re-run migrations or restart the application (Beanie will create the index)

### Enabling TTL for State Transitions

To enable automatic cleanup of state transitions after 90 days:

1. Edit `packages/core/apikeyrouter/infrastructure/state_store/mongo_models.py`
2. In `StateTransitionDocument.Settings.indexes`, uncomment the TTL index:
   ```python
   IndexModel([("transition_timestamp", 1)], expireAfterSeconds=7776000),  # 90 days in seconds
   ```
3. Re-run migrations or restart the application (Beanie will create the index)

### TTL Configuration Options

- **90 days (default)**: `expireAfterSeconds=7776000` (90 * 24 * 60 * 60)
- **30 days**: `expireAfterSeconds=2592000`
- **7 days**: `expireAfterSeconds=604800`

**Note:** TTL indexes require MongoDB to run a background task that removes expired documents. This happens approximately every 60 seconds, so documents may persist slightly longer than the TTL value.

## Creating New Migrations

1. Create a new migration file: `v{N}_description.py`
2. Implement the migration function
3. Update `migrations/__init__.py` to include the new migration
4. Update the schema version number

