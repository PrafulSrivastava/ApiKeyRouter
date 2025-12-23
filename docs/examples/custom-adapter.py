"""
Custom Provider Adapter Example

This example demonstrates how to create a custom provider adapter for ApiKeyRouter:
- Implementing the ProviderAdapter interface
- Request execution
- Response normalization
- Error mapping
- Cost estimation
- Health checking

Prerequisites:
    Install dependencies:
    pip install apikeyrouter-core httpx

Run with: python custom-adapter.py
"""

import asyncio
from decimal import Decimal
from typing import Any

import httpx

from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.api_key import APIKey
from apikeyrouter.domain.models.cost_estimate import CostEstimate
from apikeyrouter.domain.models.health_state import HealthState, HealthStatus
from apikeyrouter.domain.models.provider_capabilities import ProviderCapabilities
from apikeyrouter.domain.models.request_intent import Message, RequestIntent
from apikeyrouter.domain.models.system_error import ErrorCategory, SystemError
from apikeyrouter.domain.models.system_response import SystemResponse
from apikeyrouter.infrastructure.utils.encryption import EncryptionService


class MyCustomProviderAdapter(ProviderAdapter):
    """
    Example custom provider adapter for a hypothetical "MyProvider" API.
    
    This adapter demonstrates how to implement all required ProviderAdapter methods
    to integrate a new provider with ApiKeyRouter.
    """

    def __init__(self, base_url: str = "https://api.myprovider.com/v1"):
        """Initialize the custom adapter.
        
        Args:
            base_url: Base URL for the provider API.
        """
        self.base_url = base_url
        self._encryption_service = EncryptionService()

    async def execute_request(
        self,
        intent: RequestIntent,
        key: APIKey
    ) -> SystemResponse:
        """
        Execute request with provider using system-defined intent.
        
        This method:
        1. Decrypts the API key
        2. Converts RequestIntent to provider-specific format
        3. Makes HTTP request to provider
        4. Normalizes response to SystemResponse
        
        Args:
            intent: Request intent in system terms (model, messages, parameters)
            key: API key to use for authentication
            
        Returns:
            SystemResponse: Normalized response in system format
            
        Raises:
            SystemError: Provider-specific errors normalized to system error categories
        """
        try:
            # Decrypt API key
            decrypted_key = self._encryption_service.decrypt(key.key_material)

            # Convert RequestIntent to provider-specific format
            provider_request = self._convert_to_provider_format(intent)

            # Make HTTP request to provider
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {decrypted_key}",
                        "Content-Type": "application/json"
                    },
                    json=provider_request
                )
                response.raise_for_status()
                provider_response = response.json()

            # Normalize provider response to SystemResponse
            return self.normalize_response(provider_response)

        except httpx.HTTPStatusError as e:
            # Map HTTP errors to SystemError
            if e.response.status_code == 401:
                raise SystemError(
                    category=ErrorCategory.AuthenticationError,
                    message="Invalid API key",
                    provider_code="invalid_api_key",
                    retryable=False
                ) from e
            elif e.response.status_code == 429:
                retry_after = int(e.response.headers.get("Retry-After", "60"))
                raise SystemError(
                    category=ErrorCategory.RateLimitError,
                    message="Rate limit exceeded",
                    provider_code="rate_limit",
                    retryable=True,
                    retry_after=retry_after
                ) from e
            elif e.response.status_code >= 500:
                raise SystemError(
                    category=ErrorCategory.ProviderError,
                    message=f"Provider error: {e.response.status_code}",
                    provider_code=str(e.response.status_code),
                    retryable=True
                ) from e
            else:
                raise SystemError(
                    category=ErrorCategory.ValidationError,
                    message=f"Request error: {e.response.status_code}",
                    provider_code=str(e.response.status_code),
                    retryable=False
                ) from e

        except httpx.TimeoutException as e:
            raise SystemError(
                category=ErrorCategory.TimeoutError,
                message="Request timeout",
                provider_code="timeout",
                retryable=True
            ) from e

        except Exception as e:
            raise SystemError(
                category=ErrorCategory.UnknownError,
                message=f"Unexpected error: {str(e)}",
                provider_code="unknown",
                retryable=False
            ) from e

    def normalize_response(
        self,
        provider_response: Any
    ) -> SystemResponse:
        """
        Normalize provider response to system format.
        
        Converts provider-specific response objects into the standardized
        SystemResponse format.
        
        Args:
            provider_response: Raw response from provider API (dict, object, etc.)
            
        Returns:
            SystemResponse: Normalized response with content, metadata, cost, etc.
        """
        # Extract content from provider response
        # Format depends on provider - this is an example
        content = provider_response.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Extract metadata
        model = provider_response.get("model", "unknown")
        usage = provider_response.get("usage", {})
        tokens_used = usage.get("total_tokens", 0)

        # Create SystemResponse
        from datetime import datetime

        from apikeyrouter.domain.models.system_response import (
            ResponseMetadata,
            SystemResponse,
            TokenUsage,
        )

        # Create ResponseMetadata
        metadata = ResponseMetadata(
            model_used=model,
            tokens_used=TokenUsage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0)
            ) if usage else TokenUsage(input_tokens=0, output_tokens=0),
            response_time_ms=0,  # Would be calculated from actual request time
            provider_id="myprovider",
            timestamp=datetime.utcnow()
        )

        return SystemResponse(
            content=content,
            metadata=metadata,
            cost=None,  # Will be set by router after cost reconciliation
            key_used="",  # Will be set by router
            request_id=""  # Will be set by router
        )

    def map_error(
        self,
        provider_error: Exception
    ) -> SystemError:
        """
        Map provider error to system error category.
        
        Converts provider-specific exceptions into standardized SystemError
        objects.
        
        Args:
            provider_error: Exception raised by provider API or SDK
            
        Returns:
            SystemError: Normalized error with category, message, and retryable flag
        """
        # Map provider-specific exceptions to SystemError
        error_name = type(provider_error).__name__

        if "Auth" in error_name or "401" in str(provider_error):
            return SystemError(
                category=ErrorCategory.AuthenticationError,
                message=str(provider_error),
                provider_code="auth_error",
                retryable=False
            )
        elif "RateLimit" in error_name or "429" in str(provider_error):
            return SystemError(
                category=ErrorCategory.RateLimitError,
                message=str(provider_error),
                provider_code="rate_limit",
                retryable=True
            )
        elif "Timeout" in error_name:
            return SystemError(
                category=ErrorCategory.TimeoutError,
                message=str(provider_error),
                provider_code="timeout",
                retryable=True
            )
        else:
            return SystemError(
                category=ErrorCategory.ProviderError,
                message=str(provider_error),
                provider_code="unknown",
                retryable=True
            )

    def get_capabilities(self) -> ProviderCapabilities:
        """
        Declare what this provider supports.
        
        Returns:
            ProviderCapabilities: Capability declaration with supported features
        """
        return ProviderCapabilities(
            supports_streaming=True,
            supports_tools=False,  # This provider doesn't support function calling
            supports_images=False,
            max_tokens=4096,
            rate_limit_per_minute=60,
            custom_capabilities={
                "custom_feature": True
            }
        )

    async def estimate_cost(
        self,
        request_intent: RequestIntent
    ) -> CostEstimate:
        """
        Estimate cost for a request before execution.
        
        Calculates the expected cost based on the request intent and provider
        pricing model.
        
        Args:
            request_intent: Request intent containing model, messages, and parameters
            
        Returns:
            CostEstimate: Cost estimate with amount, confidence, and token estimates
        """
        # Simple cost estimation based on model and message length
        # In production, use actual provider pricing models

        model = request_intent.model
        messages = request_intent.messages

        # Estimate tokens (simplified - use actual tokenizer in production)
        estimated_tokens = sum(len(msg.content) // 4 for msg in messages) + 100  # Rough estimate

        # Pricing model (example - use actual provider pricing)
        cost_per_1k_tokens = Decimal("0.03") if "gpt-4" in model else Decimal("0.01")

        estimated_cost = (Decimal(estimated_tokens) / Decimal("1000")) * cost_per_1k_tokens

        return CostEstimate(
            amount=estimated_cost,
            currency="USD",
            confidence=0.8,  # 80% confidence in estimate
            estimated_tokens=estimated_tokens
        )

    async def get_health(self) -> HealthState:
        """
        Get provider health status.
        
        Returns:
            HealthState: Health state with status, last_check, and details
        """
        from datetime import datetime

        try:
            # Check provider health endpoint
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                response.raise_for_status()

            return HealthState(
                status=HealthStatus.Healthy,
                last_check=datetime.utcnow(),
                details={"endpoint": "healthy"}
            )
        except Exception as e:
            return HealthState(
                status=HealthStatus.Down,
                last_check=datetime.utcnow(),
                details={"error": str(e)}
            )

    def _convert_to_provider_format(self, intent: RequestIntent) -> dict[str, Any]:
        """Convert RequestIntent to provider-specific format.
        
        Args:
            intent: RequestIntent in system format
            
        Returns:
            dict: Provider-specific request format
        """
        return {
            "model": intent.model,
            "messages": [
                {"role": msg.role, "content": msg.content}
                for msg in intent.messages
            ],
            **intent.parameters  # Include any additional parameters
        }


async def main():
    """Main example function demonstrating custom adapter usage."""

    print("=" * 80)
    print("Custom Provider Adapter Example")
    print("=" * 80)
    print()

    # ============================================================================
    # Step 1: Create Custom Adapter
    # ============================================================================

    print("Step 1: Creating custom provider adapter...")
    adapter = MyCustomProviderAdapter(base_url="https://api.myprovider.com/v1")
    print("✓ Custom adapter created")
    print()

    # ============================================================================
    # Step 2: Register Provider with Router
    # ============================================================================

    print("Step 2: Registering provider with ApiKeyRouter...")
    from apikeyrouter import ApiKeyRouter

    router = ApiKeyRouter()
    await router.register_provider("myprovider", adapter)
    print("✓ Provider 'myprovider' registered")
    print()

    # ============================================================================
    # Step 3: Register Keys
    # ============================================================================

    print("Step 3: Registering API keys...")
    key = await router.register_key(
        key_material="sk-example-myprovider-key-not-real",
        provider_id="myprovider",
        metadata={"tier": "premium"}
    )
    print(f"✓ Key registered: {key.id}")
    print()

    # ============================================================================
    # Step 4: Check Capabilities
    # ============================================================================

    print("Step 4: Checking provider capabilities...")
    capabilities = adapter.get_capabilities()
    print(f"  Supports streaming: {capabilities.supports_streaming}")
    print(f"  Supports tools: {capabilities.supports_tools}")
    print(f"  Max tokens: {capabilities.max_tokens}")
    print(f"  Rate limit: {capabilities.rate_limit_per_minute}/minute")
    print()

    # ============================================================================
    # Step 5: Estimate Cost
    # ============================================================================

    print("Step 5: Estimating request cost...")
    from apikeyrouter.domain.models.request_intent import RequestIntent

    intent = RequestIntent(
        model="myprovider-model-v1",
        messages=[Message(role="user", content="Hello!")],
        provider_id="myprovider"
    )

    cost_estimate = await adapter.estimate_cost(intent)
    print(f"  Estimated cost: ${cost_estimate.amount}")
    print(f"  Confidence: {cost_estimate.confidence:.2f}")
    print(f"  Estimated tokens: {cost_estimate.estimated_tokens}")
    print()

    # ============================================================================
    # Step 6: Check Health
    # ============================================================================

    print("Step 6: Checking provider health...")
    health = await adapter.get_health()
    print(f"  Status: {health.status.value}")
    print(f"  Last check: {health.last_check}")
    print(f"  Details: {health.details}")
    print()

    # ============================================================================
    # Step 7: Make Request (if provider is available)
    # ============================================================================

    print("Step 7: Making request (example - may fail if provider not available)...")
    print("  Note: This will fail if 'myprovider' API is not actually available.")
    print("  This is expected - the adapter is just an example.")
    print()

    try:
        response = await router.route(intent)
        print("  ✓ Request succeeded")
        print(f"  Response: {response.content[:100]}...")
    except Exception as e:
        print(f"  ✗ Request failed (expected): {e}")
        print("  This is normal - the adapter is a template for real implementations.")

    print()

    print("=" * 80)
    print("Example completed!")
    print("=" * 80)
    print()
    print("Key takeaways:")
    print("  - Custom adapters implement the ProviderAdapter interface")
    print("  - All required methods must be implemented")
    print("  - Error mapping normalizes provider errors to SystemError")
    print("  - Response normalization converts to SystemResponse")
    print("  - Cost estimation enables proactive cost control")
    print()
    print("Next steps:")
    print("  - Read the tutorial: docs/tutorials/building-custom-adapter.md")
    print("  - See API Reference: docs/api/API_REFERENCE.md#provideradapter")
    print()


if __name__ == "__main__":
    asyncio.run(main())

