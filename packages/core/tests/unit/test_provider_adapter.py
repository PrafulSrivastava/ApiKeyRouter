"""Tests for ProviderAdapter abstract interface."""

from typing import Any

import pytest

from apikeyrouter.domain.interfaces.provider_adapter import (
    ProviderAdapter,
    ProviderAdapterProtocol,
)


class TestProviderAdapterABC:
    """Tests for ProviderAdapter abstract base class."""

    def test_abstract_class_cannot_be_instantiated(self) -> None:
        """Test that ProviderAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            ProviderAdapter()  # type: ignore[abstract]

    def test_incomplete_implementation_cannot_be_instantiated(self) -> None:
        """Test that incomplete implementations cannot be instantiated."""

        class IncompleteAdapter(ProviderAdapter):
            """Adapter missing required methods."""

            async def execute_request(self, intent: Any, key: Any) -> Any:  # type: ignore[override]
                """Implement execute_request."""
                ...

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteAdapter()  # type: ignore[abstract]

    def test_complete_implementation_can_be_instantiated(self) -> None:
        """Test that complete implementations can be instantiated."""

        class CompleteAdapter(ProviderAdapter):
            """Complete adapter implementation for testing."""

            async def execute_request(self, intent: Any, key: Any) -> Any:  # type: ignore[override]
                """Implement execute_request."""
                ...

            def normalize_response(self, provider_response: Any) -> Any:  # type: ignore[override]
                """Implement normalize_response."""
                ...

            def map_error(self, provider_error: Exception) -> Any:  # type: ignore[override]
                """Implement map_error."""
                ...

            def get_capabilities(self) -> Any:  # type: ignore[override]
                """Implement get_capabilities."""
                ...

            async def estimate_cost(self, request_intent: Any) -> Any:  # type: ignore[override]
                """Implement estimate_cost."""
                ...

            async def get_health(self) -> Any:  # type: ignore[override]
                """Implement get_health."""
                ...

        # Should not raise
        adapter = CompleteAdapter()
        assert isinstance(adapter, ProviderAdapter)
        assert isinstance(adapter, CompleteAdapter)

    def test_all_methods_are_abstract(self) -> None:
        """Test that all required methods are abstract and must be implemented."""
        # Check that ProviderAdapter has all abstract methods
        abstract_methods = ProviderAdapter.__abstractmethods__

        expected_methods = {
            "execute_request",
            "normalize_response",
            "map_error",
            "get_capabilities",
            "estimate_cost",
            "get_health",
        }

        assert abstract_methods == expected_methods, (
            f"Expected abstract methods {expected_methods}, "
            f"but found {abstract_methods}"
        )

    def test_interface_documentation_exists(self) -> None:
        """Test that interface has comprehensive documentation."""
        # Check class docstring
        assert ProviderAdapter.__doc__ is not None
        assert len(ProviderAdapter.__doc__.strip()) > 0

        # Check that class docstring contains key information
        docstring = ProviderAdapter.__doc__
        assert "abstract interface" in docstring.lower() or "interface" in docstring.lower()
        assert "provider" in docstring.lower()

        # Check method docstrings
        methods = [
            "execute_request",
            "normalize_response",
            "map_error",
            "get_capabilities",
            "estimate_cost",
            "get_health",
        ]

        for method_name in methods:
            method = getattr(ProviderAdapter, method_name)
            assert method.__doc__ is not None, f"{method_name} should have a docstring"
            assert len(method.__doc__.strip()) > 0, f"{method_name} docstring should not be empty"


class TestProviderAdapterProtocol:
    """Tests for ProviderAdapterProtocol."""

    def test_protocol_exists(self) -> None:
        """Test that ProviderAdapterProtocol is defined."""
        assert ProviderAdapterProtocol is not None
        assert hasattr(ProviderAdapterProtocol, "__protocol_attrs__") or hasattr(
            ProviderAdapterProtocol, "__annotations__"
        )

    def test_protocol_has_all_methods(self) -> None:
        """Test that Protocol defines all required methods."""
        # Check that Protocol has the same methods as ABC
        protocol_methods = {
            name
            for name in dir(ProviderAdapterProtocol)
            if not name.startswith("_") and callable(getattr(ProviderAdapterProtocol, name, None))
        }

        expected_methods = {
            "execute_request",
            "normalize_response",
            "map_error",
            "get_capabilities",
            "estimate_cost",
            "get_health",
        }

        # Protocol methods should include all expected methods
        assert expected_methods.issubset(protocol_methods), (
            f"Protocol missing methods. Expected {expected_methods}, "
            f"found {protocol_methods}"
        )

    def test_protocol_documentation_exists(self) -> None:
        """Test that Protocol has documentation."""
        assert ProviderAdapterProtocol.__doc__ is not None
        assert len(ProviderAdapterProtocol.__doc__.strip()) > 0


class TestProviderAdapterInterface:
    """Integration tests for ProviderAdapter interface."""

    def test_abc_and_protocol_consistency(self) -> None:
        """Test that ABC and Protocol define the same interface."""
        # Get methods from ABC
        abc_methods = {
            name
            for name in dir(ProviderAdapter)
            if not name.startswith("_")
            and callable(getattr(ProviderAdapter, name, None))
            and name in ProviderAdapter.__abstractmethods__
        }

        # Get methods from Protocol (approximate check)
        protocol_methods = {
            name
            for name in dir(ProviderAdapterProtocol)
            if not name.startswith("_")
            and callable(getattr(ProviderAdapterProtocol, name, None))
        }

        # Both should have the core methods
        core_methods = {
            "execute_request",
            "normalize_response",
            "map_error",
            "get_capabilities",
            "estimate_cost",
            "get_health",
        }

        assert core_methods.issubset(abc_methods), "ABC missing core methods"
        assert core_methods.issubset(protocol_methods), "Protocol missing core methods"

    def test_interface_exports(self) -> None:
        """Test that interface module exports both ABC and Protocol."""
        from apikeyrouter.domain.interfaces import (
            ProviderAdapter,
            ProviderAdapterProtocol,
        )

        assert ProviderAdapter is not None
        assert ProviderAdapterProtocol is not None

