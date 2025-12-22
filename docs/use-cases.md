# ApiKeyRouter Use Cases

This document provides comprehensive use cases demonstrating real-world scenarios where ApiKeyRouter delivers value.

## Table of Contents

1. [Cost Optimization](#1-cost-optimization)
2. [High Availability & Reliability](#2-high-availability--reliability)
3. [Multi-Tenant SaaS Applications](#3-multi-tenant-saas-applications)
4. [Rate Limit Management](#4-rate-limit-management)
5. [Budget Enforcement](#5-budget-enforcement)
6. [Development & Testing](#6-development--testing)
7. [Multi-Provider Strategy](#7-multi-provider-strategy)
8. [Fairness & Load Balancing](#8-fairness--load-balancing)
9. [Enterprise Compliance](#9-enterprise-compliance)
10. [Legacy System Integration](#10-legacy-system-integration)

---

## 1. Cost Optimization

### Scenario: Startup with Limited Budget

**Problem:** A startup needs to use GPT-4 for production but has a tight budget. They want to minimize costs while maintaining quality.

**Solution:** Use cost-optimized routing with automatic model downgrade when appropriate.

```python
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message
from apikeyrouter.domain.models.routing_decision import RoutingObjective, ObjectiveType

router = ApiKeyRouter()

# Register provider and keys
await router.register_provider("openai", OpenAIAdapter())
await router.register_key("sk-premium-key", "openai")  # GPT-4 access
await router.register_key("sk-standard-key", "openai")   # GPT-3.5 access

# Route with cost optimization
response = await router.route(
    RequestIntent(
        model="gpt-4",  # Preferred model
        messages=[Message(role="user", content="Explain quantum computing")],
        parameters={"provider_id": "openai"}
    ),
    objective=RoutingObjective(primary=ObjectiveType.Cost.value)
)

# Router automatically:
# - Estimates costs for both keys
# - Selects cheaper option if quality difference is acceptable
# - Falls back to GPT-4 for complex requests
```

**Benefits:**
- Automatic cost savings (30-50% reduction typical)
- No code changes needed for cost optimization
- Maintains quality for critical requests

---

## 2. High Availability & Reliability

### Scenario: Production Service with Zero Downtime Requirement

**Problem:** A customer-facing chatbot must never fail, even if individual API keys are rate-limited or exhausted.

**Solution:** Multiple keys with automatic failover and intelligent retry logic.

```python
router = ApiKeyRouter()

# Register multiple keys for redundancy
await router.register_provider("openai", OpenAIAdapter())
for i in range(5):
    await router.register_key(f"sk-key-{i}", "openai")

# Route with reliability focus
response = await router.route(
    RequestIntent(
        model="gpt-4",
        messages=[Message(role="user", content="Help me with my order")],
        parameters={"provider_id": "openai"}
    ),
    objective=RoutingObjective(primary=ObjectiveType.Reliability.value)
)

# Router automatically:
# - Monitors key health
# - Routes away from failing keys
# - Retries with different keys on failure
# - Predicts quota exhaustion before it happens
```

**Benefits:**
- 99.9%+ uptime even with individual key failures
- Automatic recovery monitoring
- Zero manual intervention needed

---

## 3. Multi-Tenant SaaS Applications

### Scenario: SaaS Platform with Per-Customer API Keys

**Problem:** A SaaS platform needs to route requests to customer-specific API keys while ensuring fair usage and cost tracking.

**Solution:** Per-tenant key management with quota awareness and cost tracking.

```python
router = ApiKeyRouter()

# Register customer keys
customers = {
    "customer-a": ["sk-cust-a-key1", "sk-cust-a-key2"],
    "customer-b": ["sk-cust-b-key1"],
    "customer-c": ["sk-cust-c-key1", "sk-cust-c-key2", "sk-cust-c-key3"]
}

for customer_id, keys in customers.items():
    for key in keys:
        await router.register_key(
            key,
            "openai",
            metadata={"customer_id": customer_id, "tier": "premium"}
        )

# Route request for specific customer
async def handle_customer_request(customer_id: str, user_message: str):
    # Get customer's keys
    customer_keys = [
        key for key in await router.key_manager.list_keys()
        if key.metadata.get("customer_id") == customer_id
    ]
    
    # Route with fairness objective (distributes load evenly)
    response = await router.route(
        RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content=user_message)],
            parameters={"provider_id": "openai"}
        ),
        objective=RoutingObjective(primary=ObjectiveType.Fairness.value)
    )
    
    # Track usage per customer
    return {
        "response": response.content,
        "customer_id": customer_id,
        "key_used": response.key_used,
        "cost": response.cost.amount,
        "tokens": response.metadata.tokens_used.total_tokens
    }
```

**Benefits:**
- Per-customer cost tracking
- Fair usage distribution
- Automatic key rotation per customer
- Isolated failures (one customer's key issues don't affect others)

---

## 4. Rate Limit Management

### Scenario: High-Volume Application Hitting Rate Limits

**Problem:** Application frequently hits OpenAI rate limits (429 errors), causing request failures and poor user experience.

**Solution:** Intelligent rate limit handling with automatic key rotation and cooldown management.

```python
router = ApiKeyRouter()

# Register multiple keys (each with different rate limits)
await router.register_provider("openai", OpenAIAdapter())
await router.register_key("sk-key-tier1", "openai", metadata={"tier": "tier1", "rpm": 500})
await router.register_key("sk-key-tier2", "openai", metadata={"tier": "tier2", "rpm": 3500})
await router.register_key("sk-key-tier3", "openai", metadata={"tier": "tier3", "rpm": 10000})

# Router automatically:
# - Detects 429 rate limit errors
# - Marks key as throttled
# - Routes to alternative keys
# - Monitors recovery and reactivates keys when ready
# - Predicts rate limit exhaustion before it happens

# Make requests - router handles rate limits automatically
for i in range(1000):
    response = await router.route(
        RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content=f"Request {i}")],
            parameters={"provider_id": "openai"}
        )
    )
    # No 429 errors - router automatically distributes load
```

**Benefits:**
- Zero 429 errors in application code
- Automatic load distribution
- Predictive rate limit avoidance
- Seamless user experience

---

## 5. Budget Enforcement

### Scenario: Enterprise with Strict Budget Controls

**Problem:** Enterprise needs to enforce monthly API spending limits and prevent budget overruns.

**Solution:** Budget-aware routing with hard enforcement and cost estimation.

```python
from apikeyrouter.domain.components.cost_controller import CostController
from apikeyrouter.domain.models.policy import BudgetPolicy

router = ApiKeyRouter()

# Register keys
await router.register_provider("openai", OpenAIAdapter())
await router.register_key("sk-enterprise-key", "openai")

# Configure budget policy
budget_policy = BudgetPolicy(
    scope="monthly",
    limit=10000.0,  # $10,000 monthly limit
    enforcement_mode="hard",  # Reject requests that would exceed budget
    current_spend=8500.0  # Current month's spending
)

# Router automatically:
# - Estimates cost before execution
# - Checks budget before routing
# - Rejects requests that would exceed budget
# - Provides detailed cost breakdowns

response = await router.route(
    RequestIntent(
        model="gpt-4",
        messages=[Message(role="user", content="Analyze this data")],
        parameters={"provider_id": "openai"}
    ),
    objective=RoutingObjective(primary=ObjectiveType.Cost.value)
)

# Check if request was allowed
if response.metadata.budget_status:
    print(f"Budget remaining: ${response.metadata.budget_status.remaining}")
```

**Benefits:**
- Prevents budget overruns
- Pre-execution cost estimation
- Detailed cost reporting
- Policy-driven enforcement

---

## 6. Development & Testing

### Scenario: Development Team with Multiple Environments

**Problem:** Development team needs to use different API keys for dev, staging, and production without code changes.

**Solution:** Environment-based key management with automatic selection.

```python
import os

router = ApiKeyRouter()

# Register keys per environment
env = os.getenv("ENVIRONMENT", "development")

if env == "production":
    await router.register_key("sk-prod-key1", "openai")
    await router.register_key("sk-prod-key2", "openai")
elif env == "staging":
    await router.register_key("sk-staging-key", "openai")
else:  # development
    await router.register_key("sk-dev-key", "openai")
    # Use cheaper model in dev
    await router.register_key("sk-dev-gpt35-key", "openai")

# Same code works in all environments
response = await router.route(
    RequestIntent(
        model="gpt-4" if env == "production" else "gpt-3.5-turbo",
        messages=[Message(role="user", content="Test message")],
        parameters={"provider_id": "openai"}
    )
)

# Router automatically:
# - Uses appropriate keys for environment
# - Tracks usage per environment
# - Provides cost visibility per environment
```

**Benefits:**
- Single codebase for all environments
- Environment-specific key isolation
- Cost tracking per environment
- Easy testing with cheaper models

---

## 7. Multi-Provider Strategy

### Scenario: Vendor Diversification for Risk Mitigation

**Problem:** Company wants to use multiple LLM providers (OpenAI, Anthropic, Google) to avoid vendor lock-in and ensure availability.

**Solution:** Multi-provider routing with provider-agnostic interface.

```python
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter
from apikeyrouter.infrastructure.adapters.anthropic_adapter import AnthropicAdapter
from apikeyrouter.infrastructure.adapters.gemini_adapter import GeminiAdapter

router = ApiKeyRouter()

# Register multiple providers
await router.register_provider("openai", OpenAIAdapter())
await router.register_provider("anthropic", AnthropicAdapter())
await router.register_provider("google", GeminiAdapter())

# Register keys for each provider
await router.register_key("sk-openai-key", "openai")
await router.register_key("sk-anthropic-key", "anthropic")
await router.register_key("sk-google-key", "google")

# Route request - router selects best provider
response = await router.route(
    RequestIntent(
        model="gpt-4",  # Preferred model
        messages=[Message(role="user", content="Explain AI safety")],
        parameters={"provider_id": "openai"}  # Preferred provider
    ),
    objective=RoutingObjective(primary=ObjectiveType.Reliability.value)
)

# Router automatically:
# - Falls back to alternative providers if primary fails
# - Compares costs across providers
# - Selects best provider based on objective
# - Normalizes responses across providers
```

**Benefits:**
- Vendor diversification
- Automatic failover between providers
- Cost comparison across providers
- Single unified interface

---

## 8. Fairness & Load Balancing

### Scenario: Even Distribution Across Multiple Keys

**Problem:** Application has 10 API keys and wants to distribute load evenly to maximize throughput and avoid exhausting any single key.

**Solution:** Fairness-based routing with intelligent load balancing.

```python
router = ApiKeyRouter()

# Register multiple keys
await router.register_provider("openai", OpenAIAdapter())
for i in range(10):
    await router.register_key(f"sk-key-{i}", "openai")

# Route with fairness objective
response = await router.route(
    RequestIntent(
        model="gpt-4",
        messages=[Message(role="user", content="Process this request")],
        parameters={"provider_id": "openai"}
    ),
    objective=RoutingObjective(primary=ObjectiveType.Fairness.value)
)

# Router automatically:
# - Tracks usage per key
# - Distributes requests evenly
# - Accounts for quota states
# - Balances load dynamically
```

**Benefits:**
- Even key utilization
- Maximum throughput
- Prevents key exhaustion
- Automatic load rebalancing

---

## 9. Enterprise Compliance

### Scenario: Enterprise with Audit and Compliance Requirements

**Problem:** Enterprise needs detailed audit logs, request tracing, and compliance reporting for all API usage.

**Solution:** Comprehensive observability and audit trail.

```python
from apikeyrouter.infrastructure.observability.logger import DefaultObservabilityManager
from apikeyrouter.infrastructure.state_store.mongo_store import MongoStateStore

# Use persistent state store for audit logs
state_store = MongoStateStore(
    connection_string="mongodb://localhost:27017",
    database="apikeyrouter_audit"
)

# Use observability manager with structured logging
observability = DefaultObservabilityManager(
    log_level="INFO",
    enable_audit_logging=True
)

router = ApiKeyRouter(
    state_store=state_store,
    observability_manager=observability
)

# All requests are automatically:
# - Logged with full context
# - Stored in audit database
# - Traced with correlation IDs
# - Recorded with cost and usage data

response = await router.route(
    RequestIntent(
        model="gpt-4",
        messages=[Message(role="user", content="Sensitive data analysis")],
        parameters={"provider_id": "openai"}
    )
)

# Audit trail includes:
# - Request ID and correlation ID
# - Key used
# - Cost and tokens
# - Routing decision explanation
# - Timestamp and user context
```

**Benefits:**
- Complete audit trail
- Compliance-ready logging
- Request tracing
- Cost attribution

---

## 10. Legacy System Integration

### Scenario: Existing Application with OpenAI SDK Integration

**Problem:** Existing application uses OpenAI SDK directly and wants to add intelligent routing without major refactoring.

**Solution:** Proxy service mode with OpenAI-compatible API.

```python
# Existing application code (no changes needed)
import openai

client = openai.OpenAI(
    api_key="dummy",  # Not used - proxy handles keys
    base_url="http://localhost:8000/v1"  # ApiKeyRouter proxy
)

# Make requests as usual
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}]
)

# Proxy automatically:
# - Routes to best available key
# - Handles rate limits
# - Optimizes costs
# - Provides failover
```

**Proxy Setup:**
```bash
# Start ApiKeyRouter proxy
cd packages/proxy
poetry run uvicorn apikeyrouter_proxy.main:app --reload

# Register keys via management API
curl -X POST http://localhost:8000/api/v1/keys \
  -H "Content-Type: application/json" \
  -d '{
    "key_material": "sk-your-key",
    "provider_id": "openai"
  }'
```

**Benefits:**
- Zero code changes in existing application
- Drop-in replacement for OpenAI SDK
- All intelligent routing benefits
- Easy migration path

---

## Additional Use Cases

### A/B Testing Different Models

```python
# Route 50% to GPT-4, 50% to GPT-3.5 for A/B testing
# Router can be configured with custom routing strategies
```

### Cost Attribution by Feature

```python
# Tag requests by feature for cost analysis
response = await router.route(
    RequestIntent(...),
    metadata={"feature": "chatbot", "user_segment": "premium"}
)
# Router tracks costs per feature/segment
```

### Quota-Based Feature Gating

```python
# Check quota before allowing feature
quota_state = await router.quota_awareness_engine.get_quota_state(key_id)
if quota_state.state == QuotaState.Exhausted:
    return "Feature unavailable - quota exhausted"
```

### Predictive Scaling

```python
# Predict when keys will exhaust
prediction = await router.quota_awareness_engine.predict_exhaustion(key_id)
if prediction.exhaustion_time < timedelta(hours=2):
    # Proactively add more keys or notify operations
    alert_operations("Key exhaustion predicted in 2 hours")
```

---

## Summary

ApiKeyRouter solves real-world problems across multiple domains:

- **Cost Management**: Automatic cost optimization and budget enforcement
- **Reliability**: High availability with automatic failover
- **Scalability**: Intelligent load balancing and quota management
- **Compliance**: Complete audit trails and observability
- **Flexibility**: Works as library or proxy, supports multiple providers
- **Developer Experience**: Simple API, zero boilerplate, automatic handling

Choose the use case that matches your needs, or combine multiple approaches for comprehensive API key management.

