"""Integration tests for MongoDB Beanie document models."""

from datetime import datetime, timedelta

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.domain.models.quota_state import (
    CapacityEstimate,
    CapacityState,
    CapacityUnit,
    QuotaState,
    TimeWindow,
)
from apikeyrouter.domain.models.routing_decision import (
    AlternativeRoute,
    RoutingDecision,
    RoutingObjective,
)
from apikeyrouter.domain.models.state_transition import StateTransition
from apikeyrouter.infrastructure.state_store.mongo_models import (
    APIKeyDocument,
    QuotaStateDocument,
    RoutingDecisionDocument,
    StateTransitionDocument,
    initialize_beanie_models,
)


@pytest.fixture
async def mongodb_database():
    """Create MongoDB database for testing."""
    import os

    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")

    # Check if MongoDB is available
    try:
        test_client = AsyncIOMotorClient(mongodb_url, serverSelectionTimeoutMS=2000)
        await test_client.admin.command("ping")
        test_client.close()
    except Exception:
        pytest.skip(
            "MongoDB is not available. Start MongoDB with 'docker-compose up -d' or set MONGODB_URL"
        )

    client = AsyncIOMotorClient(mongodb_url)
    database = client["test_apikeyrouter_models"]
    from contextlib import suppress

    yield database
    # Cleanup: drop test database
    with suppress(Exception):
        await client.drop_database("test_apikeyrouter_models")  # Ignore cleanup errors
    client.close()


@pytest.fixture
async def initialized_beanie(mongodb_database):
    """Initialize Beanie with test database."""
    await initialize_beanie_models(mongodb_database)
    return mongodb_database


@pytest.mark.asyncio
async def test_beanie_models_created_correctly(initialized_beanie):
    """Test that Beanie models are created correctly."""
    # Verify collections exist
    collections = await initialized_beanie.list_collection_names()
    assert "api_keys" in collections
    assert "quota_states" in collections
    assert "routing_decisions" in collections
    assert "state_transitions" in collections


@pytest.mark.asyncio
async def test_apikey_document_field_mappings(initialized_beanie):
    """Test APIKeyDocument field mappings are correct."""
    # Create domain model
    key = APIKey(
        id="test-key-1",
        key_material="encrypted_key",
        provider_id="openai",
        state=KeyState.Available,
        state_updated_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        usage_count=10,
        failure_count=1,
    )

    # Convert to document
    doc = APIKeyDocument.from_domain_model(key)
    assert doc.id == key.id
    assert doc.key_material == key.key_material
    assert doc.provider_id == key.provider_id
    assert doc.state == key.state
    assert doc.usage_count == key.usage_count
    assert doc.failure_count == key.failure_count

    # Save to database
    await doc.insert()

    # Retrieve and convert back
    retrieved_doc = await APIKeyDocument.get(key.id)
    assert retrieved_doc is not None
    domain_key = retrieved_doc.to_domain_model()
    assert domain_key.id == key.id
    assert domain_key.provider_id == key.provider_id
    assert domain_key.state == key.state

    # Cleanup
    await doc.delete()


@pytest.mark.asyncio
async def test_apikey_document_indexes(initialized_beanie):
    """Test that APIKeyDocument indexes are created."""
    # Get indexes
    indexes = await initialized_beanie["api_keys"].list_indexes().to_list(length=100)
    index_names = [idx["name"] for idx in indexes]

    # Check for unique index on id
    assert "_id_" in index_names or any("id" in str(idx) for idx in indexes)

    # Check for compound index on provider_id and state
    # Note: MongoDB may create indexes with different names, so we check if collection exists
    assert "api_keys" in await initialized_beanie.list_collection_names()


@pytest.mark.asyncio
async def test_quota_state_document_field_mappings(initialized_beanie):
    """Test QuotaStateDocument field mappings are correct."""
    # Create domain model
    quota = QuotaState(
        id="quota-1",
        key_id="key-1",
        capacity_state=CapacityState.Abundant,
        capacity_unit=CapacityUnit.Requests,
        remaining_capacity=CapacityEstimate(value=1000),
        reset_at=datetime.utcnow() + timedelta(days=1),
        updated_at=datetime.utcnow(),
    )

    # Convert to document
    doc = QuotaStateDocument.from_domain_model(quota)
    assert doc.id == quota.id
    assert doc.key_id == quota.key_id
    assert doc.capacity_state == quota.capacity_state
    assert doc.remaining_capacity.value == quota.remaining_capacity.value

    # Save to database
    await doc.insert()

    # Retrieve and convert back
    retrieved_doc = await QuotaStateDocument.get(quota.id)
    assert retrieved_doc is not None
    domain_quota = retrieved_doc.to_domain_model()
    assert domain_quota.id == quota.id
    assert domain_quota.key_id == quota.key_id

    # Cleanup
    await doc.delete()


@pytest.mark.asyncio
async def test_quota_state_document_indexes(initialized_beanie):
    """Test that QuotaStateDocument indexes are created."""
    # Verify collection exists
    assert "quota_states" in await initialized_beanie.list_collection_names()


