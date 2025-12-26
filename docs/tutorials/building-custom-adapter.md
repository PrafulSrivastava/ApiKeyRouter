# Tutorial: Building a Custom Provider Adapter

This tutorial walks you through creating a custom provider adapter for ApiKeyRouter. Adapters allow you to integrate any API provider with ApiKeyRouter's intelligent routing system.

## Overview

A **ProviderAdapter** is a bridge between ApiKeyRouter's system format and a provider's specific API. It handles:
- Converting system requests to provider format
- Making API calls to the provider
- Normalizing provider responses
- Mapping provider errors to system errors
- Estimating costs
- Reporting health status

## Prerequisites

- Python 3.11+
- Understanding of async/await in Python
- Familiarity with HTTP clients (httpx recommended)
- Basic understanding of ApiKeyRouter concepts

## Step 1: Understand the ProviderAdapter Interface

The `ProviderAdapter` is an abstract base class with 6 required methods:

```python
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter

class ProviderAdapter(ABC):
    @abstractmethod
    async def execute_request(self, intent: RequestIntent, key: APIKey) -> SystemResponse:
        """Execute request with provider."""
        ...
    
    @abstractmethod
    def normalize_response(self, provider_response: Any) -> SystemResponse:
        """Normalize provider response to system format."""
        ...
    
    @abstractmethod
    def map_error(self, provider_error: Exception) -> SystemError:
        """Map provider error to system error category."""
        ...
    
    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Declare what this provider supports."""
        ...
    
    @abstractmethod
    async def estimate_cost(self, request_intent: RequestIntent) -> CostEstimate:
        """Estimate cost for a request before execution."""
        ...
    
    @abstractmethod
    async def get_health(self) -> HealthState:
        """Get provider health status."""
        ...
```

## Step 2: Create Your Adapter Class

Start by creating a class that inherits from `ProviderAdapter`:

```python
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.api_key import APIKey
from apikeyrouter.domain.models.request_intent import RequestIntent
from apikeyrouter.domain.models.system_response import SystemResponse

class MyProviderAdapter(ProviderAdapter):
    """Adapter for MyProvider API."""
    
    def __init__(self, base_url: str = "https://api.myprovider.com/v1"):
        """Initialize adapter.
        
        Args:
            base_url: Base URL for the provider API.
        """
        self.base_url = base_url
        # Initialize encryption service for key decryption
        from apikeyrouter.infrastructure.utils.encryption import EncryptionService
        self._encryption_service = EncryptionService()
```

## Step 3: Implement execute_request()

This is the core method that makes API calls to your provider:

```python
async def execute_request(
    self,
    intent: RequestIntent,
    key: APIKey
) -> SystemResponse:
    """Execute request with provider."""
    import httpx
    
    # 1. Decrypt the API key
    decrypted_key = self._encryption_service.decrypt(key.key_material)
    
    # 2. Convert RequestIntent to provider-specific format
    provider_request = {
        "model": intent.model,
        "messages": [
            {"role": msg.role, "content": msg.content}
            for msg in intent.messages
        ],
        **intent.parameters  # Include additional parameters
    }
    
    # 3. Make HTTP request
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
    
    # 4. Normalize response
    return self.normalize_response(provider_response)
```

**Key Points:**
- Always decrypt the key using `EncryptionService`
- Convert `RequestIntent` to provider-specific format
- Handle HTTP errors and map them to `SystemError`
- Return normalized `SystemResponse`

## Step 4: Implement normalize_response()

Convert provider responses to the standard `SystemResponse` format:

```python
def normalize_response(
    self,
    provider_response: Any
) -> SystemResponse:
    """Normalize provider response to system format."""
    from apikeyrouter.domain.models.system_response import SystemResponse
    from apikeyrouter.domain.models.token_usage import TokenUsage
    
    # Extract content (format depends on provider)
    content = provider_response.get("choices", [{}])[0].get("message", {}).get("content", "")
    
    # Extract metadata
    model = provider_response.get("model", "unknown")
    usage = provider_response.get("usage", {})
    
    # Create SystemResponse
    return SystemResponse(
        content=content,
        metadata={
            "model": model,
            "tokens_used": TokenUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0)
            ) if usage else None
        },
        cost=None,  # Set by router after cost reconciliation
        key_used="",  # Set by router
        request_id=""  # Set by router
    )
```

