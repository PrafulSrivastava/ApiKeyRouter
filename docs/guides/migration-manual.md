# Migration Guide: From Manual Key Management

This guide helps you migrate from manual API key management to ApiKeyRouter.

## Overview

If you're currently managing API keys manually in your code, ApiKeyRouter can automate key switching, quota tracking, cost optimization, and error handling.

### Benefits of Migration

| Manual Management | ApiKeyRouter |
|-------------------|-------------|
| ❌ Manual key selection | ✅ Automatic intelligent routing |
| ❌ Manual error handling | ✅ Automatic retry with different keys |
| ❌ Manual quota tracking | ✅ Predictive quota management |
| ❌ Manual cost tracking | ✅ Automatic cost optimization |
| ❌ Manual state management | ✅ Explicit state machine |
| ❌ No observability | ✅ Structured logging & metrics |

## Migration Steps

### Step 1: Install ApiKeyRouter

```bash
# Install the core library
pip install apikeyrouter-core

# Or from source
git clone https://github.com/your-org/ApiKeyRouter.git
cd ApiKeyRouter/packages/core
poetry install
```

### Step 2: Replace Manual Key Management

#### Before (Manual Management)

```python
# Manual key management
keys = ["sk-key-1", "sk-key-2", "sk-key-3"]
current_key_index = 0

def make_request(messages):
    global current_key_index
    try:
        response = openai.ChatCompletion.create(
            api_key=keys[current_key_index],
            messages=messages
        )
        return response
    except Exception as e:
        # Manual error handling
        current_key_index = (current_key_index + 1) % len(keys)
        return make_request(messages)  # Retry
```

#### After (ApiKeyRouter)

```python
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

router = ApiKeyRouter()
await router.register_provider("openai", OpenAIAdapter())

# Register your existing keys
await router.register_key("sk-key-1", "openai")
await router.register_key("sk-key-2", "openai")
await router.register_key("sk-key-3", "openai")

# Automatic routing, retry, and error handling
intent = RequestIntent(
    model="gpt-4",
    messages=[Message(role="user", content="Hello!")],
    provider_id="openai"
)
response = await router.route(intent)
# No manual key selection or error handling needed!
```

### Step 3: Replace Manual Error Handling

#### Before (Manual Error Handling)

```python
import openai
import time

keys = ["sk-key-1", "sk-key-2", "sk-key-3"]
current_key_index = 0

def make_request_with_retry(messages, max_retries=3):
    global current_key_index
    for attempt in range(max_retries):
        try:
            response = openai.ChatCompletion.create(
                api_key=keys[current_key_index],
                messages=messages
            )
            return response
        except openai.RateLimitError as e:
            # Manual rate limit handling
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                current_key_index = (current_key_index + 1) % len(keys)
                continue
            raise
        except openai.AuthenticationError as e:
            # Manual auth error handling
            current_key_index = (current_key_index + 1) % len(keys)
            if attempt < max_retries - 1:
                continue
            raise
        except Exception as e:
            # Manual generic error handling
            current_key_index = (current_key_index + 1) % len(keys)
            if attempt < max_retries - 1:
                continue
            raise
    raise Exception("All retries exhausted")
```

#### After (ApiKeyRouter)

```python
from apikeyrouter.domain.components.routing_engine import NoEligibleKeysError
from apikeyrouter.domain.models.system_error import SystemError

try:
    response = await router.route(intent)
    # Automatic retry with different keys on failure
    # Automatic rate limit handling
    # Automatic error categorization
except NoEligibleKeysError as e:
    # All keys exhausted - handle gracefully
    print(f"No keys available: {e}")
except SystemError as e:
    # System error with category and retry information
    print(f"Error: {e.category.value} - {e.message}")
    if e.retryable and e.retry_after:
        await asyncio.sleep(e.retry_after)
        # Retry if needed
```

### Step 4: Replace Manual Quota Tracking

#### Before (Manual Quota Tracking)

```python
# Manual quota tracking
quota_usage = {
    "sk-key-1": {"used": 0, "limit": 1000000, "reset_at": None},
    "sk-key-2": {"used": 0, "limit": 1000000, "reset_at": None},
    "sk-key-3": {"used": 0, "limit": 1000000, "reset_at": None}
}

def make_request(messages):
    # Manual quota check
    for key_id, quota in quota_usage.items():
        if quota["used"] < quota["limit"]:
            try:
                response = openai.ChatCompletion.create(
                    api_key=key_id,
                    messages=messages
                )
                # Manual quota update
                quota["used"] += response.usage.total_tokens
                return response
            except Exception as e:
                continue
    raise Exception("All quotas exhausted")
```

#### After (ApiKeyRouter)

