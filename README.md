# API Key Router

A Python library for routing LLM API requests across multiple API keys with automatic failover, quota tracking, and cost-aware routing.

## What Problem This Solves

When using LLM APIs at scale, you face several problems:
- **Rate limits**: Single API keys hit rate limits, causing request failures
- **Quota exhaustion**: Keys run out of quota mid-operation
- **Cost management**: No visibility into which keys are being used or how much they cost
- **Manual failover**: You must manually detect failures and switch keys

This library automatically routes requests across multiple API keys, handles failures gracefully, tracks quota consumption, and can optimize for cost or reliability.

## Why This Exists

Existing solutions (LiteLLM, LLM-API-Key-Proxy) focus on proxy services and don't provide a library interface. This project provides both:
- **Library mode**: Use directly in Python applications
- **Proxy mode**: Standalone HTTP service (planned, not yet implemented)

The library is designed for applications that need programmatic control over routing decisions, quota management, and cost optimization.

## What This Project Does

**Core Library (Implemented):**
- Routes requests across multiple API keys for the same provider
- Automatically fails over to alternative keys on rate limits, quota exhaustion, or network errors
- Tracks quota consumption and key state (available, throttled, exhausted)
- Supports routing objectives: cost optimization, reliability, fairness (load balancing)
- Encrypts API keys at rest
- Provides structured logging and observability events
- Works in-memory by default (no external dependencies required)
- Optional MongoDB persistence for state storage

**Provider Support:**
- OpenAI (fully implemented)
- Anthropic (not yet implemented)
- Gemini (not yet implemented)
- Custom providers via adapter interface

**State Storage:**
- In-memory store (default, no dependencies)
- MongoDB store (optional, requires MongoDB connection)

## What This Project Does NOT Do (Yet)

**Proxy Service:**
- HTTP API endpoints are not implemented (middleware exists but no routes)
- OpenAI-compatible endpoints (`/v1/chat/completions`, etc.) are planned but not available
- Management API (`/api/v1/keys`, etc.) is planned but not available

**Features:**
- Budget enforcement (mentioned in docs but not verified in code)
- Quality-based routing (falls back to reliability)
- Redis state store (mentioned in architecture but not found in code)
- Predictive quota exhaustion (basic tracking exists, predictive algorithms not implemented)

**Production Readiness:**
- No distributed state synchronization
- No built-in metrics dashboard
- No automatic key rotation
- No webhook notifications for quota exhaustion

## Who Should Use This

- **Python applications** that make LLM API calls and need automatic failover
- **Teams managing multiple API keys** for the same provider
- **Applications hitting rate limits** and needing automatic key rotation
- **Cost-conscious users** who want visibility into which keys are used
- **Developers who prefer libraries** over proxy services for integration

## Who Should NOT Use This

- **Non-Python applications**: This is a Python library only
- **Users needing HTTP proxy immediately**: Proxy endpoints are not implemented yet
- **Users with single API key**: No benefit over direct API calls
- **Users needing Anthropic/Gemini support**: Only OpenAI is implemented
- **Production deployments requiring distributed state**: Currently in-memory or single MongoDB instance only

## Quick Start (5 minutes)

### Prerequisites