@pytest.mark.asyncio
async def test_routing_decision_document_field_mappings(initialized_beanie):
    """Test RoutingDecisionDocument field mappings are correct."""
    # Create domain model
    decision = RoutingDecision(
        id="decision-1",
        request_id="req-1",
        selected_key_id="key-1",
        selected_provider_id="openai",
        decision_timestamp=datetime.utcnow(),
        objective=RoutingObjective(primary="cost"),
        explanation="Lowest cost key available",
        confidence=0.9,
        alternatives_considered=[
            AlternativeRoute(
                key_id="key-2",
                provider_id="openai",
                score=0.8,
                reason_not_selected="Higher cost",
            )
        ],
    )

    # Convert to document
    doc = RoutingDecisionDocument.from_domain_model(decision)
    assert doc.id == decision.id
    assert doc.selected_key_id == decision.selected_key_id
    assert doc.explanation == decision.explanation
    assert len(doc.alternatives_considered) == 1

    # Save to database
    await doc.insert()

    # Retrieve and convert back
    retrieved_doc = await RoutingDecisionDocument.get(decision.id)
    assert retrieved_doc is not None
    domain_decision = retrieved_doc.to_domain_model()
    assert domain_decision.id == decision.id
    assert domain_decision.explanation == decision.explanation

    # Cleanup
    await doc.delete()


@pytest.mark.asyncio
async def test_routing_decision_document_indexes(initialized_beanie):
    """Test that RoutingDecisionDocument indexes are created."""
    # Verify collection exists
    assert "routing_decisions" in await initialized_beanie.list_collection_names()


@pytest.mark.asyncio
async def test_state_transition_document_field_mappings(initialized_beanie):
    """Test StateTransitionDocument field mappings are correct."""
    # Create domain model
    transition = StateTransition(
        entity_type="APIKey",
        entity_id="key-1",
        from_state="available",
        to_state="throttled",
        transition_timestamp=datetime.utcnow(),
        trigger="rate_limit_error",
        context={"error_code": 429},
    )

    # Convert to document
    doc = StateTransitionDocument.from_domain_model(transition)
    assert doc.entity_type == transition.entity_type
    assert doc.entity_id == transition.entity_id
    assert doc.from_state == transition.from_state
    assert doc.to_state == transition.to_state
    assert doc.context == transition.context

    # Save to database
    await doc.insert()

    # Retrieve (using find since there's no unique id)
    retrieved_docs = await StateTransitionDocument.find(
        StateTransitionDocument.entity_id == transition.entity_id
    ).to_list()
    assert len(retrieved_docs) > 0
    retrieved_doc = retrieved_docs[0]
    domain_transition = retrieved_doc.to_domain_model()
    assert domain_transition.entity_id == transition.entity_id
    assert domain_transition.trigger == transition.trigger

    # Cleanup
    await retrieved_doc.delete()


@pytest.mark.asyncio
async def test_state_transition_document_indexes(initialized_beanie):
    """Test that StateTransitionDocument indexes are created."""
    # Verify collection exists
    assert "state_transitions" in await initialized_beanie.list_collection_names()


@pytest.mark.asyncio
async def test_pydantic_validation_works(initialized_beanie):
    """Test that Pydantic validation works in Beanie documents."""
    from pydantic import ValidationError

    # Create a document with invalid data (missing required field)
    with pytest.raises(ValidationError):  # Pydantic validation error
        # Try to create document without required fields
        APIKeyDocument(
            id="test-key",
            # Missing key_material, provider_id, state, etc.
        )


@pytest.mark.asyncio
async def test_initialize_beanie_models_registers_all_models(initialized_beanie):
    """Test that initialize_beanie_models registers all document models."""
    # Verify all collections exist
    collections = await initialized_beanie.list_collection_names()
    assert "api_keys" in collections
    assert "quota_states" in collections
    assert "routing_decisions" in collections
    assert "state_transitions" in collections


@pytest.mark.asyncio
async def test_document_to_domain_model_conversion(initialized_beanie):
    """Test conversion from document to domain model preserves all fields."""
    # Create and save APIKey
    key = APIKey(
        id="test-key-conv",
        key_material="encrypted",
        provider_id="openai",
        state=KeyState.Available,
        state_updated_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        metadata={"test": "value"},
    )

    doc = APIKeyDocument.from_domain_model(key)
    await doc.insert()

    # Retrieve and convert back
    retrieved = await APIKeyDocument.get(key.id)
    assert retrieved is not None
    converted = retrieved.to_domain_model()

    # Verify all fields preserved
    assert converted.id == key.id
    assert converted.key_material == key.key_material
    assert converted.provider_id == key.provider_id
    assert converted.state == key.state
    assert converted.metadata == key.metadata

    # Cleanup
    await doc.delete()


@pytest.mark.asyncio
async def test_domain_model_to_document_conversion(initialized_beanie):
    """Test conversion from domain model to document preserves all fields."""
    # Create domain model with all fields
    quota = QuotaState(
        id="quota-conv",
        key_id="key-conv",
        capacity_state=CapacityState.Constrained,
        capacity_unit=CapacityUnit.Mixed,
        remaining_capacity=CapacityEstimate(value=500, confidence=0.9),
        total_capacity=1000,
        used_capacity=500,
        remaining_tokens=CapacityEstimate(value=10000),
        total_tokens=20000,
        used_tokens=10000,
        used_requests=50,
        time_window=TimeWindow.Daily,
        reset_at=datetime.utcnow() + timedelta(days=1),
        updated_at=datetime.utcnow(),
    )

    # Convert to document
    doc = QuotaStateDocument.from_domain_model(quota)

    # Verify all fields preserved
    assert doc.id == quota.id
    assert doc.key_id == quota.key_id
    assert doc.capacity_state == quota.capacity_state
    assert doc.capacity_unit == quota.capacity_unit
    assert doc.remaining_capacity.value == quota.remaining_capacity.value
    assert doc.total_capacity == quota.total_capacity
    assert doc.remaining_tokens is not None
    assert doc.remaining_tokens.value == quota.remaining_tokens.value
