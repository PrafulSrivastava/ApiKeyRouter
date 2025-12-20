"""Tests for StateStore abstract interface."""

from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from apikeyrouter.domain.interfaces.state_store import (
    StateQuery,
    StateStore,
    StateStoreError,
)
from apikeyrouter.domain.models.api_key import APIKey
from apikeyrouter.domain.models.quota_state import QuotaState
from apikeyrouter.domain.models.routing_decision import RoutingDecision
from apikeyrouter.domain.models.state_transition import StateTransition


class TestStateStoreABC:
    """Tests for StateStore abstract base class."""

    def test_abstract_class_cannot_be_instantiated(self) -> None:
        """Test that StateStore cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            StateStore()  # type: ignore[abstract]

    def test_incomplete_implementation_cannot_be_instantiated(self) -> None:
        """Test that incomplete implementations cannot be instantiated."""

        class IncompleteStore(StateStore):
            """Store missing required methods."""

            async def save_key(self, key: APIKey) -> None:
                """Implement save_key."""
                ...

            async def get_key(self, key_id: str) -> APIKey | None:
                """Implement get_key."""
                ...

            async def save_quota_state(self, state: QuotaState) -> None:
                """Implement save_quota_state."""
                ...

            async def get_quota_state(self, key_id: str) -> QuotaState | None:
                """Implement get_quota_state."""
                ...

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteStore()  # type: ignore[abstract]

    def test_complete_implementation_can_be_instantiated(self) -> None:
        """Test that complete implementations can be instantiated."""

        class CompleteStore(StateStore):
            """Complete store implementation for testing."""

            async def save_key(self, key: APIKey) -> None:
                """Implement save_key."""
                ...

            async def get_key(self, key_id: str) -> APIKey | None:
                """Implement get_key."""
                ...

            async def save_quota_state(self, state: QuotaState) -> None:
                """Implement save_quota_state."""
                ...

            async def get_quota_state(self, key_id: str) -> QuotaState | None:
                """Implement get_quota_state."""
                ...

            async def save_routing_decision(self, decision: RoutingDecision) -> None:
                """Implement save_routing_decision."""
                ...

            async def save_state_transition(self, transition: StateTransition) -> None:
                """Implement save_state_transition."""
                ...

            async def query_state(self, query: StateQuery) -> list[Any]:
                """Implement query_state."""
                ...

            async def list_keys(self, provider_id: str | None = None) -> list[APIKey]:
                """Implement list_keys."""
                ...

        # Should not raise
        store = CompleteStore()
        assert isinstance(store, StateStore)
        assert isinstance(store, CompleteStore)

    def test_all_methods_are_abstract(self) -> None:
        """Test that all required methods are abstract and must be implemented."""
        # Check that StateStore has all abstract methods
        abstract_methods = StateStore.__abstractmethods__

        expected_methods = {
            "save_key",
            "get_key",
            "list_keys",
            "save_quota_state",
            "get_quota_state",
            "save_routing_decision",
            "save_state_transition",
            "query_state",
        }

        assert abstract_methods == expected_methods, (
            f"Expected abstract methods {expected_methods}, " f"but found {abstract_methods}"
        )

    def test_interface_documentation_exists(self) -> None:
        """Test that interface has comprehensive documentation."""
        # Check class docstring
        assert StateStore.__doc__ is not None
        assert len(StateStore.__doc__.strip()) > 0

        # Check that class docstring contains key information
        docstring = StateStore.__doc__
        assert "abstract interface" in docstring.lower() or "interface" in docstring.lower()
        assert "state" in docstring.lower() or "persistence" in docstring.lower()

        # Check method docstrings
        methods = [
            "save_key",
            "get_key",
            "save_quota_state",
            "get_quota_state",
            "save_routing_decision",
            "save_state_transition",
            "query_state",
        ]

        for method_name in methods:
            method = getattr(StateStore, method_name)
            assert method.__doc__ is not None, f"{method_name} should have a docstring"
            assert len(method.__doc__.strip()) > 0, f"{method_name} docstring should not be empty"

    def test_type_hints_are_correct(self) -> None:
        """Test that all methods have correct type hints."""
        import inspect

        # Check save_key
        save_key_sig = inspect.signature(StateStore.save_key)
        assert save_key_sig.parameters["key"].annotation == APIKey
        assert save_key_sig.return_annotation is None  # Async functions return None directly

        # Check get_key
        get_key_sig = inspect.signature(StateStore.get_key)
        assert get_key_sig.parameters["key_id"].annotation is str
        # For async functions, return annotation is the actual return type
        return_annotation_str = str(get_key_sig.return_annotation)
        assert "APIKey" in return_annotation_str and "None" in return_annotation_str

        # Check save_quota_state
        save_quota_sig = inspect.signature(StateStore.save_quota_state)
        assert save_quota_sig.parameters["state"].annotation == QuotaState
        assert save_quota_sig.return_annotation is None  # Async functions return None directly

        # Check get_quota_state
        get_quota_sig = inspect.signature(StateStore.get_quota_state)
        assert get_quota_sig.parameters["key_id"].annotation is str
        return_annotation_str = str(get_quota_sig.return_annotation)
        assert "QuotaState" in return_annotation_str and "None" in return_annotation_str

        # Check save_routing_decision
        save_decision_sig = inspect.signature(StateStore.save_routing_decision)
        assert save_decision_sig.parameters["decision"].annotation == RoutingDecision
        assert save_decision_sig.return_annotation is None  # Async functions return None directly

        # Check save_state_transition
        save_transition_sig = inspect.signature(StateStore.save_state_transition)
        assert save_transition_sig.parameters["transition"].annotation == StateTransition
        assert save_transition_sig.return_annotation is None  # Async functions return None directly

        # Check query_state
        query_sig = inspect.signature(StateStore.query_state)
        assert query_sig.parameters["query"].annotation == StateQuery
        return_annotation_str = str(query_sig.return_annotation)
        assert "list" in return_annotation_str.lower() or "List" in return_annotation_str


class TestStateQuery:
    """Tests for StateQuery model."""

    def test_state_query_can_be_created(self) -> None:
        """Test that StateQuery can be instantiated with all fields."""
        query = StateQuery(
            entity_type="APIKey",
            key_id="key1",
            provider_id="openai",
            state="available",
            timestamp_from=datetime(2024, 1, 1),
            timestamp_to=datetime(2024, 1, 31),
            limit=100,
            offset=0,
        )

        assert query.entity_type == "APIKey"
        assert query.key_id == "key1"
        assert query.provider_id == "openai"
        assert query.state == "available"
        assert query.timestamp_from == datetime(2024, 1, 1)
        assert query.timestamp_to == datetime(2024, 1, 31)
        assert query.limit == 100
        assert query.offset == 0

    def test_state_query_can_be_created_with_none_fields(self) -> None:
        """Test that StateQuery can be instantiated with None fields."""
        query = StateQuery()

        assert query.entity_type is None
        assert query.key_id is None
        assert query.provider_id is None
        assert query.state is None
        assert query.timestamp_from is None
        assert query.timestamp_to is None
        assert query.limit is None
        assert query.offset is None

    def test_state_query_validation(self) -> None:
        """Test that StateQuery validates input correctly."""
        # Test limit must be >= 1
        with pytest.raises(ValidationError):
            StateQuery(limit=0)

        # Test offset must be >= 0
        with pytest.raises(ValidationError):
            StateQuery(offset=-1)

    def test_state_query_is_frozen(self) -> None:
        """Test that StateQuery is immutable (frozen)."""
        query = StateQuery(entity_type="APIKey")

        with pytest.raises(ValidationError):
            query.entity_type = "QuotaState"  # type: ignore[misc]


class TestStateStoreError:
    """Tests for StateStoreError exception."""

    def test_state_store_error_can_be_raised(self) -> None:
        """Test that StateStoreError can be raised and caught."""
        with pytest.raises(StateStoreError, match="test error"):
            raise StateStoreError("test error")

    def test_state_store_error_inherits_from_exception(self) -> None:
        """Test that StateStoreError inherits from Exception."""
        assert issubclass(StateStoreError, Exception)

    def test_state_store_error_documentation_exists(self) -> None:
        """Test that StateStoreError has documentation."""
        assert StateStoreError.__doc__ is not None
        assert len(StateStoreError.__doc__.strip()) > 0


class TestStateStoreInterface:
    """Integration tests for StateStore interface."""

    def test_interface_exports(self) -> None:
        """Test that interface module exports StateStore, StateQuery, and StateStoreError."""
        from apikeyrouter.domain.interfaces import StateQuery, StateStore, StateStoreError

        assert StateStore is not None
        assert StateQuery is not None
        assert StateStoreError is not None

    def test_all_methods_are_async(self) -> None:
        """Test that all StateStore methods are async."""
        import inspect

        methods = [
            "save_key",
            "get_key",
            "save_quota_state",
            "get_quota_state",
            "save_routing_decision",
            "save_state_transition",
            "query_state",
        ]

        for method_name in methods:
            method = getattr(StateStore, method_name)
            assert inspect.iscoroutinefunction(method), f"{method_name} should be async"