- Python 3.11 or higher
- Poetry 1.7.1 or higher ([installation guide](https://python-poetry.org/docs/#installation))

### Installation

```bash
# Clone repository
git clone <repository-url>
cd ApiKeyRouter

# Install dependencies
poetry install
```

### Basic Usage

```python
import asyncio
from apikeyrouter import ApiKeyRouter
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message

async def main():
    # Initialize router
    router = ApiKeyRouter()
    
    # Register OpenAI provider
    await router.register_provider("openai", OpenAIAdapter())
    
    # Register multiple API keys
    await router.register_key("sk-your-openai-key-1", "openai")
    await router.register_key("sk-your-openai-key-2", "openai")
    
    # Make a request
    intent = RequestIntent(
        model="gpt-4",
        messages=[Message(role="user", content="Hello!")],
        parameters={"provider_id": "openai"}
    )
    
    response = await router.route(intent)
    print(response.content)  # LLM response
    print(f"Key used: {response.key_used}")
    print(f"Tokens: {response.metadata.tokens_used.total_tokens}")

asyncio.run(main())
```

### With Routing Objectives

```python
# Optimize for cost
response = await router.route(intent, objective="cost")

# Optimize for reliability
response = await router.route(intent, objective="reliability")

# Load balancing (default)
response = await router.route(intent, objective="fairness")
```

### With MongoDB Persistence (Optional)

```python
from apikeyrouter.infrastructure.state_store.mongo_store import MongoStateStore

# Initialize MongoDB store
mongo_store = MongoStateStore(
    connection_string="mongodb://localhost:27017",
    database_name="apikeyrouter"
)
await mongo_store.initialize()

# Use with router
router = ApiKeyRouter(state_store=mongo_store)
```

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run specific test suite
poetry run pytest packages/core/tests/unit
poetry run pytest packages/core/tests/integration

# Run with coverage
poetry run pytest --cov=packages/core/apikeyrouter --cov-report=html
```

## How It Works (High Level)

### Request Flow

1. **Request**: You call `router.route(request_intent)` with a model, messages, and provider ID
2. **Routing Decision**: Library selects best key based on:
   - Key availability (not throttled or exhausted)
   - Quota remaining
   - Routing objective (cost, reliability, fairness)
   - Key health and failure history
3. **Execution**: Library calls provider API using selected key
4. **Failure Handling**: If request fails (rate limit, network error):
   - Library automatically tries next best key (up to 3 attempts)
   - Updates key state (throttled, exhausted)
   - Returns error only if all keys fail
5. **State Update**: After successful request:
   - Updates quota consumption
   - Records usage statistics
   - Updates key last-used timestamp

### Routing Logic

The routing engine scores each eligible key based on:
- **Cost objective**: Selects key with lowest estimated cost
- **Reliability objective**: Selects key with highest success rate and lowest failure count
- **Fairness objective**: Distributes load evenly across keys (round-robin with state awareness)

Keys are excluded if:
- State is `Throttled` (in cooldown period)
- State is `Exhausted` (quota depleted)
- State is `Disabled` or `Invalid`

### Failure Handling

The library implements automatic failover:
- **Rate limit (429)**: Key marked as `Throttled`, next key tried immediately
- **Quota exhausted**: Key marked as `Exhausted`, excluded from routing
- **Network error**: Retried with next key (up to 3 attempts)
- **Authentication error**: Key marked as `Invalid`, not retried

All failures are logged with structured events for observability.

## Project Status

**Version**: 0.1.0 (Early development)

**Maturity**: Core library is functional but proxy service is incomplete. Breaking changes are expected in future releases.

**Current State**:
- ✅ Core routing library works
- ✅ OpenAI adapter implemented
- ✅ In-memory and MongoDB state stores
- ✅ Comprehensive test suite
- ❌ Proxy HTTP API not implemented
- ❌ Additional providers (Anthropic, Gemini) not implemented
- ❌ Budget enforcement not verified
- ❌ Distributed state synchronization not implemented

**Breaking Changes**: The API is not stable. Expect changes to:
- `RequestIntent` model structure
- Routing objective API
- State store interfaces
- Provider adapter interface

## Roadmap

**Short-term (Next 3 months)**:
- Implement proxy HTTP API endpoints (`/v1/chat/completions`, etc.)
- Add Anthropic adapter
- Add management API for key registration via HTTP
- Improve documentation and examples

**Medium-term (Next 6 months)**:
- Add Gemini adapter
- Implement budget enforcement
- Add Redis state store option
- Performance optimizations

**Long-term**:
- Distributed state synchronization
- Metrics dashboard
- Automatic key rotation
- Webhook notifications

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Support

- **Documentation**: See [docs/](docs/) directory
- **API Reference**: See [API_REFERENCE.md](API_REFERENCE.md)
- **Issues**: Report bugs and feature requests via GitHub Issues
