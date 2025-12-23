"""ProviderAdapter abstract interface for provider-specific implementations.

This module defines the abstract base class and protocol for provider adapters.
All provider-specific implementations must conform to this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from apikeyrouter.domain.models.api_key import APIKey
    from apikeyrouter.domain.models.cost_estimate import CostEstimate
    from apikeyrouter.domain.models.health_state import HealthState
    from apikeyrouter.domain.models.provider_capabilities import ProviderCapabilities
    from apikeyrouter.domain.models.request_intent import RequestIntent
    from apikeyrouter.domain.models.system_error import SystemError
    from apikeyrouter.domain.models.system_response import SystemResponse


class ProviderAdapter(ABC):
    """Abstract interface for provider-specific implementations.

    ProviderAdapter defines the contract that all provider implementations must follow.
    It ensures that providers adapt to the system's model, not vice versa. All
    provider-specific logic is contained within adapter implementations.

    Key Responsibilities:
    - Translate system intent (RequestIntent) to provider-specific execution
    - Normalize provider responses to system format (SystemResponse)
    - Map provider errors to system error categories
    - Declare provider capabilities explicitly
    - Estimate request costs
    - Report provider health status

    Example Usage:
        ```python
        class OpenAIAdapter(ProviderAdapter):
            async def execute_request(
                self,
                intent: RequestIntent,
                key: APIKey
            ) -> SystemResponse:
                # Convert RequestIntent to OpenAI API format
                # Make HTTP request to OpenAI
                # Return normalized SystemResponse
                ...

            def normalize_response(
                self,
                provider_response: Any
            ) -> SystemResponse:
                # Convert OpenAI response to SystemResponse
                ...
        ```

    All adapters must implement all abstract methods. Provider-specific quirks
    and special cases must be handled internally and never leak to the core system.
    """

    @abstractmethod
    async def execute_request(self, intent: RequestIntent, key: APIKey) -> SystemResponse:
        """Execute request with provider using system-defined intent.

        This method translates the system's RequestIntent into provider-specific
        API calls and returns a normalized SystemResponse. The adapter handles
        all provider-specific details internally.

        Args:
            intent: Request intent in system terms (model, messages, parameters)
            key: API key to use for authentication

        Returns:
            SystemResponse: Normalized response in system format with content,
                metadata, cost, and key_used fields

        Raises:
            SystemError: Provider-specific errors normalized to system error
                categories. Never raises provider-specific exceptions directly.

        Example:
            ```python
            intent = RequestIntent(
                model="gpt-4",
                messages=[Message(role="user", content="Hello")],
                parameters={"temperature": 0.7}
            )
            key = APIKey(id="key-123", ...)
            response = await adapter.execute_request(intent, key)
            print(response.content)  # Normalized response text
            ```
        """
        ...

    @abstractmethod
    def normalize_response(self, provider_response: Any) -> SystemResponse:
        """Normalize provider response to system format.

        Converts provider-specific response objects into the standardized
        SystemResponse format. This ensures the core system always works with
        a consistent response structure regardless of provider.

        Args:
            provider_response: Raw response from provider API (format varies
                by provider - could be dict, object, etc.)

        Returns:
            SystemResponse: Normalized response with:
                - content: Response text
                - metadata: Response metadata (tokens, model, etc.)
                - cost: Cost estimate if available
                - key_used: ID of key used for request
                - request_id: Request identifier

        Example:
            ```python
            # OpenAI returns: {"choices": [{"message": {"content": "Hi"}}]}
            openai_response = {"choices": [{"message": {"content": "Hi"}}]}
            system_response = adapter.normalize_response(openai_response)
            # Returns SystemResponse with content="Hi" and normalized metadata
            ```
        """
        ...

    @abstractmethod
    def map_error(self, provider_error: Exception) -> SystemError:
        """Map provider error to system error category.

        Converts provider-specific exceptions into standardized SystemError
        objects. This allows the core system to handle errors uniformly
        regardless of provider-specific error formats.

        Args:
            provider_error: Exception raised by provider API or SDK

        Returns:
            SystemError: Normalized error with:
                - category: Error category (AuthenticationError, RateLimitError,
                    QuotaExceededError, ProviderError, etc.)
                - message: Human-readable error message
                - provider_code: Original provider error code if available
                - retryable: Whether error is retryable

        Example:
            ```python
            try:
                response = await provider_client.chat(...)
            except OpenAIError as e:
                system_error = adapter.map_error(e)
                # Returns SystemError with appropriate category
                if system_error.retryable:
                    # Handle retryable error
                    ...
            ```
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Declare what this provider supports.

        Returns explicit capability declaration for the provider. Capabilities
        are not assumed - they must be explicitly declared. This enables the
        routing engine to make informed decisions about which provider to use.

        Returns:
            ProviderCapabilities: Capability declaration with:
                - supports_streaming: Whether provider supports streaming
                - supports_tools: Whether provider supports function/tool calling
                - supports_images: Whether provider supports image input/output
                - max_tokens: Maximum tokens per request (if known)
                - rate_limit_per_minute: Rate limit if known
                - custom_capabilities: Provider-specific features

        Example:
            ```python
            capabilities = adapter.get_capabilities()
            if capabilities.supports_streaming:
                # Use streaming endpoint
                ...
            if "vision" in capabilities.custom_capabilities:
                # Provider supports vision features
                ...
            ```
        """
        ...

    @abstractmethod
    async def estimate_cost(self, request_intent: RequestIntent) -> CostEstimate:
        """Estimate cost for a request before execution.

        Calculates the expected cost for a request based on the RequestIntent.
        This enables proactive cost control and budget enforcement before
        making the actual API call.

        Args:
            request_intent: Request intent containing model, messages, and
                parameters needed for cost calculation

        Returns:
            CostEstimate: Cost estimate with:
                - amount: Estimated cost amount
                - currency: Currency code (e.g., "USD")
                - confidence: Confidence level in estimate (0.0 to 1.0)
                - breakdown: Optional cost breakdown by component

        Example:
            ```python
            intent = RequestIntent(
                model="gpt-4",
                messages=[Message(role="user", content="Hello")],
                parameters={"max_tokens": 100}
            )
            estimate = await adapter.estimate_cost(intent)
            print(f"Estimated cost: {estimate.amount} {estimate.currency}")
            if estimate.amount > budget_limit:
                # Reject request or use cheaper provider
                ...
            ```
        """
        ...

    @abstractmethod
    async def get_health(self) -> HealthState:
        """Get provider health status.

        Returns the current health state of the provider. This enables the
        routing engine to avoid unhealthy providers and implement circuit
        breaker patterns.

        Returns:
            HealthState: Health state with:
                - status: Health status (Healthy, Degraded, Down)
                - last_check: Timestamp of last health check
                - details: Optional health check details
                - latency: Optional response latency measurement

        Example:
            ```python
            health = await adapter.get_health()
            if health.status == HealthStatus.Down:
                # Skip this provider
                ...
            elif health.status == HealthStatus.Degraded:
                # Use as fallback only
                ...
            ```
        """
        ...


class ProviderAdapterProtocol(Protocol):
    """Protocol for type checking provider adapters.

    This protocol allows type checkers to verify that classes conform to the
    ProviderAdapter interface without requiring inheritance from the ABC.
    Useful for duck typing and structural subtyping.

    The protocol defines the same methods as ProviderAdapter ABC, allowing
    both inheritance-based and protocol-based implementations.

    Note: Type hints use forward references (strings) since the types may not
    be available at runtime. With `from __future__ import annotations`, all
    annotations are strings by default.
    """

    async def execute_request(self, intent: RequestIntent, key: APIKey) -> SystemResponse:
        """Execute request with provider."""
        ...

    def normalize_response(self, provider_response: Any) -> SystemResponse:
        """Normalize provider response to system format."""
        ...

    def map_error(self, provider_error: Exception) -> SystemError:
        """Map provider error to system error category."""
        ...

    def get_capabilities(self) -> ProviderCapabilities:
        """Declare what this provider supports."""
        ...

    async def estimate_cost(self, request_intent: RequestIntent) -> CostEstimate:
        """Estimate cost for a request before execution."""
        ...

    async def get_health(self) -> HealthState:
        """Get provider health status."""
        ...


__all__ = [
    "ProviderAdapter",
    "ProviderAdapterProtocol",
]
