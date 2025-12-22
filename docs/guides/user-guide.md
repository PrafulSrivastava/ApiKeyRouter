# User Guide

Complete guide to using ApiKeyRouter library and proxy service.

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Library Usage](#library-usage)
4. [Proxy Service Usage](#proxy-service-usage)
5. [Configuration Reference](#configuration-reference)
6. [Common Use Cases and Patterns](#common-use-cases-and-patterns)
7. [Troubleshooting](#troubleshooting)

---

## Installation

### Prerequisites

- **Python 3.11+**: Required for all packages
- **Poetry 1.7.1+** (recommended) or **pip**: Package manager

### Installing the Core Library

#### Using Poetry (Recommended)

```bash
poetry add apikeyrouter-core
```

#### Using pip

```bash
pip install apikeyrouter-core
```

#### From Source

```bash
git clone https://github.com/your-org/ApiKeyRouter.git
cd ApiKeyRouter/packages/core
poetry install
```

### Installing the Proxy Service

#### Using Poetry

```bash
poetry add apikeyrouter-proxy
```

#### Using pip

```bash
pip install apikeyrouter-proxy
```

#### From Source

```bash
git clone https://github.com/your-org/ApiKeyRouter.git
cd ApiKeyRouter/packages/proxy
poetry install
```

### Installing Both (Monorepo)

If working with the full monorepo:

```bash
git clone https://github.com/your-org/ApiKeyRouter.git
cd ApiKeyRouter
poetry install
```

This installs both `apikeyrouter-core` and `apikeyrouter-proxy` packages.

### Verifying Installation

```python
# Verify core library
python -c "from apikeyrouter import ApiKeyRouter; print('Core library installed')"

# Verify proxy service
python -c "from apikeyrouter_proxy.main import app; print('Proxy service installed')"
```

---

## Quick Start

Get started with ApiKeyRouter in under 10 minutes.

### Step 1: Install the Library

```bash
pip install apikeyrouter-core
```

### Step 2: Set Up Encryption Key (Optional)

For production, set an encryption key:

```bash
export APIKEYROUTER_ENCRYPTION_KEY="your-32-byte-base64-encoded-key"
```

For development, the library will auto-generate one if not set.

### Step 3: Basic Setup

```python
import asyncio
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

async def main():
    # Initialize router
    router = ApiKeyRouter()
    
    # Register provider adapter
    openai_adapter = OpenAIAdapter()
    await router.register_provider("openai", openai_adapter)
    
    # Register API keys
    await router.register_key(
        key_material="sk-your-openai-key-1",
        provider_id="openai"
    )
    await router.register_key(
        key_material="sk-your-openai-key-2",
        provider_id="openai"
    )
    
    # Make a request
    intent = RequestIntent(
        model="gpt-4",
        messages=[Message(role="user", content="Hello, world!")],
        provider_id="openai"
    )
    
    response = await router.route(intent)
    print(f"Response: {response.content}")
    print(f"Key used: {response.metadata.key_used}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Step 4: Run Your First Request

Save the code above to `example.py` and run:

```bash
python example.py
```

**That's it!** You're now using ApiKeyRouter to intelligently route requests across multiple API keys.

---

## Library Usage

### Basic ApiKeyRouter Setup

The `ApiKeyRouter` class is the main entry point for the library.

```python
from apikeyrouter import ApiKeyRouter

# Basic initialization (uses in-memory state store)
router = ApiKeyRouter()

# With custom configuration
from apikeyrouter.infrastructure.config.settings import RouterSettings

config = RouterSettings(
    max_decisions=1000,
    max_transitions=500,
    log_level="INFO"
)
router = ApiKeyRouter(config=config)

# With custom state store (Redis, MongoDB, etc.)
from apikeyrouter.infrastructure.state_store.redis_store import RedisStateStore

redis_store = RedisStateStore(redis_url="redis://localhost:6379")
router = ApiKeyRouter(state_store=redis_store)

# Using async context manager
async with ApiKeyRouter() as router:
    # Use router
    pass
```

### Registering Keys and Providers

#### Registering Providers

Providers are registered with adapter implementations:

```python
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

# Register OpenAI provider
openai_adapter = OpenAIAdapter()
await router.register_provider("openai", openai_adapter)

# Register multiple providers
# await router.register_provider("anthropic", AnthropicAdapter())
# await router.register_provider("cohere", CohereAdapter())
```

#### Registering API Keys

Register API keys with optional metadata:

```python
# Basic registration
key = await router.register_key(
    key_material="sk-your-api-key",
    provider_id="openai"
)

# With metadata for advanced routing
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

# Register multiple keys
keys = []
for i in range(5):
    key = await router.register_key(
        key_material=f"sk-key-{i}",
        provider_id="openai",
        metadata={"index": i}
    )
    keys.append(key)
```

**Note**: API keys are automatically encrypted using Fernet (AES-256). Set the `APIKEYROUTER_ENCRYPTION_KEY` environment variable for production use.

### Making Requests with Routing

#### Basic Request

```python
from apikeyrouter.domain.models.request_intent import RequestIntent, Message

intent = RequestIntent(
    model="gpt-4",
    messages=[
        Message(role="user", content="Hello, how are you?")
    ],
    provider_id="openai"
)

response = await router.route(intent)
print(response.content)  # LLM response
print(f"Key used: {response.metadata.key_used}")
print(f"Cost: ${response.metadata.cost_actual}")
```

#### Request with Streaming (if supported by adapter)

```python
# Some adapters support streaming responses
async for chunk in router.route_stream(intent):
    print(chunk, end="", flush=True)
```

### Using Routing Objectives

Route requests based on different optimization goals:

#### Cost Optimization

```python
from apikeyrouter.domain.models.routing_decision import RoutingObjective

# Minimize cost
response = await router.route(
    intent,
    objective=RoutingObjective(primary="cost")
)
```

#### Reliability Optimization

```python
# Maximize success rate
response = await router.route(
    intent,
    objective=RoutingObjective(primary="reliability")
)
```

#### Fairness Optimization

```python
# Distribute load evenly across keys
response = await router.route(
    intent,
    objective=RoutingObjective(primary="fairness")
)
```

#### Multi-Objective Routing

```python
# Combine multiple objectives with weights
objective = RoutingObjective(
    primary="cost",
    secondary=["reliability", "fairness"],
    weights={"cost": 0.5, "reliability": 0.3, "fairness": 0.2},
    constraints={"min_reliability": 0.95}
)

response = await router.route(intent, objective=objective)
```

### Error Handling

The library provides comprehensive error handling:

```python
from apikeyrouter.domain.components.routing_engine import NoEligibleKeysError
from apikeyrouter.domain.components.cost_controller import BudgetExceededError
from apikeyrouter.domain.models.system_error import SystemError

try:
    response = await router.route(intent)
except NoEligibleKeysError as e:
    print(f"No eligible keys available: {e}")
    # Handle: all keys exhausted, rate limited, etc.
except BudgetExceededError as e:
    print(f"Budget exceeded: {e.details}")
    # Handle: request would exceed budget
except SystemError as e:
    print(f"System error: {e.category} - {e.message}")
    # Handle: network errors, timeouts, etc.
except Exception as e:
    print(f"Unexpected error: {e}")
    # Handle: unexpected errors
```

#### Automatic Retry Logic

The router automatically retries with different keys on failures:

```python
# Router automatically:
# 1. Tries first key
# 2. On failure (rate limit, network error, etc.), tries next eligible key
# 3. Continues until success or all keys exhausted

response = await router.route(intent)
# No manual retry logic needed!
```

---

## Proxy Service Usage

### Starting the Proxy Service

#### Using uvicorn (Development)

```bash
cd packages/proxy
poetry run uvicorn apikeyrouter_proxy.main:app --reload
```

#### Using Docker

```bash
docker-compose up
```

#### Production Deployment

```bash
# Using gunicorn with uvicorn workers
gunicorn apikeyrouter_proxy.main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000
```

The service will be available at `http://localhost:8000` with:
- **API endpoints**: `/v1/chat/completions`, `/v1/completions`, etc.
- **Management API**: `/api/v1/keys`, `/api/v1/providers`, etc.
- **API documentation**: `/docs` (Swagger UI), `/redoc` (ReDoc)

### Using OpenAI-Compatible Endpoints

The proxy service provides OpenAI-compatible endpoints:

#### Chat Completions

```python
import httpx

response = httpx.post(
    "http://localhost:8000/v1/chat/completions",
    json={
        "model": "gpt-4",
        "messages": [
            {"role": "user", "content": "Hello!"}
        ]
    }
)

data = response.json()
print(data["choices"][0]["message"]["content"])
print(data["routing_metadata"]["key_used"])
```

#### Using OpenAI Python SDK

```python
from openai import OpenAI

# Point OpenAI client to proxy
client = OpenAI(
    api_key="dummy-key",  # Not used, proxy handles routing
    base_url="http://localhost:8000/v1"
)

response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}]
)

print(response.choices[0].message.content)
```

### Managing Keys via API

#### Register a Key

```bash
curl -X POST http://localhost:8000/api/v1/keys \
  -H "X-API-Key: your-management-key" \
  -H "Content-Type: application/json" \
  -d '{
    "key_material": "sk-your-openai-key",
    "provider_id": "openai",
    "metadata": {"tier": "pay-as-you-go"}
  }'
```

#### List Keys

```bash
curl -X GET http://localhost:8000/api/v1/keys \
  -H "X-API-Key: your-management-key"
```

#### Update Key State

```bash
curl -X PATCH http://localhost:8000/api/v1/keys/{key_id} \
  -H "X-API-Key: your-management-key" \
  -H "Content-Type: application/json" \
  -d '{
    "state": "throttled",
    "reason": "Rate limit encountered"
  }'
```

#### Delete Key

```bash
curl -X DELETE http://localhost:8000/api/v1/keys/{key_id} \
  -H "X-API-Key: your-management-key"
```

### Configuration via Environment Variables

The proxy service can be configured using environment variables:

```bash
# Proxy settings
export PROXY_HOST="0.0.0.0"
export PROXY_PORT="8000"
export PROXY_RELOAD="false"

# Management API
export MANAGEMENT_API_KEY="your-secret-key"
export MANAGEMENT_API_ENABLED="true"

# State store
export MONGODB_URL="mongodb://localhost:27017"
export MONGODB_DATABASE="apikeyrouter"
export REDIS_URL="redis://localhost:6379"

# Observability
export LOG_LEVEL="INFO"
export METRICS_ENABLED="true"
```

See [Configuration Reference](#configuration-reference) for complete list.

### Health Checks and Metrics

#### Health Check Endpoint

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "keys_registered": 5,
  "providers_registered": 2
}
```

#### Metrics Endpoint

```bash
curl http://localhost:8000/metrics
```

Returns Prometheus-formatted metrics.

---

## Configuration Reference

### Environment Variables

All configuration can be set via environment variables with the `APIKEYROUTER_` prefix.

#### Core Library Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `APIKEYROUTER_MAX_DECISIONS` | `1000` | Maximum routing decisions to store |
| `APIKEYROUTER_MAX_TRANSITIONS` | `1000` | Maximum state transitions to store |
| `APIKEYROUTER_DEFAULT_COOLDOWN_SECONDS` | `60` | Default cooldown for throttled keys (seconds) |
| `APIKEYROUTER_QUOTA_DEFAULT_COOLDOWN_SECONDS` | `60` | Default cooldown when retry-after missing (seconds) |
| `APIKEYROUTER_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `APIKEYROUTER_ENCRYPTION_KEY` | `None` | Encryption key for API key material (32-byte base64) |

#### State Store Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `None` | Redis connection URL (e.g., `redis://localhost:6379`) |
| `MONGODB_URL` | `None` | MongoDB connection URL (e.g., `mongodb://localhost:27017`) |
| `MONGODB_DATABASE` | `apikeyrouter` | MongoDB database name |

#### Proxy Service Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PROXY_HOST` | `0.0.0.0` | Host to bind proxy service |
| `PROXY_PORT` | `8000` | Port to bind proxy service |
| `PROXY_RELOAD` | `false` | Enable auto-reload (development) |
| `MANAGEMENT_API_KEY` | `None` | API key for management endpoints |
| `MANAGEMENT_API_ENABLED` | `true` | Enable management API |
| `ENABLE_HSTS` | `false` | Enable HSTS security headers |

### Programmatic Configuration

#### RouterSettings

```python
from apikeyrouter.infrastructure.config.settings import RouterSettings

# Create settings from dictionary
config = RouterSettings(
    max_decisions=1000,
    max_transitions=500,
    default_cooldown_seconds=60,
    quota_default_cooldown_seconds=60,
    log_level="INFO",
    encryption_key="your-key"  # Optional, can use env var
)

router = ApiKeyRouter(config=config)
```

#### Configuration Priority

1. **Programmatic** (passed to constructor) - Highest priority
2. **Environment variables** (with `APIKEYROUTER_` prefix)
3. **Default values** - Lowest priority

### Default Values

All configuration options have sensible defaults:

- **State Store**: In-memory (no persistence required)
- **Logging**: INFO level
- **Cooldown**: 60 seconds
- **Storage Limits**: 1000 decisions, 1000 transitions

### Configuration Examples

#### Development Configuration

```bash
# .env file
APIKEYROUTER_LOG_LEVEL=DEBUG
APIKEYROUTER_MAX_DECISIONS=100
PROXY_RELOAD=true
```

#### Production Configuration

```bash
# .env file
APIKEYROUTER_ENCRYPTION_KEY="your-32-byte-base64-key"
APIKEYROUTER_LOG_LEVEL=INFO
MONGODB_URL="mongodb://prod-db:27017"
MONGODB_DATABASE="apikeyrouter"
REDIS_URL="redis://prod-redis:6379"
MANAGEMENT_API_KEY="secure-random-key"
ENABLE_HSTS=true
```

---

## Common Use Cases and Patterns

### Use Case 1: Multi-Key Routing for Reliability

Route requests across multiple keys to ensure high availability:

```python
# Register multiple keys
for i in range(10):
    await router.register_key(
        key_material=f"sk-key-{i}",
        provider_id="openai"
    )

# Route with reliability objective
response = await router.route(
    intent,
    objective=RoutingObjective(primary="reliability")
)

# Router automatically:
# - Selects keys with highest success rate
# - Avoids keys that are rate limited or exhausted
# - Retries with different keys on failure
```

### Use Case 2: Cost-Optimized Routing

Minimize costs by routing to the cheapest available keys:

```python
# Register keys with different cost tiers
await router.register_key(
    key_material="sk-cheap-key",
    provider_id="openai",
    metadata={"cost_per_1k": "0.01"}
)
await router.register_key(
    key_material="sk-expensive-key",
    provider_id="openai",
    metadata={"cost_per_1k": "0.05"}
)

# Route with cost optimization
response = await router.route(
    intent,
    objective=RoutingObjective(primary="cost")
)

# Router selects cheapest key that meets reliability threshold
```

### Use Case 3: Budget Enforcement

Enforce spending limits to prevent cost overruns:

```python
from apikeyrouter.domain.models.budget import BudgetScope, EnforcementMode, TimeWindow
from decimal import Decimal

# Create daily budget with hard enforcement
budget = await router.cost_controller.create_budget(
    scope=BudgetScope.Global,
    limit=Decimal("100.00"),  # $100 daily limit
    period=TimeWindow.Daily,
    enforcement_mode=EnforcementMode.Hard  # Reject requests that exceed budget
)

# Update spending (typically done automatically after requests)
await router.cost_controller.update_spending(budget.id, Decimal("25.50"))

# Route requests - keys that would exceed budget are filtered out
try:
    response = await router.route(intent, objective="cost")
except BudgetExceededError as e:
    print(f"Budget exceeded: {e.details}")
```

### Use Case 4: Custom Provider Adapter

Create custom adapters for unsupported providers:

```python
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.request_intent import RequestIntent
from apikeyrouter.domain.models.system_response import SystemResponse
from apikeyrouter.domain.models.cost_estimate import CostEstimate

class MyCustomAdapter(ProviderAdapter):
    """Custom adapter for MyProvider."""
    
    async def execute_request(
        self, intent: RequestIntent, key: str
    ) -> SystemResponse:
        # Your implementation
        # Make HTTP request to provider API
        # Return SystemResponse
        pass
    
    async def estimate_cost(
        self, request_intent: RequestIntent
    ) -> CostEstimate:
        # Your cost estimation logic
        pass
    
    async def check_health(self, key: str) -> bool:
        # Your health check logic
        return True
    
    def get_provider_id(self) -> str:
        return "my-provider"

# Register custom adapter
await router.register_provider("my-provider", MyCustomAdapter())
```

### Pattern 1: Key Rotation Strategy

Implement key rotation to distribute load:

```python
# Register keys with rotation metadata
keys = []
for i in range(5):
    key = await router.register_key(
        key_material=f"sk-key-{i}",
        provider_id="openai",
        metadata={"rotation_group": "primary", "index": i}
    )
    keys.append(key)

# Use fairness objective for even distribution
response = await router.route(
    intent,
    objective=RoutingObjective(primary="fairness")
)

# Router distributes requests evenly across keys
```

### Pattern 2: Monitoring and Observability

Monitor routing decisions and system health:

```python
# Access routing decisions
from apikeyrouter.domain.interfaces.state_store import StateQuery
from apikeyrouter.domain.models.routing_decision import RoutingDecision

query = StateQuery(entity_type="RoutingDecision")
decisions = await router.state_store.query_state(query)

for decision in decisions[-10:]:  # Last 10 decisions
    print(f"Key: {decision.selected_key_id}")
    print(f"Objective: {decision.objective.primary}")
    print(f"Explanation: {decision.explanation}")
    print(f"Confidence: {decision.confidence}")

# Get system state summary
state = await router.get_state_summary()
print(f"Total keys: {state.keys.total}")
print(f"Available keys: {state.keys.available}")
print(f"Exhausted keys: {state.quotas.exhausted_keys}")
print(f"Total cost: ${state.costs.total_spent}")
```

### Pattern 3: Quota-Aware Routing

Track and manage API key quotas:

```python
from apikeyrouter.domain.models.quota_state import TimeWindow

# Update quota after request
response = await router.route(intent)
await router.quota_awareness_engine.update_capacity(
    key_id=response.metadata.key_used,
    used_tokens=response.metadata.token_usage.total,
    time_window=TimeWindow.Daily
)

# Check quota state
quota_state = await router.quota_awareness_engine.get_quota_state(
    key_id=response.metadata.key_used,
    time_window=TimeWindow.Daily
)

if quota_state.capacity_state == "Exhausted":
    print("Key exhausted, will be filtered from routing")
elif quota_state.capacity_state == "Critical":
    print("Key near exhaustion, router will prefer other keys")
```

### Pattern 4: Policy-Driven Routing

Use policies to enforce business rules:

```python
from apikeyrouter.domain.models.policy import Policy, PolicyScope, PolicyType

# Create routing policy
policy = Policy(
    id="team-engineering",
    name="Engineering Team Policy",
    type=PolicyType.Routing,
    scope=PolicyScope.PerTeam,
    scope_id="engineering",
    rules={
        "allowed_providers": ["openai"],
        "preferred_models": ["gpt-4", "gpt-3.5-turbo"],
        "max_cost_per_request": 0.10
    }
)

# Apply policy during routing
response = await router.route(intent, policy=policy)
```

---

## Troubleshooting

### Common Issues

#### Issue: "No eligible keys available"

**Cause**: All keys are exhausted, rate limited, or in an unavailable state.

**Solution**:
```python
# Check key states
state = await router.get_state_summary()
print(f"Available keys: {state.keys.available}")
print(f"Exhausted keys: {state.quotas.exhausted_keys}")

# Register additional keys
await router.register_key("sk-new-key", "openai")

# Or wait for keys to recover (cooldown period)
```

#### Issue: "Encryption key not set"

**Cause**: Encryption key not configured for production.

**Solution**:
```bash
# Set environment variable
export APIKEYROUTER_ENCRYPTION_KEY="your-32-byte-base64-key"

# Or generate one
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

#### Issue: "Budget exceeded"

**Cause**: Request would exceed configured budget limit.

**Solution**:
```python
# Check current spending
budget = await router.cost_controller.get_budget(budget_id)
print(f"Spent: ${budget.current_spending}, Limit: ${budget.limit}")

# Increase budget or wait for period reset
# Or use soft enforcement mode
budget.enforcement_mode = EnforcementMode.Soft
```

#### Issue: "Provider adapter not found"

**Cause**: Provider not registered before routing.

**Solution**:
```python
# Register provider before routing
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter
await router.register_provider("openai", OpenAIAdapter())
```

#### Issue: "State store connection failed"

**Cause**: Redis/MongoDB connection issues (if using persistent state store).

**Solution**:
```python
# Check connection
# For Redis
redis_store = RedisStateStore(redis_url="redis://localhost:6379")
await redis_store.health_check()

# For MongoDB
mongo_store = MongoStateStore(mongodb_url="mongodb://localhost:27017")
await mongo_store.health_check()

# Or use in-memory store (default)
router = ApiKeyRouter()  # Uses InMemoryStateStore by default
```

### Debug Mode

Enable debug logging for detailed information:

```python
from apikeyrouter.infrastructure.config.settings import RouterSettings

config = RouterSettings(log_level="DEBUG")
router = ApiKeyRouter(config=config)

# Or via environment variable
# export APIKEYROUTER_LOG_LEVEL=DEBUG
```

### Getting Help

- **Documentation**: See [docs/](../) for detailed documentation
- **API Reference**: See [packages/core/API_REFERENCE.md](../../packages/core/API_REFERENCE.md)
- **Examples**: See [docs/examples/](../examples/) for code examples
- **Issues**: Open an issue on GitHub for bug reports or feature requests

---

## Next Steps

- Read the [Architecture Documentation](../architecture/) for design details
- Check [Component Specifications](../architecture/component-specifications.md) for implementation details
- Review [API Documentation](../api/openapi.yaml) for proxy endpoints
- See [Quick Start Guide](./quick-start.md) for a faster introduction
- Explore [Examples](../examples/) for more code samples