```python
# Automatic quota tracking and prediction
response = await router.route(intent)

# Quota automatically updated after request
# Quota exhaustion automatically predicted
# Keys automatically filtered when quota exhausted

# Check quota state if needed
quota_state = await router.quota_awareness_engine.get_quota_state(key_id)
print(f"Capacity state: {quota_state.capacity_state}")
print(f"Remaining: {quota_state.remaining_capacity.value}")
```

### Step 5: Replace Manual Cost Tracking

#### Before (Manual Cost Tracking)

```python
# Manual cost tracking
total_cost = 0.0
budget_limit = 100.0
cost_per_1k_tokens = 0.03

def make_request(messages):
    global total_cost
    if total_cost >= budget_limit:
        raise Exception("Budget exceeded")
    
    response = openai.ChatCompletion.create(
        api_key=keys[0],
        messages=messages
    )
    
    # Manual cost calculation
    tokens_used = response.usage.total_tokens
    cost = (tokens_used / 1000) * cost_per_1k_tokens
    total_cost += cost
    
    if total_cost >= budget_limit:
        raise Exception("Budget exceeded")
    
    return response
```

#### After (ApiKeyRouter)

```python
from apikeyrouter.domain.models.budget import BudgetScope, EnforcementMode, TimeWindow
from decimal import Decimal

# Set budget (automatic enforcement)
budget = await router.cost_controller.create_budget(
    scope=BudgetScope.Global,
    limit=Decimal("100.00"),
    period=TimeWindow.Daily,
    enforcement_mode=EnforcementMode.Hard
)

# Automatic cost estimation before execution
# Automatic budget checking
# Automatic rejection if budget would be exceeded
response = await router.route(intent, objective="cost")
# No manual cost tracking needed!
```

## Code Examples

### Example 1: Basic Key Switching

#### Before (Manual)

```python
keys = ["sk-key-1", "sk-key-2", "sk-key-3"]
current_key_index = 0

def get_next_key():
    global current_key_index
    key = keys[current_key_index]
    current_key_index = (current_key_index + 1) % len(keys)
    return key

response = openai.ChatCompletion.create(
    api_key=get_next_key(),
    messages=[{"role": "user", "content": "Hello!"}]
)
```

#### After (ApiKeyRouter)

```python
# Automatic round-robin (fairness objective)
response = await router.route(intent, objective="fairness")
# Automatically rotates through keys
```

### Example 2: Cost-Aware Key Selection

#### Before (Manual)

```python
keys_with_costs = [
    {"key": "sk-key-1", "cost_per_1k": 0.03},
    {"key": "sk-key-2", "cost_per_1k": 0.01},
    {"key": "sk-key-3", "cost_per_1k": 0.05}
]

def get_cheapest_key():
    return min(keys_with_costs, key=lambda x: x["cost_per_1k"])

response = openai.ChatCompletion.create(
    api_key=get_cheapest_key()["key"],
    messages=[{"role": "user", "content": "Hello!"}]
)
```

#### After (ApiKeyRouter)

```python
# Register keys with cost metadata
await router.register_key(
    "sk-key-1", "openai",
    metadata={"cost_per_1k": "0.03"}
)
await router.register_key(
    "sk-key-2", "openai",
    metadata={"cost_per_1k": "0.01"}
)
await router.register_key(
    "sk-key-3", "openai",
    metadata={"cost_per_1k": "0.05"}
)

# Automatic cost-aware routing
response = await router.route(intent, objective="cost")
# Automatically selects cheapest available key
```

### Example 3: Reliability-Aware Key Selection

#### Before (Manual)

```python
key_stats = {
    "sk-key-1": {"success_count": 100, "failure_count": 5},
    "sk-key-2": {"success_count": 95, "failure_count": 10},
    "sk-key-3": {"success_count": 90, "failure_count": 15}
}

def get_most_reliable_key():
    def reliability_score(stats):
        total = stats["success_count"] + stats["failure_count"]
        return stats["success_count"] / total if total > 0 else 0
    return max(key_stats.items(), key=lambda x: reliability_score(x[1]))[0]

response = openai.ChatCompletion.create(
    api_key=get_most_reliable_key(),
    messages=[{"role": "user", "content": "Hello!"}]
)
```

#### After (ApiKeyRouter)

```python
# Automatic reliability tracking and routing
response = await router.route(intent, objective="reliability")
# Automatically selects most reliable available key
# Tracks success/failure rates automatically
```

### Example 4: State Management

#### Before (Manual)

