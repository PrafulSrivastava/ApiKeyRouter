# Quick Start Guide

Get started with ApiKeyRouter in under 10 minutes.

## Installation

```bash
# Install from PyPI (when available)
pip install apikeyrouter-core

# Or install from source
git clone https://github.com/yourorg/apikeyrouter
cd apikeyrouter
poetry install
```

## Library Mode (Python Application)

### Basic Usage

```python
import asyncio
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.infrastructure.adapters import OpenAIAdapter

async def main():
    # Initialize router
    router = ApiKeyRouter()
    
    # Register provider
    router.register_provider("openai", OpenAIAdapter())
    
    # Register multiple API keys
    await router.register_key("sk-your-openai-key-1", "openai")
    await router.register_key("sk-your-openai-key-2", "openai")
    await router.register_key("sk-your-openai-key-3", "openai")
    
    # Make API call - library handles key switching automatically
    response = await router.route({
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Hello, how are you?"}
        ]
    })
    
    # Response includes completion + metadata
    print(response.content)  # LLM response
    print(f"Key used: {response.metadata.key_used}")
    print(f"Cost: ${response.metadata.cost_actual}")

if __name__ == "__main__":
    asyncio.run(main())
```

### With Routing Objectives

```python
from apikeyrouter.domain.models import RoutingObjective

# Optimize for cost
response = await router.route(
    request_intent={
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "Hello!"}]
    },
    objective=RoutingObjective(primary="cost")
)

# Optimize for reliability
response = await router.route(
    request_intent={...},
    objective=RoutingObjective(primary="reliability")
)

# Multi-objective (cost + reliability)
response = await router.route(
    request_intent={...},
    objective=RoutingObjective(
        primary="cost",
        secondary=["reliability"],
        constraints={"min_reliability": 0.95}
    )
)
```

### With Budget Control

```python
from apikeyrouter.domain.models import BudgetLimit, BudgetScope

# Set daily budget
await router.configure_budget(
    BudgetLimit(
        scope=BudgetScope.GLOBAL,
        limit_amount=100.00,
        period=TimeWindow.DAILY,
        enforcement_mode=EnforcementMode.HARD
    )
)

# Requests that would exceed budget are rejected
try:
    response = await router.route(request_intent)
except BudgetExceededError as e:
    print(f"Budget exceeded: {e.details}")
```

## Proxy Mode (Standalone Service)

### Start Proxy

```bash
# Using Docker
docker-compose up

# Or directly
cd packages/proxy
poetry run uvicorn apikeyrouter_proxy.main:app --reload
```

### Configure Keys

```bash
# Register keys via management API
curl -X POST http://localhost:8000/api/v1/keys \
  -H "X-API-Key: your-management-key" \
  -H "Content-Type: application/json" \
  -d '{
    "key_material": "your-actual-openai-key-here",
    "provider_id": "openai",
    "metadata": {"tier": "pay-as-you-go"}
  }'
```

### Use Proxy (OpenAI-Compatible)

```python
import httpx

# Use just like OpenAI API
response = httpx.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "Hello!"}]
    }
)

# Response includes routing metadata
print(response.json()["routing_metadata"]["key_used"])
print(response.json()["routing_metadata"]["routing_explanation"])
```

## Key Features Demonstrated

### Automatic Key Switching

```python
# Library automatically switches keys when:
# - Key is rate limited (429 error)
# - Key quota exhausted
# - Key fails (network error, timeout)
# - Key is throttled

# You don't need to handle this - it's automatic!
response = await router.route(request_intent)
```

### Quota Awareness

```python
# Library predicts quota exhaustion and routes proactively
# If key1 will exhaust in 2 hours, library routes to key2
# even though key1 is still technically available

response = await router.route(request_intent)
# Library chose key2 because key1 predicted to exhaust soon
```

### Cost Control

```python
# Library estimates cost before execution
# If request would exceed budget, it's rejected (or downgraded)

try:
    response = await router.route(request_intent)
except BudgetExceededError:
    print("Request would exceed budget")
```

### Observability

```python
# Every routing decision is explainable
response = await router.route(request_intent)
print(response.metadata.routing_explanation)
# "Selected key1 because lowest cost ($0.01) while maintaining reliability threshold (>0.95)"

# Get full system state
state = await router.get_state_summary()
print(f"Keys: {state.keys.total}, Exhausted: {state.quotas.exhausted_keys}")
```

## Next Steps

- Read the [Architecture Document](../architecture.md) for detailed design
- Check [Component Specifications](../architecture/component-specifications.md) for implementation details
- Review [API Documentation](../api/openapi.yaml) for proxy endpoints
- See examples in `examples/` directory

