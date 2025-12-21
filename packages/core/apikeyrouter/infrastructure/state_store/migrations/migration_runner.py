"""Migration runner for MongoDB schema changes."""

from motor.motor_asyncio import AsyncIOMotorDatabase

from apikeyrouter.infrastructure.state_store.migrations.v1_initial_schema import (
    migrate_v1_initial_schema,
)

# Schema version tracking
CURRENT_SCHEMA_VERSION = 1


async def run_migrations(database: AsyncIOMotorDatabase) -> None:
    """Run all pending migrations.

    Checks the current schema version and runs any migrations that haven't
    been applied yet.

    Args:
        database: MongoDB database instance.

    Example:
        ```python
        from motor.motor_asyncio import AsyncIOMotorClient
        from apikeyrouter.infrastructure.state_store.migrations import run_migrations

        client = AsyncIOMotorClient("mongodb://localhost:27017")
        database = client["apikeyrouter"]
        await run_migrations(database)
        ```
    """
    # Get current schema version
    migrations_collection = database["_migrations"]
    version_doc = await migrations_collection.find_one({"type": "schema_version"})
    current_version = version_doc["version"] if version_doc else 0

    # Run migrations in order
    if current_version < 1:
        await migrate_v1_initial_schema(database)
        await migrations_collection.update_one(
            {"type": "schema_version"},
            {"$set": {"version": 1, "type": "schema_version"}},
            upsert=True,
        )

    # Add future migrations here:
    # if current_version < 2:
    #     await migrate_v2_next_migration(database)
    #     await migrations_collection.update_one(
    #         {"type": "schema_version"},
    #         {"$set": {"version": 2}},
    #         upsert=True,
    #     )

