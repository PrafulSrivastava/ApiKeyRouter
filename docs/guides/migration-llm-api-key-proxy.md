# Migration Guide: From LLM-API-Key-Proxy

This guide helps you migrate from [LLM-API-Key-Proxy](https://github.com/your-org/llm-api-key-proxy) to ApiKeyRouter.

## Overview

LLM-API-Key-Proxy is an Express.js proxy service for OpenAI API key management. ApiKeyRouter provides similar functionality with additional intelligent routing, quota awareness, and cost control features.

### Key Differences

| Aspect | LLM-API-Key-Proxy | ApiKeyRouter |
|--------|-------------------|--------------|
| **Language** | Node.js/Express.js | Python/FastAPI |
| **Deployment** | Proxy-only | Library + Proxy |
| **Quota Management** | Reactive counting | Predictive, forward-looking |
| **Routing** | Round-robin or least-used | Multi-objective optimization |
| **Cost Control** | None | Pre-execution estimation & budgets |
| **State Management** | Implicit | Explicit state machine |
| **Explainability** | None | Routing explanations |

## Migration Steps

### Step 1: Install ApiKeyRouter

```bash
# Install the proxy package
pip install apikeyrouter-proxy

# Or from source
git clone https://github.com/your-org/ApiKeyRouter.git
cd ApiKeyRouter/packages/proxy
poetry install
```

### Step 2: Migrate Configuration

#### LLM-API-Key-Proxy Configuration

```javascript
// config.js (LLM-API-Key-Proxy)
module.exports = {
  port: 3000,
  keys: [
    { key: "sk-key-1", provider: "openai" },
    { key: "sk-key-2", provider: "openai" },
    { key: "sk-key-3", provider: "openai" }
  ],
  routing: "round-robin" // or "least-used"
};
```

#### ApiKeyRouter Configuration

```python
# config.py (ApiKeyRouter)
from apikeyrouter import ApiKeyRouter
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

router = ApiKeyRouter()

# Register provider
await router.register_provider("openai", OpenAIAdapter())

# Register keys
await router.register_key("sk-key-1", "openai")
await router.register_key("sk-key-2", "openai")
await router.register_key("sk-key-3", "openai")
```

**Or via environment variables:**

```bash
# .env
APIKEYROUTER_ENCRYPTION_KEY=your-encryption-key
LOG_LEVEL=INFO
```

### Step 3: Start the Proxy Service

#### LLM-API-Key-Proxy

```bash
npm start
# Service runs on http://localhost:3000
```

#### ApiKeyRouter Proxy

```bash
cd packages/proxy
poetry run uvicorn apikeyrouter_proxy.main:app --reload
# Service runs on http://localhost:8000
```

### Step 4: Update API Calls

The API endpoints are compatible, so minimal changes are needed:

#### Before (LLM-API-Key-Proxy)

```javascript
// Client code
const response = await fetch('http://localhost:3000/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer YOUR_KEY'
  },
  body: JSON.stringify({
    model: 'gpt-4',
    messages: [
      { role: 'user', content: 'Hello!' }
    ]
  })
});
```

#### After (ApiKeyRouter Proxy)

```javascript
// Client code (same API, different port)
const response = await fetch('http://localhost:8000/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer YOUR_KEY'
  },
  body: JSON.stringify({
    model: 'gpt-4',
    messages: [
      { role: 'user', content: 'Hello!' }
    ]
  })
});
```

**Note:** The API is compatible, so you only need to change the port (3000 → 8000).

### Step 5: Configure Routing Strategy

#### LLM-API-Key-Proxy

```javascript
// Round-robin routing
routing: "round-robin"

// Or least-used routing
routing: "least-used"
```

#### ApiKeyRouter

```python
# Fairness (round-robin equivalent)
response = await router.route(intent, objective="fairness")

# Reliability (similar to least-used)
response = await router.route(intent, objective="reliability")

# Cost optimization (new feature)
response = await router.route(intent, objective="cost")

# Multi-objective (new feature)
from apikeyrouter.domain.models.routing_decision import RoutingObjective

objective = RoutingObjective(
    primary="cost",
    secondary=["reliability"],
    weights={"cost": 0.7, "reliability": 0.3}
)
response = await router.route(intent, objective=objective)
```

### Step 6: Add Advanced Features (Optional)

ApiKeyRouter provides features not available in LLM-API-Key-Proxy:

#### Budget Enforcement

```python
from apikeyrouter.domain.models.budget import BudgetScope, EnforcementMode, TimeWindow
from decimal import Decimal

# Set daily budget
budget = await router.cost_controller.create_budget(
    scope=BudgetScope.Global,
    limit=Decimal("100.00"),
    period=TimeWindow.Daily,
    enforcement_mode=EnforcementMode.Hard
)

# Requests that would exceed budget are automatically rejected
```

#### Quota Awareness

```python
# ApiKeyRouter automatically tracks quota and predicts exhaustion
# No manual configuration needed - it's built-in
response = await router.route(intent)

# Check quota state
quota_state = await router.quota_awareness_engine.get_quota_state(key_id)
print(f"Capacity state: {quota_state.capacity_state}")
print(f"Remaining: {quota_state.remaining_capacity.value}")
```

#### Routing Explanations

```python
# Get routing decision explanation
response = await router.route(intent)
# Explanation is automatically included in response metadata
print(response.metadata.routing_explanation)
# "Selected key1 because lowest cost ($0.01) while maintaining reliability threshold (>0.95)"
```

## Code Examples

### Example 1: Basic Proxy Usage

#### Before (LLM-API-Key-Proxy)

```javascript
// server.js
const express = require('express');
const { LLMProxy } = require('llm-api-key-proxy');

const app = express();
const proxy = new LLMProxy({
  keys: [
    { key: "sk-key-1", provider: "openai" },
    { key: "sk-key-2", provider: "openai" }
  ],
  routing: "round-robin"
});

app.use('/v1', proxy.middleware());
app.listen(3000);
```

#### After (ApiKeyRouter Proxy)

```python
# main.py
from fastapi import FastAPI
from apikeyrouter_proxy.main import app

# Keys registered via management API or environment variables
# Proxy automatically handles routing

# Run with: uvicorn apikeyrouter_proxy.main:app --reload
```

### Example 2: Library Usage

#### Before (LLM-API-Key-Proxy - Library Mode Not Available)

LLM-API-Key-Proxy is proxy-only, so you must use HTTP calls.

#### After (ApiKeyRouter - Library Mode)

```python
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

router = ApiKeyRouter()
await router.register_provider("openai", OpenAIAdapter())
await router.register_key("sk-key-1", "openai")
await router.register_key("sk-key-2", "openai")

# Direct library usage (no HTTP overhead)
intent = RequestIntent(
    model="gpt-4",
    messages=[Message(role="user", content="Hello!")],
    provider_id="openai"
)
response = await router.route(intent, objective="cost")
print(response.content)
```

### Example 3: Error Handling

#### Before (LLM-API-Key-Proxy)

```javascript
// Manual error handling
try {
  const response = await fetch('http://localhost:3000/v1/chat/completions', {...});
  if (!response.ok) {
    // Handle error
    if (response.status === 429) {
      // Rate limit - wait and retry
    }
  }
} catch (error) {
  // Handle network error
}
```

#### After (ApiKeyRouter)

```python
from apikeyrouter.domain.components.routing_engine import NoEligibleKeysError
from apikeyrouter.domain.models.system_error import SystemError, ErrorCategory

try:
    response = await router.route(intent)
except NoEligibleKeysError as e:
    # All keys exhausted or rate limited
    print(f"No keys available: {e}")
except SystemError as e:
    if e.category == ErrorCategory.RateLimitError:
        # Automatic retry with different key already attempted
        print(f"Rate limit: {e.message}")
        if e.retry_after:
            await asyncio.sleep(e.retry_after)
    else:
        # Other errors
        print(f"Error: {e.message}")
```

## Configuration Differences

### Port Configuration

| Setting | LLM-API-Key-Proxy | ApiKeyRouter |
|---------|-------------------|--------------|
| **Default Port** | 3000 | 8000 |
| **Configuration** | `config.js` | Environment variables or code |

### Key Management

| Feature | LLM-API-Key-Proxy | ApiKeyRouter |
|---------|-------------------|--------------|
| **Key Storage** | In-memory or config file | Encrypted in StateStore |
| **Key Registration** | Config file | API or code |
| **Key Rotation** | Manual | Built-in rotation support |

### Routing Configuration

| Feature | LLM-API-Key-Proxy | ApiKeyRouter |
|---------|-------------------|--------------|
| **Routing Modes** | Round-robin, least-used | Cost, reliability, fairness, multi-objective |
| **Configuration** | Config file | Per-request or default |

## Troubleshooting

### Issue: Port Already in Use

**Problem:** Port 8000 is already in use.

**Solution:**
```bash
# Change port via environment variable
export PROXY_PORT=3000
poetry run uvicorn apikeyrouter_proxy.main:app --port 3000
```

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

### Issue: Different Routing Behavior

**Problem:** Routing behaves differently than LLM-API-Key-Proxy.

**Solution:**
```python
# Use fairness objective for round-robin behavior
response = await router.route(intent, objective="fairness")

# Use reliability objective for least-used behavior
response = await router.route(intent, objective="reliability")
```

### Issue: Missing OAuth Support

**Problem:** LLM-API-Key-Proxy has OAuth support, ApiKeyRouter doesn't yet.

**Solution:**
- OAuth support is planned for future release
- For now, use API keys directly
- Track issue on GitHub for updates

## Feature Parity

### ✅ Fully Supported

- OpenAI-compatible API endpoints
- Round-robin routing (via "fairness" objective)
- Least-used routing (via "reliability" objective)
- Automatic key switching on failures
- Proxy service mode
- Multiple key support

### ⚠️ Partially Supported

- **Detailed Logging**: ApiKeyRouter has structured logging, but format may differ
- **Rate Limiting**: Built-in but may behave differently

### ❌ Not Yet Supported

- **OAuth Credential Management**: Planned for future release
- **Exclusive Provider Support**: Not yet implemented

### ✅ Additional Features (Not in LLM-API-Key-Proxy)

- Predictive quota management
- Cost optimization routing
- Budget enforcement
- Multi-objective routing
- Routing explanations
- Library mode (embeddable)
- Explicit state management

## Next Steps

1. **Test the migration** with a small subset of keys
2. **Monitor routing behavior** to ensure it meets your needs
3. **Configure routing objectives** based on your priorities
4. **Set up budgets** if cost control is important
5. **Read the [User Guide](./user-guide.md)** for advanced features

## Getting Help

- **Documentation**: See [docs/](../) for detailed documentation
- **API Reference**: See [docs/api/API_REFERENCE.md](../api/API_REFERENCE.md)
- **Examples**: See [docs/examples/](../examples/) for code examples
- **Issues**: Open an issue on GitHub for questions or problems

