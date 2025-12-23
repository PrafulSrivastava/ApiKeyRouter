"""Test fixtures and test data for common test scenarios.

This module provides pytest fixtures for creating test instances of domain models,
state stores, routers, and mocked adapters. These fixtures can be used across
all test files to ensure consistent test data.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.domain.models.quota_state import (
    CapacityEstimate,
    CapacityState,
    CapacityUnit,
    QuotaState,
    TimeWindow,
)
from apikeyrouter.domain.models.request_intent import RequestIntent
from apikeyrouter.domain.models.routing_decision import (
    ObjectiveType,
    RoutingDecision,
    RoutingObjective,
)
from apikeyrouter.domain.models.system_response import SystemResponse
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore
from apikeyrouter.router import ApiKeyRouter


@pytest.fixture
def sample_api_key() -> APIKey:
    """Create a sample APIKey for testing.

    Returns:
        APIKey with default test values.
    """
    return APIKey(
        id="test-key-1",
        key_material="encrypted_test_key_material",
        provider_id="openai",
        state=KeyState.Available,
        usage_count=0,
        failure_count=0,
    )


@pytest.fixture
def sample_api_key_anthropic() -> APIKey:
    """Create a sample Anthropic APIKey for testing.

    Returns:
        APIKey for Anthropic provider.
    """
    return APIKey(
        id="test-key-anthropic-1",
        key_material="encrypted_test_key_material_anthropic",
        provider_id="anthropic",
        state=KeyState.Available,
        usage_count=0,
        failure_count=0,
    )


@pytest.fixture
def sample_api_key_throttled() -> APIKey:
    """Create a throttled APIKey for testing.

    Returns:
        APIKey in Throttled state with cooldown.
    """
    return APIKey(
        id="test-key-throttled",
        key_material="encrypted_test_key_material",
        provider_id="openai",
        state=KeyState.Throttled,
        cooldown_until=datetime.utcnow() + timedelta(minutes=5),
        usage_count=10,
        failure_count=2,
    )


@pytest.fixture
def sample_quota_state(sample_api_key: APIKey) -> QuotaState:
    """Create a sample QuotaState for testing.

    Args:
        sample_api_key: APIKey fixture to link quota state to.

    Returns:
        QuotaState with default test values.
    """
    return QuotaState(
        id=f"quota-{sample_api_key.id}",
        key_id=sample_api_key.id,
        capacity_state=CapacityState.Abundant,
        capacity_unit=CapacityUnit.Requests,
        remaining_capacity=CapacityEstimate(value=1000, confidence=1.0),
        total_capacity=1000,
        used_capacity=0,
        time_window=TimeWindow.Daily,
        reset_at=datetime.utcnow() + timedelta(days=1),
    )


@pytest.fixture
def sample_quota_state_constrained(sample_api_key: APIKey) -> QuotaState:
    """Create a constrained QuotaState for testing.

    Args:
        sample_api_key: APIKey fixture to link quota state to.

    Returns:
        QuotaState in Constrained capacity state.
    """
    return QuotaState(
        id=f"quota-{sample_api_key.id}",
        key_id=sample_api_key.id,
        capacity_state=CapacityState.Constrained,
        capacity_unit=CapacityUnit.Requests,
        remaining_capacity=CapacityEstimate(value=600, confidence=1.0),
        total_capacity=1000,
        used_capacity=400,
        time_window=TimeWindow.Daily,
        reset_at=datetime.utcnow() + timedelta(days=1),
    )


@pytest.fixture
def sample_routing_decision(sample_api_key: APIKey) -> RoutingDecision:
    """Create a sample RoutingDecision for testing.

    Args:
        sample_api_key: APIKey fixture to use in decision.

    Returns:
        RoutingDecision with default test values.
    """
    return RoutingDecision(
        id=f"decision-{uuid.uuid4().hex[:8]}",
        request_id=f"request-{uuid.uuid4().hex[:8]}",
        selected_key_id=sample_api_key.id,
        selected_provider_id=sample_api_key.provider_id,
        objective=RoutingObjective(primary=ObjectiveType.Cost.value),
        explanation="Lowest cost key available",
        confidence=0.95,
    )


@pytest.fixture
def sample_request_intent() -> RequestIntent:
    """Create a sample RequestIntent for testing.

    Returns:
        RequestIntent with default test values.
    """
    return RequestIntent(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hello, world!"}],
        parameters={"temperature": 0.7},
    )


@pytest.fixture
def sample_system_response(sample_api_key: APIKey) -> SystemResponse:
    """Create a sample SystemResponse for testing.

    Args:
        sample_api_key: APIKey fixture to use in response.

    Returns:
        SystemResponse with default test values.
    """
    return SystemResponse(
        request_id=f"request-{uuid.uuid4().hex[:8]}",
        content="Test response content",
        metadata={"tokens": 100, "model": "gpt-4"},
        cost=0.002,
        key_used=sample_api_key.id,
    )


@pytest.fixture
async def memory_state_store() -> InMemoryStateStore:
    """Create an in-memory StateStore for testing.

    Returns:
        InMemoryStateStore instance ready for use.
    """
    return InMemoryStateStore(max_decisions=1000, max_transitions=1000)


@pytest.fixture
async def populated_state_store(
    memory_state_store: InMemoryStateStore,
    sample_api_key: APIKey,
    sample_quota_state: QuotaState,
) -> InMemoryStateStore:
    """Create a StateStore with pre-populated test data.

    Args:
        memory_state_store: InMemoryStateStore fixture.
        sample_api_key: APIKey fixture to add to store.
        sample_quota_state: QuotaState fixture to add to store.

    Returns:
        InMemoryStateStore with test data pre-loaded.
    """
    await memory_state_store.save_key(sample_api_key)
    await memory_state_store.save_quota_state(sample_quota_state)
    return memory_state_store


@pytest.fixture
async def api_key_router(memory_state_store: InMemoryStateStore) -> ApiKeyRouter:
    """Create an ApiKeyRouter instance for testing.

    Args:
        memory_state_store: StateStore fixture to use.

    Returns:
        ApiKeyRouter instance ready for use.
    """
    return ApiKeyRouter(state_store=memory_state_store)


@pytest.fixture
def mock_provider_adapter() -> MagicMock:
    """Create a mocked ProviderAdapter for testing.

    Returns:
        MagicMock configured as a ProviderAdapter with default behaviors.
    """
    adapter = MagicMock(spec=ProviderAdapter)
    adapter.provider_id = "openai"
    adapter.execute_request = AsyncMock(
        return_value=SystemResponse(
            request_id="test-request-1",
            content="Mocked response",
            metadata={"tokens": 50},
            cost=0.001,
            key_used="test-key-1",
        )
    )
    adapter.normalize_response = MagicMock(
        return_value=SystemResponse(
            request_id="test-request-1",
            content="Normalized response",
            metadata={"tokens": 50},
            cost=0.001,
            key_used="test-key-1",
        )
    )
    adapter.estimate_cost = MagicMock(return_value=0.001)
    adapter.get_health_state = AsyncMock(return_value={"status": "healthy", "latency_ms": 100})
    adapter.get_capabilities = MagicMock(
        return_value={
            "models": ["gpt-4", "gpt-3.5-turbo"],
            "supports_streaming": True,
        }
    )
    return adapter


@pytest.fixture
def mock_provider_adapter_anthropic() -> MagicMock:
    """Create a mocked Anthropic ProviderAdapter for testing.

    Returns:
        MagicMock configured as an Anthropic ProviderAdapter.
    """
    adapter = MagicMock(spec=ProviderAdapter)
    adapter.provider_id = "anthropic"
    adapter.execute_request = AsyncMock(
        return_value=SystemResponse(
            request_id="test-request-2",
            content="Anthropic mocked response",
            metadata={"tokens": 75},
            cost=0.0015,
            key_used="test-key-anthropic-1",
        )
    )
    adapter.normalize_response = MagicMock(
        return_value=SystemResponse(
            request_id="test-request-2",
            content="Anthropic normalized response",
            metadata={"tokens": 75},
            cost=0.0015,
            key_used="test-key-anthropic-1",
        )
    )
    adapter.estimate_cost = MagicMock(return_value=0.0015)
    adapter.get_health_state = AsyncMock(return_value={"status": "healthy", "latency_ms": 120})
    adapter.get_capabilities = MagicMock(
        return_value={
            "models": ["claude-3-opus", "claude-3-sonnet"],
            "supports_streaming": True,
        }
    )
    return adapter


@pytest.fixture
def mock_provider_adapter_with_error() -> MagicMock:
    """Create a mocked ProviderAdapter that raises errors for testing.

    Returns:
        MagicMock configured to raise errors on execute_request.
    """
    adapter = MagicMock(spec=ProviderAdapter)
    adapter.provider_id = "openai"
    adapter.execute_request = AsyncMock(side_effect=Exception("Provider error"))
    adapter.normalize_response = MagicMock(
        return_value=SystemResponse(
            request_id="test-request-error",
            content="",
            metadata={},
            cost=0.0,
            key_used="test-key-1",
        )
    )
    adapter.estimate_cost = MagicMock(return_value=0.001)
    adapter.get_health_state = AsyncMock(return_value={"status": "unhealthy", "latency_ms": 5000})
    adapter.get_capabilities = MagicMock(
        return_value={
            "models": ["gpt-4"],
            "supports_streaming": True,
        }
    )
    return adapter
