# ApiKeyRouter

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/poetry-1.5+-blue.svg)](https://python-poetry.org/)

**Intelligent API Key Routing for LLM Applications**

ApiKeyRouter is a production-ready Python library that provides intelligent routing, quota management, cost optimization, and automatic failover for API keys across multiple LLM providers. It helps you manage multiple API keys efficiently, optimize costs, and ensure high availability for your LLM applications.

## ✨ Features

- **🎯 Intelligent Routing**: Route requests based on cost, reliability, fairness, or custom objectives
- **💰 Cost Optimization**: Pre-execution cost estimation, budget enforcement, and cost-aware routing
- **📊 Quota Management**: Track usage, predict exhaustion, and manage capacity across time windows
- **🔄 Automatic Failover**: Smart retry logic with different keys on failures
- **🔐 Secure Key Storage**: Encrypted key material with Fernet (AES-256)
- **📈 Observability**: Structured logging, request tracing, and comprehensive metrics
- **🎛️ Policy Engine**: Declarative policies for routing, cost control, and key selection
- **🔌 Provider Agnostic**: Works with any LLM provider through adapter pattern
- **⚡ High Performance**: Async/await throughout, optimized for production workloads

## 🚀 Quick Start

### Installation

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

### Basic Usage

```python
import asyncio
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

async def main():
    # Initialize router
    router = ApiKeyRouter()
    
    # Register a provider adapter
    openai_adapter = OpenAIAdapter()
    await router.register_provider("openai", openai_adapter)
    
    # Register API keys
    key1 = await router.register_key(
        key_material="sk-your-openai-key-1",
        provider_id="openai",
        metadata={"account_tier": "pro", "region": "us-east"}
    )
    
    key2 = await router.register_key(
        key_material="sk-your-openai-key-2",
        provider_id="openai",
        metadata={"account_tier": "basic"}
    )
    
    # Route a request
    intent = RequestIntent(
        model="gpt-4",
        messages=[Message(role="user", content="Hello, world!")],
        provider_id="openai"
    )
    
    # Route with cost optimization
    response = await router.route(intent, objective="cost")
    print(f"Response: {response.content}")
    print(f"Key used: {response.key_used}")
    print(f"Cost: ${response.cost}")

if __name__ == "__main__":
    asyncio.run(main())
```

## 📖 Documentation

### API Reference

**👉 [API_REFERENCE.md](./API_REFERENCE.md)** - **Start here!** Clean, simple API documentation that abstracts all complexity. Shows only what you need to use the library.

### Core Concepts

#### 1. **ApiKeyRouter** - Main Entry Point

The `ApiKeyRouter` class orchestrates all components and provides a simple API:

```python
from apikeyrouter import ApiKeyRouter

# Basic initialization
router = ApiKeyRouter()

# With custom state store (Redis, MongoDB, etc.)
from apikeyrouter.infrastructure.state_store.redis_store import RedisStateStore
redis_store = RedisStateStore(redis_url="redis://localhost:6379")
router = ApiKeyRouter(state_store=redis_store)

# With custom observability
from apikeyrouter.infrastructure.observability.logger import DefaultObservabilityManager
obs_manager = DefaultObservabilityManager()
router = ApiKeyRouter(observability_manager=obs_manager)
```

#### 2. **Provider Registration**

Register provider adapters to enable routing to different LLM providers:

```python
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

# Register OpenAI
openai_adapter = OpenAIAdapter()
await router.register_provider("openai", openai_adapter)

# You can register multiple providers
# await router.register_provider("anthropic", anthropic_adapter)
# await router.register_provider("cohere", cohere_adapter)
```

#### 3. **Key Registration**

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
```

**Note**: API keys are automatically encrypted using Fernet (AES-256). Set the `APIKEYROUTER_ENCRYPTION_KEY` environment variable, or the library will generate one automatically.

#### 4. **Routing Objectives**

Route requests based on different optimization goals:

```python
from apikeyrouter.domain.models.routing_decision import RoutingObjective

# Cost optimization - minimize expenses
response = await router.route(intent, objective="cost")

# Reliability - maximize success rate
response = await router.route(intent, objective="reliability")

# Fairness - distribute load evenly
response = await router.route(intent, objective="fairness")

# Multi-objective with weights
objective = RoutingObjective(
    primary="cost",
    secondary=["reliability", "fairness"],
    weights={"cost": 0.5, "reliability": 0.3, "fairness": 0.2}
)
response = await router.route(intent, objective=objective)
```

#### 5. **Cost-Aware Routing with Budgets**

Set budgets and enforce cost limits:

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

# Update spending (typically done automatically)
await cost_controller.update_spending(budget.id, Decimal("25.50"))

# Route requests - keys that would exceed budget are filtered out
response = await router.route(intent, objective="cost")
```

#### 6. **Quota Awareness**

Track and manage API key quotas:

```python
from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.domain.models.quota_state import TimeWindow

# Get quota engine
quota_engine = router.quota_awareness_engine

# Update capacity for a key
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

### Advanced Features

#### Policy-Driven Routing

Define declarative policies for routing decisions:

```python
from apikeyrouter.domain.models.policy import Policy, PolicyScope, PolicyType

# Create a routing policy
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

#### Observability

Access structured logs and metrics:

```python
# The router automatically logs:
# - Request start/completion
# - Routing decisions
# - Key selection reasoning
# - Cost estimates
# - Errors and retries

# Access routing decisions
from apikeyrouter.domain.interfaces.state_store import StateQuery
from apikeyrouter.domain.models.routing_decision import RoutingDecision

query = StateQuery(entity_type="RoutingDecision")
decisions = await router.state_store.query_state(query)

for decision in decisions:
    print(f"Key: {decision.selected_key_id}")
    print(f"Objective: {decision.objective.primary}")
    print(f"Explanation: {decision.explanation}")
    print(f"Confidence: {decision.confidence}")
```

#### Key Lifecycle Management

Manage keys throughout their lifecycle:

```python
# Update key state
await router.key_manager.update_key_state(
    key_id=key.id,
    new_state=KeyState.Throttled,
    reason="Rate limit encountered"
)

# Revoke a key
await router.key_manager.revoke_key(key.id, reason="Security incident")

# Rotate a key (preserves key ID and metadata)
new_key = await router.key_manager.rotate_key(
    key_id=key.id,
    new_key_material="sk-new-key-material"
)

# Check key eligibility
eligible_keys = await router.key_manager.get_eligible_keys(
    provider_id="openai",
    policy=None
)
```

## 🔧 Configuration

### Environment Variables

```bash
# Encryption key for API key material (required)
export APIKEYROUTER_ENCRYPTION_KEY="your-32-byte-base64-encoded-key"

# Or let the library generate one (not recommended for production)
# The library will generate a key if not set, but it won't persist

# State store configuration (if using Redis)
export REDIS_URL="redis://localhost:6379"

# State store configuration (if using MongoDB)
export MONGODB_URL="mongodb://localhost:27017"
export MONGODB_DATABASE="apikeyrouter"
```

### Programmatic Configuration

```python
from apikeyrouter.infrastructure.config.settings import RouterSettings

config = RouterSettings(
    max_decisions=1000,  # Max routing decisions to store
    max_transitions=500,  # Max state transitions to store
    default_objective="fairness",  # Default routing objective
)

router = ApiKeyRouter(config=config)
```

## 📚 Examples

### Example 1: Multi-Provider Setup

```python
from apikeyrouter import ApiKeyRouter
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

router = ApiKeyRouter()

# Register multiple providers
await router.register_provider("openai", OpenAIAdapter())
# await router.register_provider("anthropic", AnthropicAdapter())

# Register keys for each provider
await router.register_key("sk-openai-key-1", "openai")
await router.register_key("sk-openai-key-2", "openai")
# await router.register_key("sk-anthropic-key-1", "anthropic")

# Route to specific provider
intent = RequestIntent(
    model="gpt-4",
    messages=[Message(role="user", content="Hello!")],
    provider_id="openai"
)
response = await router.route(intent)
```

### Example 2: Cost Optimization with Budget

```python
from decimal import Decimal
from apikeyrouter.domain.models.budget import BudgetScope, EnforcementMode, TimeWindow

# Create budget
budget = await router.cost_controller.create_budget(
    scope=BudgetScope.Global,
    limit=Decimal("50.00"),
    period=TimeWindow.Daily,
    enforcement_mode=EnforcementMode.Hard
)

# Route with cost optimization
response = await router.route(intent, objective="cost")
# Router automatically filters keys that would exceed budget
```

### Example 3: Quota-Aware Routing

```python
from apikeyrouter.domain.models.quota_state import TimeWindow

# Update quota after request
response = await router.route(intent)
await router.quota_awareness_engine.update_capacity(
    key_id=response.key_used,
    used_tokens=response.metadata.token_usage.total,
    time_window=TimeWindow.Daily
)

# Check quota state
quota_state = await router.quota_awareness_engine.get_quota_state(
    key_id=response.key_used,
    time_window=TimeWindow.Daily
)

if quota_state.capacity_state == "Exhausted":
    print("Key exhausted, will be filtered from routing")
```

### Example 4: Custom Provider Adapter

```python
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.request_intent import RequestIntent
from apikeyrouter.domain.models.system_response import SystemResponse
from apikeyrouter.domain.models.cost_estimate import CostEstimate

class MyCustomAdapter(ProviderAdapter):
    async def execute_request(
        self, intent: RequestIntent, key: str
    ) -> SystemResponse:
        # Your implementation
        pass
    
    async def estimate_cost(
        self, request_intent: RequestIntent
    ) -> CostEstimate:
        # Your cost estimation
        pass
    
    # Implement other required methods...

# Register custom adapter
await router.register_provider("my-provider", MyCustomAdapter())
```

## 🏗️ Architecture

ApiKeyRouter follows a clean architecture with clear separation of concerns:

- **Domain Layer**: Core business logic, models, and interfaces
- **Infrastructure Layer**: Implementations (adapters, state stores, observability)
- **Application Layer**: ApiKeyRouter orchestrator

### Key Components

- **ApiKeyRouter**: Main orchestrator
- **KeyManager**: Key lifecycle and eligibility management
- **RoutingEngine**: Intelligent routing decisions
- **CostController**: Cost estimation and budget enforcement
- **QuotaAwarenessEngine**: Capacity tracking and exhaustion prediction
- **PolicyEngine**: Policy evaluation and enforcement
- **StateStore**: Persistence abstraction (InMemory, Redis, MongoDB)
- **ObservabilityManager**: Logging and event emission

## 🧪 Testing

Run the test suite:

```bash
# Install development dependencies
poetry install --with dev

# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=apikeyrouter --cov-report=html

# Run specific test file
poetry run pytest tests/unit/test_router.py -v
```

## 🤝 Contributing

Contributions are welcome! Please see our contributing guidelines for details.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](../../LICENSE) file for details.

## 🆘 Support

- **Documentation**: See [docs/](../../docs/) for detailed documentation
- **Examples**: See [test_manual_example.py](./test_manual_example.py) for comprehensive examples
- **Issues**: Open an issue on GitHub for bug reports or feature requests

## 🗺️ Roadmap

Current features (up to Story 2.3.7):
- ✅ Key registration and lifecycle management
- ✅ Multi-objective routing (cost, reliability, fairness)
- ✅ Cost-aware routing with budget filtering
- ✅ Quota awareness and capacity tracking
- ✅ State management and persistence
- ✅ Observability and logging

Upcoming features:
- 🔄 Redis and MongoDB state store implementations
- 🔄 Additional provider adapters (Anthropic, Cohere, etc.)
- 🔄 REST API server
- 🔄 Advanced policy engine features
- 🔄 Cost reconciliation and learning

## 🙏 Acknowledgments

Built with ❤️ for the LLM developer community.
