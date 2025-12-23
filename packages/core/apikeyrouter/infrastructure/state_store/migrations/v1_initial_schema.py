"""Initial MongoDB schema migration.

This migration sets up the initial schema with all indexes and optional
TTL indexes for automatic cleanup of old audit trail data.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase

from apikeyrouter.infrastructure.state_store.mongo_models import (
    APIKeyDocument,
    QuotaStateDocument,
    RoutingDecisionDocument,
    StateTransitionDocument,
)


async def migrate_v1_initial_schema(database: AsyncIOMotorDatabase) -> None:
    """Create initial schema with indexes.

    This migration:
    - Creates all required indexes for APIKeyDocument
    - Creates all required indexes for QuotaStateDocument
    - Creates all required indexes for RoutingDecisionDocument
    - Creates all required indexes for StateTransitionDocument
    - Optionally creates TTL indexes for automatic cleanup (commented out by default)

    Args:
        database: MongoDB database instance.

    Note:
        Beanie will automatically create indexes defined in Document.Settings.indexes
        when models are initialized. This migration is for manual index management
        or custom index configurations.
    """
    # Initialize Beanie models to ensure indexes are created
    from beanie import init_beanie

    await init_beanie(
        database=database,
        document_models=[
            APIKeyDocument,
            QuotaStateDocument,
            RoutingDecisionDocument,
            StateTransitionDocument,
        ],
    )

    # Optional: Create TTL indexes for automatic cleanup
    # Uncomment the following lines to enable automatic cleanup after 90 days
    #
    # routing_decisions_collection = database["routing_decisions"]
    # await routing_decisions_collection.create_index(
    #     [("decision_timestamp", 1)], expireAfterSeconds=7776000  # 90 days
    # )
    #
    # state_transitions_collection = database["state_transitions"]
    # await state_transitions_collection.create_index(
    #     [("transition_timestamp", 1)], expireAfterSeconds=7776000  # 90 days
    # )
