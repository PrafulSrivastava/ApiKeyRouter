# Migration Overview

This guide helps you migrate to ApiKeyRouter from other solutions. Choose the migration path that matches your current setup.

## Quick Decision Guide

**Which migration guide should I follow?**

- **Using LLM-API-Key-Proxy?** → [Migration from LLM-API-Key-Proxy](./migration-llm-api-key-proxy.md)
- **Using LiteLLM?** → [Migration from LiteLLM](./migration-litellm.md)
- **Managing keys manually?** → [Migration from Manual Key Management](./migration-manual.md)
- **Not sure?** → Read the [Feature Comparison Table](#feature-comparison-table) below

## Feature Comparison Table

### ApiKeyRouter vs LLM-API-Key-Proxy

| Feature | ApiKeyRouter | LLM-API-Key-Proxy |
|---------|--------------|-------------------|
| **Quota Awareness** | ✅ Predictive, forward-looking | ⚠️ Reactive counting only |
| **Intelligent Routing** | ✅ Multi-objective (cost, reliability, fairness) | ⚠️ Round-robin or least-used |
| **Cost Control** | ✅ Pre-execution estimation & budget enforcement | ❌ No cost control |
| **State Management** | ✅ Explicit, observable state machine | ⚠️ Implicit state |
| **Provider Abstraction** | ✅ General-purpose (any API) | ⚠️ LLM-focused |
| **Explainable Decisions** | ✅ Routing explanations | ❌ No explanations |
| **Graceful Failure** | ✅ Reduces load under failure | ⚠️ Basic retry logic |
| **Library Mode** | ✅ Embeddable Python library | ❌ Proxy-only |
| **Proxy Mode** | ✅ FastAPI proxy service | ✅ Express.js proxy |
| **OpenAI Compatibility** | ✅ OpenAI-compatible endpoints | ✅ OpenAI-compatible |
| **OAuth Support** | ❌ Not yet implemented | ✅ OAuth credential management |
| **Detailed Logging** | ✅ Structured logging | ✅ Detailed logging |

**Key Differentiators:**
- **Predictive Quota Management**: ApiKeyRouter predicts exhaustion before it happens
- **Intelligent Routing**: Multi-objective optimization with explainable decisions
- **Proactive Cost Control**: Budget enforcement before execution
- **Library + Proxy**: Use as library or standalone proxy

### ApiKeyRouter vs LiteLLM

| Feature | ApiKeyRouter | LiteLLM |
|---------|--------------|---------|
| **Quota Awareness** | ✅ Predictive, forward-looking | ⚠️ Reactive counting only |
| **Intelligent Routing** | ✅ Multi-objective optimization | ⚠️ Simple fallback |
| **Cost Control** | ✅ Pre-execution estimation & budgets | ⚠️ Post-execution tracking |
| **State Management** | ✅ Explicit state machine | ⚠️ Implicit state |
| **Provider Coverage** | ⚠️ Core providers (extensible) | ✅ Wide provider coverage |
| **Unified API** | ✅ RequestIntent abstraction | ✅ Unified API |
| **Fallback Mechanisms** | ✅ Automatic failover | ✅ Automatic fallback |
| **Library Mode** | ✅ Embeddable Python library | ✅ Python library |
| **Proxy Mode** | ✅ FastAPI proxy | ✅ Proxy server |
| **OpenAI Compatibility** | ✅ OpenAI-compatible | ✅ OpenAI-compatible |
| **Documentation** | ✅ Comprehensive guides | ✅ Good documentation |
| **Community** | ⚠️ Growing | ✅ Active community |

**Key Differentiators:**
- **Predictive Quota Management**: ApiKeyRouter predicts exhaustion before it happens
- **Intelligent Routing**: Multi-objective optimization (cost, reliability, fairness)
- **Proactive Cost Control**: Budget enforcement before execution
- **Explainable Decisions**: Every routing decision includes explanation

### ApiKeyRouter vs Manual Key Management

| Feature | ApiKeyRouter | Manual Management |
|---------|--------------|-------------------|
| **Automatic Key Switching** | ✅ Automatic on failures | ❌ Manual handling required |
| **Quota Tracking** | ✅ Predictive, multi-state | ❌ Manual tracking |
| **Cost Optimization** | ✅ Automatic cost-aware routing | ❌ Manual cost management |
| **Budget Enforcement** | ✅ Automatic budget checks | ❌ Manual budget tracking |
| **Failure Handling** | ✅ Automatic retry with different keys | ❌ Manual error handling |
| **State Management** | ✅ Explicit state machine | ❌ No state tracking |
| **Observability** | ✅ Structured logging & metrics | ❌ Manual logging |
| **Routing Intelligence** | ✅ Multi-objective optimization | ❌ Manual key selection |
| **Key Rotation** | ✅ Built-in rotation support | ❌ Manual rotation |
| **Provider Abstraction** | ✅ Unified interface | ❌ Provider-specific code |

**Key Benefits:**
- **Zero Manual Work**: Automatic key switching, quota tracking, and cost optimization
- **Predictive Intelligence**: Predict quota exhaustion before it happens
- **Cost Savings**: Automatic cost-aware routing minimizes expenses
- **Reliability**: Automatic failover ensures high availability

## Common Migration Patterns

### Pattern 1: Library Integration

**Before (Manual):**
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

**After (ApiKeyRouter):**
```python
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message

router = ApiKeyRouter()
await router.register_provider("openai", OpenAIAdapter())
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
```

### Pattern 2: Proxy Migration

**Before (LLM-API-Key-Proxy):**
```bash
# Start proxy
npm start

# Use proxy
curl http://localhost:3000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_KEY" \
  -d '{"model": "gpt-4", "messages": [...]}'
```

**After (ApiKeyRouter Proxy):**
```bash
# Start proxy
cd packages/proxy
poetry run uvicorn apikeyrouter_proxy.main:app --reload

# Use proxy (same API)
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_KEY" \
  -d '{"model": "gpt-4", "messages": [...]}'
```

### Pattern 3: Cost Optimization

**Before (Manual):**
```python
# Manual cost tracking
total_cost = 0.0
budget_limit = 100.0

def make_request(messages):
    global total_cost
    if total_cost >= budget_limit:
        raise Exception("Budget exceeded")
    
    response = openai.ChatCompletion.create(...)
    # Manual cost calculation
    cost = calculate_cost(response)
    total_cost += cost
    return response
```

**After (ApiKeyRouter):**
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

# Automatic cost estimation and budget checking
response = await router.route(intent, objective="cost")
# Budget automatically enforced before execution
```

## Migration Steps Overview

### Step 1: Install ApiKeyRouter

```bash
pip install apikeyrouter-core
# or
poetry add apikeyrouter-core
```

### Step 2: Register Providers and Keys

```python
from apikeyrouter import ApiKeyRouter
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

router = ApiKeyRouter()
await router.register_provider("openai", OpenAIAdapter())

# Register your existing keys
await router.register_key("sk-your-key-1", "openai")
await router.register_key("sk-your-key-2", "openai")
```

### Step 3: Update Your Code

Replace manual key management or competitor API calls with ApiKeyRouter:

```python
# Old way
response = openai.ChatCompletion.create(...)

# New way
response = await router.route(intent)
```

### Step 4: Configure Routing Objectives

Choose your routing strategy:

```python
# Cost optimization
response = await router.route(intent, objective="cost")

# Reliability optimization
response = await router.route(intent, objective="reliability")

# Fairness (default)
response = await router.route(intent, objective="fairness")
```

### Step 5: Set Up Budgets (Optional)

```python
from apikeyrouter.domain.models.budget import BudgetScope, EnforcementMode, TimeWindow
from decimal import Decimal

budget = await router.cost_controller.create_budget(
    scope=BudgetScope.Global,
    limit=Decimal("100.00"),
    period=TimeWindow.Daily,
    enforcement_mode=EnforcementMode.Hard
)
```

## Next Steps

1. **Choose your migration guide:**
   - [From LLM-API-Key-Proxy](./migration-llm-api-key-proxy.md)
   - [From LiteLLM](./migration-litellm.md)
   - [From Manual Key Management](./migration-manual.md)

2. **Read the [User Guide](./user-guide.md)** for detailed usage instructions

3. **Check the [API Reference](../api/API_REFERENCE.md)** for complete API documentation

## Getting Help

- **Documentation**: See [docs/](../) for detailed documentation
- **Examples**: See [docs/examples/](../examples/) for code examples
- **Issues**: Open an issue on GitHub for questions or problems