**Key Points:**
- Extract content from provider-specific response format
- Extract metadata (tokens, model, etc.)
- Create `SystemResponse` with all required fields
- Leave `cost`, `key_used`, and `request_id` empty (set by router)

## Step 5: Implement map_error()

Map provider-specific errors to system error categories:

```python
def map_error(
    self,
    provider_error: Exception
) -> SystemError:
    """Map provider error to system error category."""
    from apikeyrouter.domain.models.system_error import SystemError, ErrorCategory
    
    error_name = type(provider_error).__name__
    error_str = str(provider_error)
    
    # Map based on error type or message
    if "401" in error_str or "auth" in error_str.lower():
        return SystemError(
            category=ErrorCategory.AuthenticationError,
            message=str(provider_error),
            provider_code="auth_error",
            retryable=False
        )
    elif "429" in error_str or "rate" in error_str.lower():
        return SystemError(
            category=ErrorCategory.RateLimitError,
            message=str(provider_error),
            provider_code="rate_limit",
            retryable=True
        )
    elif "timeout" in error_str.lower():
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
```

**Key Points:**
- Map authentication errors → `AuthenticationError` (not retryable)
- Map rate limit errors → `RateLimitError` (retryable)
- Map timeouts → `TimeoutError` (retryable)
- Map unknown errors → `ProviderError` (retryable by default)

## Step 6: Implement get_capabilities()

Declare what your provider supports:

```python
def get_capabilities(self) -> ProviderCapabilities:
    """Declare what this provider supports."""
    from apikeyrouter.domain.models.provider_capabilities import ProviderCapabilities
    
    return ProviderCapabilities(
        supports_streaming=True,  # Does provider support streaming?
        supports_tools=False,  # Does provider support function calling?
        supports_images=False,  # Does provider support image input/output?
        max_tokens=4096,  # Maximum tokens per request
        rate_limit_per_minute=60,  # Rate limit if known
        custom_capabilities={
            "custom_feature": True  # Provider-specific features
        }
    )
```

**Key Points:**
- Be honest about capabilities (don't claim features you don't support)
- Set `max_tokens` to actual provider limit
- Include rate limits if known
- Add custom capabilities for provider-specific features

## Step 7: Implement estimate_cost()

Estimate cost before execution (enables budget enforcement):

```python
async def estimate_cost(
    self,
    request_intent: RequestIntent
) -> CostEstimate:
    """Estimate cost for a request before execution."""
    from apikeyrouter.domain.models.cost_estimate import CostEstimate
    from decimal import Decimal
    
    # Estimate tokens (simplified - use actual tokenizer in production)
    estimated_tokens = sum(len(msg.content) // 4 for msg in request_intent.messages) + 100
    
    # Get pricing based on model
    model = request_intent.model
    if "gpt-4" in model:
        cost_per_1k = Decimal("0.03")
    else:
        cost_per_1k = Decimal("0.01")
    
    # Calculate estimated cost
    estimated_cost = (Decimal(estimated_tokens) / Decimal("1000")) * cost_per_1k
    
    return CostEstimate(
        amount=estimated_cost,
        currency="USD",
        confidence=0.8,  # Confidence in estimate (0.0 to 1.0)
        estimated_tokens=estimated_tokens
    )
```

**Key Points:**
- Estimate tokens accurately (use actual tokenizer if available)
- Use provider's actual pricing model
- Set confidence based on estimation accuracy
- Return `CostEstimate` with amount, currency, and confidence

## Step 8: Implement get_health()

Report provider health status:

```python
async def get_health(self) -> HealthState:
    """Get provider health status."""
    from apikeyrouter.domain.models.health_state import HealthState, HealthStatus
    from datetime import datetime
    import httpx
    
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
```

**Key Points:**
- Check provider health endpoint if available
- Return `HealthStatus.Healthy`, `HealthStatus.Degraded`, or `HealthStatus.Down`
- Include timestamp and details
- Handle errors gracefully

## Step 9: Register Your Adapter

Once your adapter is complete, register it with ApiKeyRouter:

```python
from apikeyrouter import ApiKeyRouter

router = ApiKeyRouter()
adapter = MyProviderAdapter(base_url="https://api.myprovider.com/v1")
await router.register_provider("myprovider", adapter)

# Register keys
await router.register_key("sk-myprovider-key", "myprovider")

# Use it!
intent = RequestIntent(
    model="myprovider-model",
    messages=[Message(role="user", content="Hello!")],
    provider_id="myprovider"
)
response = await router.route(intent)
```

