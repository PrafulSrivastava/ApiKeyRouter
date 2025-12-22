# ApiKeyRouter Comprehensive Examples

This directory contains comprehensive examples demonstrating the full potential of the ApiKeyRouter library.

## Files

- **`comprehensive-usage-example.py`** - Complete example showcasing all major features
- **`README.md`** - This file, providing context and explanations

## Overview

The comprehensive example demonstrates:

### 1. **Multi-Provider Setup**
- Registering multiple LLM providers (OpenAI, Anthropic, etc.)
- Managing provider-specific adapters
- Provider abstraction and extensibility

### 2. **Advanced Key Management**
- Registering multiple keys per provider
- Rich metadata (tiers, quotas, regions, teams)
- Key lifecycle management (registration, rotation, revocation)
- State tracking (Available, Throttled, Exhausted, Disabled, Invalid)

### 3. **Quota Awareness**
- Time-window quotas (daily, hourly, monthly)
- Multi-state capacity tracking (Abundant, Constrained, Critical, Exhausted)
- Predictive exhaustion detection
- Automatic quota resets

### 4. **Cost Optimization**
- Pre-execution cost estimation
- Budget enforcement (prevent vs. alert)
- Cost-aware routing decisions
- Actual cost tracking and reconciliation

### 5. **Policy-Driven Routing**
- Declarative policies (routing, cost, key selection)
- Policy hierarchy and precedence
- Team/scope-based policy application
- Policy evaluation and impact prediction

### 6. **Multiple Routing Objectives**
- **Cost Optimization**: Minimize expenses while maintaining quality
- **Reliability**: Maximize success rate and uptime
- **Fairness**: Round-robin distribution across keys
- **Speed**: Minimize latency
- **Multi-Objective**: Balance multiple factors with weights

### 7. **Automatic Failover**
- Semantic error interpretation
- Automatic retry with different keys
- Circuit breaker pattern
- Graceful degradation
- Health monitoring and recovery

### 8. **Observability**
- Structured logging with correlation IDs
- Request tracing (full decision history)
- System state inspection
- Metrics collection (Prometheus-compatible)
- Budget and quota monitoring

### 9. **Concurrent Processing**
- Async/await support
- Batch request handling
- Concurrent request execution
- Thread-safe operations

### 10. **Proxy Mode**
- HTTP API with OpenAI-compatible endpoints
- Management API for configuration
- Stateless deployment
- Environment-based configuration

## Key Concepts

### Routing Objectives

Routing objectives determine how the system selects API keys:

```python
# Cost-optimized
objective = RoutingObjective(
    primary=ObjectiveType.Cost.value,
    secondary=ObjectiveType.Reliability.value,
    weights={"cost": 0.8, "reliability": 0.2}
)

# Reliability-first
objective = RoutingObjective(
    primary=ObjectiveType.Reliability.value,
    weights={"reliability": 0.9, "cost": 0.1}
)

# Fairness (round-robin)
objective = RoutingObjective(
    primary=ObjectiveType.Fairness.value
)
```

### Policies

Policies express declarative intent, not procedural logic:

```python
# Cost policy for development team
policy = Policy(
    name="development_cost_optimization",
    type=PolicyType.Cost,
    scope=PolicyScope.Team,
    scope_value="development",
    rules=[
        {
            "action": "prefer_lowest_cost",
            "max_cost_per_request": 0.10,
            "fallback_to_reliable": True
        }
    ]
)
```

### Quota Management

Quotas track capacity over time windows:

```python
router.configure_quota(
    key_id=key_id,
    time_window=TimeWindow.Monthly,
    total_capacity=1000000,  # 1M tokens
    reset_at=next_month_start
)
```

### State Management

Keys have explicit states with valid transitions:

- **Available**: Ready for use
- **Throttled**: Temporarily unavailable (rate limit, cooldown)
- **Exhausted**: Quota exhausted
- **Disabled**: Manually disabled or revoked
- **Invalid**: Authentication failure or invalid key

## Usage Patterns

### Pattern 1: Simple Automatic Routing

```python
router = ApiKeyRouter()
router.register_provider("openai", OpenAIAdapter())
router.register_key("sk-key1", "openai", {})
router.register_key("sk-key2", "openai", {})

response = await router.route(
    request_intent={"model": "gpt-4", "messages": [...]}
)
# Library automatically selects best key
```

### Pattern 2: Cost-Optimized with Budget

```python
# Configure budget
router.configure_policy(Policy(
    name="budget",
    type=PolicyType.Cost,
    rules=[{"budget_limit": 1000.00, "budget_window": "monthly"}]
))

# Route with cost objective
response = await router.route(
    request_intent={...},
    objective=RoutingObjective(primary=ObjectiveType.Cost.value)
)
```