```python
# Manual state tracking
key_states = {
    "sk-key-1": "available",
    "sk-key-2": "throttled",
    "sk-key-3": "exhausted"
}

def get_available_key():
    for key_id, state in key_states.items():
        if state == "available":
            return key_id
    return None

def update_key_state(key_id, new_state):
    key_states[key_id] = new_state

# Manual state updates
try:
    response = openai.ChatCompletion.create(api_key="sk-key-1", ...)
except openai.RateLimitError:
    update_key_state("sk-key-1", "throttled")
```

#### After (ApiKeyRouter)

```python
# Automatic state management
response = await router.route(intent)

# State automatically updated on:
# - Rate limit errors → Throttled
# - Quota exhaustion → Exhausted
# - Authentication errors → Invalid
# - Cooldown expiration → Available

# Check key state if needed
key = await router.key_manager.get_key(key_id)
print(f"Key state: {key.state}")
```

## Key Registration Process

### Step 1: Initialize Router

```python
from apikeyrouter import ApiKeyRouter
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

router = ApiKeyRouter()
```

### Step 2: Register Provider

```python
openai_adapter = OpenAIAdapter()
await router.register_provider("openai", openai_adapter)
```

### Step 3: Register Keys

```python
# Basic registration
key = await router.register_key(
    key_material="sk-your-openai-key",
    provider_id="openai"
)

# With metadata (for advanced routing)
key = await router.register_key(
    key_material="sk-your-openai-key",
    provider_id="openai",
    metadata={
        "account_tier": "pro",
        "region": "us-east",
        "cost_per_1k": "0.01",
        "team": "engineering"
    }
)
```

### Step 4: Use Router

```python
intent = RequestIntent(
    model="gpt-4",
    messages=[Message(role="user", content="Hello!")],
    provider_id="openai"
)
response = await router.route(intent)
```

## Troubleshooting

### Issue: Keys Not Working

**Problem:** Registered keys don't work.

**Solution:**
```python
# Verify keys are registered
keys = await router.state_store.list_keys(provider_id="openai")
for key in keys:
    print(f"Key: {key.id}, State: {key.state}")

# Check key eligibility
eligible_keys = await router.key_manager.get_eligible_keys("openai")
print(f"Eligible keys: {len(eligible_keys)}")
```

### Issue: Routing Not Optimal

**Problem:** Router doesn't select the best key.

**Solution:**
```python
# Try different routing objectives
response = await router.route(intent, objective="cost")  # Cost optimization
response = await router.route(intent, objective="reliability")  # Reliability
response = await router.route(intent, objective="fairness")  # Fair distribution

# Check routing explanation
print(response.metadata.routing_explanation)
```

### Issue: Budget Exceeded

**Problem:** Requests are rejected due to budget.

**Solution:**
```python
# Check current spending
budget = await router.cost_controller.get_budget(budget_id)
print(f"Spent: ${budget.current_spending}, Limit: ${budget.limit}")

# Increase budget or wait for period reset
# Or use soft enforcement mode
budget.enforcement_mode = EnforcementMode.Soft
```

### Issue: All Keys Exhausted

**Problem:** No eligible keys available.

**Solution:**
```python
# Check key states
state = await router.get_state_summary()
print(f"Available keys: {state.keys.available}")
print(f"Exhausted keys: {state.quotas.exhausted_keys}")

# Register additional keys
await router.register_key("sk-new-key", "openai")

# Or wait for keys to recover (cooldown period)
```

## Benefits Summary

### Automation

- **Automatic Key Switching**: No manual key selection needed
- **Automatic Error Handling**: Retries with different keys automatically
- **Automatic Quota Tracking**: Tracks and predicts quota exhaustion
- **Automatic Cost Optimization**: Selects cheapest available key

### Intelligence

- **Predictive Quota Management**: Predicts exhaustion before it happens
- **Intelligent Routing**: Multi-objective optimization (cost, reliability, fairness)
- **Explainable Decisions**: Every routing decision includes explanation
- **State-Aware Routing**: Routes based on key state and quota

### Observability

- **Structured Logging**: All routing decisions logged
- **Metrics**: Track usage, costs, and performance
- **State Inspection**: Query key states and quota states
- **Routing History**: View past routing decisions

## Next Steps

1. **Register your existing keys** with ApiKeyRouter
2. **Replace manual key management** with router.route() calls
3. **Configure routing objectives** based on your priorities
4. **Set up budgets** if cost control is important
5. **Read the [User Guide](./user-guide.md)** for advanced features

## Getting Help

- **Documentation**: See [docs/](../) for detailed documentation
- **API Reference**: See [docs/api/API_REFERENCE.md](../api/API_REFERENCE.md)
- **Examples**: See [docs/examples/](../examples/) for code examples
- **Issues**: Open an issue on GitHub for questions or problems