## Complete Example

See `docs/examples/custom-adapter.py` for a complete working example.

## Testing Your Adapter

### Unit Tests

Test each method independently:

```python
import pytest
from apikeyrouter.domain.models.request_intent import RequestIntent, Message

@pytest.mark.asyncio
async def test_execute_request():
    adapter = MyProviderAdapter()
    intent = RequestIntent(
        model="test-model",
        messages=[Message(role="user", content="test")],
        provider_id="myprovider"
    )
    key = APIKey(id="test-key", key_material="encrypted-key", provider_id="myprovider")
    
    response = await adapter.execute_request(intent, key)
    assert response.content is not None
    assert response.metadata.model == "test-model"

@pytest.mark.asyncio
async def test_estimate_cost():
    adapter = MyProviderAdapter()
    intent = RequestIntent(
        model="test-model",
        messages=[Message(role="user", content="test")],
        provider_id="myprovider"
    )
    
    estimate = await adapter.estimate_cost(intent)
    assert estimate.amount > 0
    assert estimate.currency == "USD"
```

### Integration Tests

Test with real ApiKeyRouter:

```python
@pytest.mark.asyncio
async def test_adapter_integration():
    router = ApiKeyRouter()
    adapter = MyProviderAdapter()
    await router.register_provider("myprovider", adapter)
    await router.register_key("sk-test-key", "myprovider")
    
    intent = RequestIntent(
        model="test-model",
        messages=[Message(role="user", content="test")],
        provider_id="myprovider"
    )
    
    response = await router.route(intent)
    assert response.content is not None
```

## Best Practices

### 1. Error Handling

- Always catch provider-specific exceptions
- Map to `SystemError` with appropriate category
- Set `retryable` flag correctly
- Include `retry_after` for rate limit errors

### 2. Key Security

- Always use `EncryptionService` to decrypt keys
- Never log key material
- Never expose keys in error messages

### 3. Response Normalization

- Extract all relevant metadata
- Handle missing fields gracefully
- Use default values when appropriate
- Maintain consistent format

### 4. Cost Estimation

- Use actual provider pricing models
- Estimate tokens accurately
- Set confidence based on accuracy
- Update estimates as pricing changes

### 5. Health Checking

- Check health endpoint if available
- Handle timeouts gracefully
- Cache health status (optional)
- Report accurate status

## Common Pitfalls

### Pitfall 1: Not Decrypting Keys

❌ **Wrong:**
```python
# Using key directly
headers = {"Authorization": f"Bearer {key.key_material}"}
```

✅ **Correct:**
```python
# Decrypt key first
decrypted_key = self._encryption_service.decrypt(key.key_material)
headers = {"Authorization": f"Bearer {decrypted_key}"}
```

### Pitfall 2: Raising Provider Exceptions

❌ **Wrong:**
```python
except httpx.HTTPStatusError as e:
    raise e  # Don't raise provider exceptions directly
```

✅ **Correct:**
```python
except httpx.HTTPStatusError as e:
    raise SystemError(
        category=ErrorCategory.ProviderError,
        message=str(e),
        retryable=True
    ) from e
```

### Pitfall 3: Incomplete Response Normalization

❌ **Wrong:**
```python
return SystemResponse(
    content=provider_response["content"]  # Missing required fields
)
```

✅ **Correct:**
```python
return SystemResponse(
    content=provider_response.get("content", ""),
    metadata={"model": provider_response.get("model", "unknown")},
    cost=None,
    key_used="",
    request_id=""
)
```

## Next Steps

1. **Test your adapter** with unit and integration tests
2. **Register it** with ApiKeyRouter
3. **Use it** in your application
4. **Share it** with the community (optional)

## Resources

- **Example Code**: `docs/examples/custom-adapter.py`
- **API Reference**: `docs/api/API_REFERENCE.md#provideradapter`
- **ProviderAdapter Interface**: `packages/core/apikeyrouter/domain/interfaces/provider_adapter.py`
- **OpenAI Adapter** (reference implementation): `packages/core/apikeyrouter/infrastructure/adapters/openai_adapter.py`

## Getting Help

- **Documentation**: See [docs/](../) for detailed documentation
- **Examples**: See [docs/examples/](../examples/) for more examples
- **Issues**: Open an issue on GitHub for questions or problems