### Pattern 3: Reliability-First for Production

```python
# Configure reliability policy
router.configure_policy(Policy(
    name="production_reliability",
    type=PolicyType.Routing,
    scope=PolicyScope.Team,
    scope_value="production",
    rules=[{"min_success_rate": 0.95, "prefer_premium_tier": True}]
))

# Route with reliability objective
response = await router.route(
    request_intent={...},
    objective=RoutingObjective(primary=ObjectiveType.Reliability.value)
)
```

### Pattern 4: Multi-Provider Fallback

```python
# Register multiple providers
router.register_provider("openai", OpenAIAdapter())
router.register_provider("anthropic", AnthropicAdapter())

# Route to primary provider, automatic fallback
try:
    response = await router.route(
        request_intent={"provider_id": "openai", ...}
    )
except ProviderError:
    # Automatic fallback or manual retry with different provider
    response = await router.route(
        request_intent={"provider_id": "anthropic", ...}
    )
```

## Running the Example

### Prerequisites

1. Install dependencies:
   ```bash
   poetry install
   ```

2. **Set up API keys** (required for actual API calls):
   
   The example loads API keys from environment variables. You have two options:
   
   **Option A: Environment Variables**
   ```bash
   export OPENAI_KEY_1=sk-your-actual-openai-key-1
   export OPENAI_KEY_2=sk-your-actual-openai-key-2
   export OPENAI_KEY_3=sk-your-actual-openai-key-3
   export OPENAI_KEY_4=sk-your-actual-openai-key-4
   export ANTHROPIC_KEY_1=sk-your-actual-anthropic-key-1
   export ANTHROPIC_KEY_2=sk-your-actual-anthropic-key-2
   ```
   
   **Option B: .env File**
   ```bash
   # Create .env file in project root
   OPENAI_KEY_1=sk-your-actual-openai-key-1
   OPENAI_KEY_2=sk-your-actual-openai-key-2
   OPENAI_KEY_3=sk-your-actual-openai-key-3
   OPENAI_KEY_4=sk-your-actual-openai-key-4
   ANTHROPIC_KEY_1=sk-your-actual-anthropic-key-1
   ANTHROPIC_KEY_2=sk-your-actual-anthropic-key-2
   ```
   
   Then load it in Python:
   ```python
   from dotenv import load_dotenv
   load_dotenv()
   ```
   
   **Note:** If you don't set these environment variables, the example will use placeholder keys that demonstrate the structure but won't work for actual API calls. The example will print a warning if placeholder keys are detected.

3. Set up environment variables for other services (optional):
   ```bash
   cp .env.example .env
   # Edit .env with your configuration (MongoDB, Redis, etc.)
   ```

4. Start local services (optional, for persistence):
   ```bash
   docker-compose up -d
   ```

### Run Library Mode Example

```bash
cd docs/examples
poetry run python comprehensive-usage-example.py
```

### Run Proxy Mode Example

1. Start the proxy service:
   ```bash
   cd packages/proxy
   poetry run uvicorn apikeyrouter_proxy.main:app --reload
   ```

2. In another terminal, run the proxy example:
   ```bash
   cd docs/examples
   poetry run python comprehensive-usage-example.py
   # Uncomment the proxy_mode_example() call
   ```

## Expected Output

The example will demonstrate:

1. **Setup**: Provider and key registration
2. **Configuration**: Quota and policy setup
3. **Routing**: Different objectives and their outcomes
4. **Failover**: Automatic key switching on failure
5. **Quota Tracking**: Capacity state transitions
6. **Cost Management**: Budget tracking and enforcement
7. **Key Lifecycle**: Rotation and revocation
8. **Observability**: State inspection and tracing
9. **Multi-Provider**: Routing across providers
10. **Concurrency**: Batch request handling
11. **Policies**: Team-based routing decisions

## Key Takeaways

1. **Automatic Key Management**: The library handles all key selection, failover, and state management automatically.

2. **Declarative Configuration**: Express what you want (policies, objectives) rather than how to do it.

3. **Observable Decisions**: Every routing decision is explainable and traceable.

4. **Graceful Degradation**: System continues operating even when keys fail or quotas are exhausted.

5. **Cost Control**: Proactive budget enforcement prevents overspending.

6. **Flexible Deployment**: Use as library (embedded) or proxy service (standalone).

## Next Steps

- Review the [Architecture Documentation](../architecture/) for design details
- Check [Component Specifications](../architecture/component-specifications.md) for API details
- Explore [REST API Spec](../architecture/rest-api-spec.md) for proxy endpoints
- Read [Epics and Stories](../epics-and-stories.md) for feature roadmap

## Support

For questions or issues:
- Review the [README](../../README.md)
- Check [Architecture Documentation](../architecture/)
- Open an issue on GitHub

