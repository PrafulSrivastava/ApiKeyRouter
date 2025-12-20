# ApiKeyRouter API Reference

**Simple, clean API documentation for client developers.**

This document shows only the public APIs you need to use. All internal complexity is abstracted away.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Core APIs](#core-apis)
   - [Initialization](#initialization)
   - [Provider Registration](#provider-registration)
   - [Key Registration](#key-registration)
   - [Making Requests](#making-requests)
3. [Advanced Features](#advanced-features)
   - [Routing Objectives](#routing-objectives)
   - [Cost Control](#cost-control)
   - [Quota Management](#quota-management)
   - [Key Management](#key-management)
4. [Response Objects](#response-objects)
5. [Error Handling](#error-handling)

---

## Quick Start

```python
import asyncio
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

async def main():
    # 1. Initialize router
    router = ApiKeyRouter()
    
    # 2. Register provider
    await router.register_provider("openai", OpenAIAdapter())
    
    # 3. Register API keys
    await router.register_key("sk-your-key-1", "openai")
    await router.register_key("sk-your-key-2", "openai")
    
    # 4. Make requests - that's it!
    response = await router.route(
        RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")],
            provider_id="openai"
        )
    )
    
    print(response.content)  # LLM response
    print(f"Key used: {response.key_used}")
    print(f"Cost: ${response.cost}")

asyncio.run(main())
```

---

## Core APIs

### Initialization

**Create a router instance:**

```python
from apikeyrouter import ApiKeyRouter

# Simple initialization (uses defaults)
router = ApiKeyRouter()

# With custom configuration
from apikeyrouter.infrastructure.config.settings import RouterSettings
config = RouterSettings(max_decisions=1000)
router = ApiKeyRouter(config=config)
```

**Parameters:**
- `state_store` (optional): Custom state store implementation
- `observability_manager` (optional): Custom logging/observability
- `config` (optional): RouterSettings or dict with configuration

**Returns:** `ApiKeyRouter` instance

---

### Provider Registration

**Register a provider adapter:**

```python
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

# Register OpenAI
openai_adapter = OpenAIAdapter()
await router.register_provider("openai", openai_adapter)

# Register multiple providers
# await router.register_provider("anthropic", anthropic_adapter)
```

**Method:** `register_provider(provider_id: str, adapter: ProviderAdapter, overwrite: bool = False)`

**Parameters:**
- `provider_id` (str): Unique identifier for the provider (e.g., "openai", "anthropic")
- `adapter` (ProviderAdapter): Provider adapter instance
- `overwrite` (bool, optional): Allow overwriting existing provider (default: False)

**Raises:**
- `ValueError`: If provider_id is invalid or already registered (unless overwrite=True)

---

### Key Registration

**Register API keys:**

```python
# Basic registration
key = await router.register_key(
    key_material="sk-your-api-key",
    provider_id="openai"
)

# With metadata (for advanced routing)
key = await router.register_key(
    key_material="sk-your-api-key",
    provider_id="openai",
    metadata={
        "account_tier": "pro",
        "region": "us-east",
        "cost_per_1k": "0.01",
        "team": "engineering"
    }
)
```

**Method:** `register_key(key_material: str, provider_id: str, metadata: dict | None = None)`

**Parameters:**
- `key_material` (str): Your API key (will be encrypted automatically)
- `provider_id` (str): Provider this key belongs to (must be registered first)
- `metadata` (dict, optional): Key metadata for routing decisions

**Returns:** `APIKey` object with:
- `id`: Unique key identifier
- `provider_id`: Provider identifier
- `state`: Current key state (Available, Throttled, etc.)
- `usage_count`: Number of requests made
- `failure_count`: Number of failures
- `metadata`: Your provided metadata

**Raises:**
- `ValueError`: If provider_id is not registered
- `KeyRegistrationError`: If registration fails

**Note:** Keys are automatically encrypted using Fernet (AES-256). Set `APIKEYROUTER_ENCRYPTION_KEY` environment variable, or the library will generate one.

---

### Making Requests

**Route and execute a request:**

```python
from apikeyrouter.domain.models.request_intent import RequestIntent, Message

# Using RequestIntent object
intent = RequestIntent(
    model="gpt-4",
    messages=[
        Message(role="user", content="Hello, world!")
    ],
    provider_id="openai",
    parameters={
        "temperature": 0.7,
        "max_tokens": 100
    }
)

response = await router.route(intent)
print(response.content)
```

**Or using a dictionary:**

```python
# Using dict (simpler for some use cases)
response = await router.route({
    "model": "gpt-4",
    "messages": [
        {"role": "user", "content": "Hello, world!"}
    ],
    "provider_id": "openai",
    "parameters": {
        "temperature": 0.7,
        "max_tokens": 100
    }
})
```

**Method:** `route(request_intent: RequestIntent | dict, objective: RoutingObjective | str | None = None)`

**Parameters:**
- `request_intent` (RequestIntent | dict): Request details
  - **Required fields:**
    - `model` (str): Model identifier (e.g., "gpt-4", "gpt-3.5-turbo")
    - `messages` (list[Message]): Conversation messages
    - `provider_id` (str): Provider to route to
  - **Optional fields:**
    - `parameters` (dict): Request parameters (temperature, max_tokens, etc.)
- `objective` (str | RoutingObjective, optional): Routing objective
  - String: `"cost"`, `"reliability"`, `"fairness"` (default: `"fairness"`)
  - RoutingObjective: Advanced multi-objective routing

**Returns:** `SystemResponse` object (see [Response Objects](#response-objects))

**Raises:**
- `ValueError`: If request_intent is invalid
- `NoEligibleKeysError`: If no keys are available
- `SystemError`: If request execution fails

---

## Advanced Features

### Routing Objectives

**Control how keys are selected:**

```python
# Cost optimization (minimize expenses)
response = await router.route(intent, objective="cost")

# Reliability optimization (maximize success rate)
response = await router.route(intent, objective="reliability")

# Fairness (distribute load evenly) - DEFAULT
response = await router.route(intent, objective="fairness")

# Multi-objective with weights
from apikeyrouter.domain.models.routing_decision import RoutingObjective

objective = RoutingObjective(
    primary="cost",
    secondary=["reliability", "fairness"],
    weights={"cost": 0.5, "reliability": 0.3, "fairness": 0.2}
)
response = await router.route(intent, objective=objective)
```

**Available Objectives:**
- `"cost"`: Select key with lowest cost
- `"reliability"`: Select key with best success rate
- `"fairness"`: Distribute load evenly (round-robin)

---

### Cost Control

**Set budgets and enforce cost limits:**

```python
from apikeyrouter.domain.components.cost_controller import CostController
from apikeyrouter.domain.models.budget import BudgetScope, EnforcementMode, TimeWindow
from decimal import Decimal

# Get cost controller
cost_controller = router.cost_controller

# Create a daily budget with hard enforcement
budget = await cost_controller.create_budget(
    scope=BudgetScope.Global,
    limit=Decimal("100.00"),  # $100 daily limit
    period=TimeWindow.Daily,
    enforcement_mode=EnforcementMode.Hard  # Reject requests that exceed budget
)

# Update spending (typically done automatically after requests)
await cost_controller.update_spending(budget.id, Decimal("25.50"))

# Check budget before making request
from apikeyrouter.domain.models.request_intent import RequestIntent
request_intent = RequestIntent(...)
cost_estimate = await cost_controller.estimate_request_cost(
    request_intent=request_intent,
    provider_id="openai",
    key_id="some-key-id"
)

budget_check = await cost_controller.check_budget(
    request_intent=request_intent,
    cost_estimate=cost_estimate,
    provider_id="openai",
    key_id="some-key-id"
)

if budget_check.allowed:
    response = await router.route(request_intent)
else:
    print(f"Budget exceeded: {budget_check.remaining_budget} remaining")
```

**Budget Scopes:**
- `BudgetScope.Global`: Applies to all requests
- `BudgetScope.PerProvider`: Per provider
- `BudgetScope.PerKey`: Per API key

**Enforcement Modes:**
- `EnforcementMode.Hard`: Reject requests that exceed budget
- `EnforcementMode.Soft`: Allow but warn when budget exceeded

**Time Windows:**
- `TimeWindow.Daily`: Resets daily
- `TimeWindow.Monthly`: Resets monthly
- `TimeWindow.Hourly`: Resets hourly

---

### Quota Management

**Track and manage API key quotas:**

```python
from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.domain.models.quota_state import TimeWindow

# Get quota engine
quota_engine = router.quota_awareness_engine

# Update capacity after a request
await quota_engine.update_capacity(
    key_id=key.id,
    used_tokens=1000,
    time_window=TimeWindow.Daily
)

# Get quota state
quota_state = await quota_engine.get_quota_state(key.id, TimeWindow.Daily)

print(f"Used: {quota_state.used_capacity}")
print(f"Remaining: {quota_state.remaining_capacity.value}")
print(f"State: {quota_state.capacity_state}")  # Abundant, Constrained, Critical, Exhausted
```

**Capacity States:**
- `Abundant`: Plenty of capacity remaining
- `Constrained`: Getting low, but still usable
- `Critical`: Very low, prefer other keys
- `Exhausted`: No capacity remaining

---

### Key Management

**Manage keys throughout their lifecycle:**

```python
from apikeyrouter.domain.models.api_key import KeyState

# Update key state
await router.key_manager.update_key_state(
    key_id=key.id,
    new_state=KeyState.Throttled,
    reason="Rate limit encountered"
)

# Revoke a key
await router.key_manager.revoke_key(
    key_id=key.id,
    reason="Security incident"
)

# Rotate a key (preserves key ID and metadata)
new_key = await router.key_manager.rotate_key(
    key_id=key.id,
    new_key_material="sk-new-key-material"
)

# Get eligible keys
eligible_keys = await router.key_manager.get_eligible_keys(
    provider_id="openai",
    policy=None
)

# Get a specific key
key = await router.key_manager.get_key(key_id)
```

**Key States:**
- `Available`: Ready for use
- `Throttled`: Temporarily unavailable (rate limit, cooldown)
- `Exhausted`: Quota exhausted
- `Disabled`: Manually disabled or revoked
- `Invalid`: Authentication failure

---

## Response Objects

**SystemResponse** - The response from `router.route()`:

```python
response: SystemResponse

# Main content
response.content          # str: LLM response text
response.key_used         # str: ID of key used
response.request_id       # str: Unique request identifier

# Cost information
response.cost             # Decimal: Actual cost of request
response.cost_estimate    # CostEstimate: Estimated cost (if available)

# Metadata
response.metadata         # ResponseMetadata object
response.metadata.model   # str: Model used
response.metadata.provider_id  # str: Provider used
response.metadata.token_usage  # TokenUsage object
response.metadata.token_usage.input_tokens   # int
response.metadata.token_usage.output_tokens  # int
response.metadata.token_usage.total         # int
response.metadata.response_time            # float: Seconds
response.metadata.correlation_id           # str: For tracing

# Error information (if request failed)
response.error            # SystemError | None
```

**Example:**

```python
response = await router.route(intent)

if response.error:
    print(f"Error: {response.error.message}")
    print(f"Category: {response.error.category}")
    print(f"Retryable: {response.error.retryable}")
else:
    print(f"Response: {response.content}")
    print(f"Tokens used: {response.metadata.token_usage.total}")
    print(f"Cost: ${response.cost}")
    print(f"Key: {response.key_used}")
```

---

## Error Handling

**Common exceptions:**

```python
from apikeyrouter.domain.components.key_manager import KeyRegistrationError
from apikeyrouter.domain.components.routing_engine import NoEligibleKeysError
from apikeyrouter.domain.models.system_error import SystemError

try:
    response = await router.route(intent)
except NoEligibleKeysError as e:
    # No keys available (all exhausted, throttled, or disabled)
    print(f"No eligible keys: {e}")
except ValueError as e:
    # Invalid request (missing fields, invalid format)
    print(f"Invalid request: {e}")
except SystemError as e:
    # Request execution failed (from provider adapter)
    print(f"Request failed: {e.message}")
    print(f"Category: {e.category}")
    print(f"Retryable: {e.retryable}")
except KeyRegistrationError as e:
    # Key registration failed
    print(f"Key registration failed: {e}")
```

**Error Categories:**
- `AuthenticationError`: Invalid API key
- `RateLimitError`: Rate limit exceeded (429)
- `QuotaExceededError`: Quota exhausted
- `NetworkError`: Network/connection issues
- `TimeoutError`: Request timeout
- `ProviderError`: Provider-specific error
- `ValidationError`: Invalid request format

**Retry Logic:**

The router automatically handles retries for retryable errors. You can check if an error is retryable:

```python
if response.error and response.error.retryable:
    # Error is retryable - router may have already retried
    # You can manually retry if needed
    pass
```

---

## Complete Example

```python
import asyncio
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter
from apikeyrouter.domain.components.cost_controller import CostController
from apikeyrouter.domain.models.budget import BudgetScope, EnforcementMode, TimeWindow
from decimal import Decimal

async def main():
    # Initialize
    router = ApiKeyRouter()
    
    # Register provider
    await router.register_provider("openai", OpenAIAdapter())
    
    # Register keys
    key1 = await router.register_key(
        "sk-key-1",
        "openai",
        metadata={"cost_per_1k": "0.01", "tier": "pro"}
    )
    key2 = await router.register_key(
        "sk-key-2",
        "openai",
        metadata={"cost_per_1k": "0.02", "tier": "basic"}
    )
    
    # Set up budget
    budget = await router.cost_controller.create_budget(
        scope=BudgetScope.Global,
        limit=Decimal("50.00"),
        period=TimeWindow.Daily,
        enforcement_mode=EnforcementMode.Hard
    )
    
    # Make requests
    for i in range(5):
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content=f"Request {i+1}")],
            provider_id="openai"
        )
        
        try:
            response = await router.route(intent, objective="cost")
            print(f"Request {i+1}: {response.content[:50]}...")
            print(f"  Key: {response.key_used}")
            print(f"  Cost: ${response.cost}")
        except Exception as e:
            print(f"Request {i+1} failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Summary

**Three main APIs you need:**

1. **`router.register_provider()`** - Register a provider adapter
2. **`router.register_key()`** - Register API keys
3. **`router.route()`** - Make requests (handles everything automatically)

**That's it!** The router handles:
- ✅ Automatic key selection
- ✅ Failover on errors
- ✅ Quota tracking
- ✅ Cost optimization
- ✅ Load balancing
- ✅ State management

All complexity is abstracted away. Just register providers and keys, then call `route()`.

---

## Next Steps

- See `packages/core/README.md` for detailed documentation
- Check `packages/core/test_manual_example.py` for comprehensive examples
- Review `docs/architecture/` for design details (if contributing)

