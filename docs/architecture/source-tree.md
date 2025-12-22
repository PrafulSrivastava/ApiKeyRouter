# Source Tree

The project uses a **monorepo structure** with separate packages for the library and proxy service. This enables shared code while maintaining clear separation of concerns.

## Project Structure

```
apikeyrouter/
├── .github/                          # GitHub workflows and templates
│   ├── workflows/
│   │   ├── ci.yml                   # Continuous integration
│   │   ├── release.yml               # Release automation
│   │   └── benchmark.yml            # Performance benchmarking
│   └── ISSUE_TEMPLATE/
│
├── docs/                             # Documentation
│   ├── architecture.md               # This document
│   ├── brainstorming-session-results.md
│   ├── competitor-analysis.md
│   ├── api/                          # API documentation
│   └── guides/                       # User guides
│
├── packages/
│   ├── core/                         # Core library package
│   │   ├── apikeyrouter/
│   │   │   ├── __init__.py
│   │   │   ├── router.py             # ApiKeyRouter (main orchestrator)
│   │   │   │
│   │   │   ├── domain/               # Domain layer (business logic)
│   │   │   │   ├── __init__.py
│   │   │   │   ├── models/           # Domain models (Pydantic)
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── api_key.py
│   │   │   │   │   ├── quota_state.py
│   │   │   │   │   ├── provider.py
│   │   │   │   │   ├── routing_decision.py
│   │   │   │   │   ├── cost_model.py
│   │   │   │   │   ├── policy.py
│   │   │   │   │   └── request_context.py
│   │   │   │   │
│   │   │   │   ├── components/       # Core components
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── key_manager.py
│   │   │   │   │   ├── quota_awareness_engine.py
│   │   │   │   │   ├── routing_engine.py
│   │   │   │   │   ├── failure_handler.py
│   │   │   │   │   ├── cost_controller.py
│   │   │   │   │   └── policy_engine.py
│   │   │   │   │
│   │   │   │   └── interfaces/       # Abstract interfaces
│   │   │   │       ├── __init__.py
│   │   │   │       ├── provider_adapter.py
│   │   │   │       ├── state_store.py
│   │   │   │       └── observability_manager.py
│   │   │   │
│   │   │   ├── infrastructure/       # Infrastructure layer
│   │   │   │   ├── __init__.py
│   │   │   │   ├── state_store/
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── memory_store.py      # In-memory (default)
│   │   │   │   │   ├── redis_store.py       # Redis backend (optional)
│   │   │   │   │   └── mongo_store.py       # MongoDB backend (optional)
│   │   │   │   │
│   │   │   │   ├── observability/
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── logger.py            # Structlog integration
│   │   │   │   │   ├── metrics.py           # Metrics collection
│   │   │   │   │   └── tracer.py            # Request tracing
│   │   │   │   │
│   │   │   │   ├── config/
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── settings.py          # Pydantic settings
│   │   │   │   │   └── loader.py            # Configuration loader
│   │   │   │   │
│   │   │   │   └── adapters/                # Provider adapters
│   │   │   │       ├── __init__.py
│   │   │   │       ├── base.py              # Base adapter interface
│   │   │   │       ├── openai_adapter.py
│   │   │   │       ├── anthropic_adapter.py
│   │   │   │       ├── gemini_adapter.py
│   │   │   │       └── generic_http_adapter.py
│   │   │   │
│   │   │   └── utils/                       # Utilities
│   │   │       ├── __init__.py
│   │   │       ├── encryption.py            # Key encryption
│   │   │       ├── validation.py            # Input validation
│   │   │       └── exceptions.py           # Custom exceptions
│   │   │
│   │   ├── tests/                           # Core library tests
│   │   │   ├── __init__.py
│   │   │   ├── unit/
│   │   │   │   ├── test_key_manager.py
│   │   │   │   ├── test_quota_awareness.py
│   │   │   │   ├── test_routing_engine.py
│   │   │   │   └── ...
│   │   │   ├── integration/
│   │   │   │   ├── test_provider_adapters.py
│   │   │   │   └── test_state_store.py
│   │   │   ├── benchmarks/                  # Performance benchmarks
│   │   │   │   ├── benchmark_routing.py
│   │   │   │   ├── benchmark_quota.py
│   │   │   │   └── benchmark_cost.py
│   │   │   └── fixtures/
│   │   │       └── test_data.py
│   │   │
│   │   ├── pyproject.toml                   # Poetry configuration
│   │   ├── README.md
│   │   └── CHANGELOG.md
│   │
│   └── proxy/                               # Proxy service package
│       ├── apikeyrouter_proxy/
│       │   ├── __init__.py
│       │   ├── main.py                     # FastAPI application entry
│       │   │
│       │   ├── api/                        # API routes
│       │   │   ├── __init__.py
│       │   │   ├── v1/                     # OpenAI-compatible endpoints
│       │   │   │   ├── __init__.py
│       │   │   │   ├── chat.py             # /v1/chat/completions
│       │   │   │   ├── completions.py      # /v1/completions
│       │   │   │   ├── embeddings.py       # /v1/embeddings
│       │   │   │   └── models.py           # /v1/models
│       │   │   │
│       │   │   └── management/             # Management API
│       │   │       ├── __init__.py
│       │   │       ├── keys.py             # /api/v1/keys
│       │   │       ├── providers.py        # /api/v1/providers
│       │   │       ├── policies.py         # /api/v1/policies
│       │   │       └── state.py            # /api/v1/state
│       │   │
│       │   ├── middleware/                  # FastAPI middleware
│       │   │   ├── __init__.py
│       │   │   ├── auth.py                 # Authentication
│       │   │   ├── logging.py              # Request logging
│       │   │   ├── metrics.py              # Metrics collection
│       │   │   └── error_handler.py        # Error handling
│       │   │
│       │   ├── services/                    # Service layer
│       │   │   ├── __init__.py
│       │   │   ├── router_service.py       # Wraps core library
│       │   │   └── config_service.py       # Configuration management
│       │   │
│       │   └── schemas/                     # API schemas (Pydantic)
│       │       ├── __init__.py
│       │       ├── chat.py
│       │       ├── keys.py
│       │       └── errors.py
│       │
│       ├── tests/                           # Proxy tests
│       │   ├── __init__.py
│       │   ├── test_api/
│       │   │   ├── test_chat.py
│       │   │   ├── test_keys.py
│       │   │   └── ...
│       │   └── e2e/
│       │       └── test_proxy_integration.py
│       │
│       ├── pyproject.toml                   # Poetry configuration
│       ├── README.md
│       └── CHANGELOG.md
│
├── scripts/                                 # Utility scripts
│   ├── setup_dev.sh                        # Development setup
│   ├── benchmark.sh                        # Run benchmarks
│   ├── migrate_db.py                       # Database migrations
│   └── generate_docs.py                    # Generate API docs
│
├── .env.example                            # Environment variable template
├── .gitignore
├── .pre-commit-config.yaml                 # Pre-commit hooks
├── pyproject.toml                          # Root Poetry workspace config
├── poetry.lock                             # Lock file (generated)
├── README.md                               # Project README
├── CONTRIBUTING.md                         # Contribution guidelines
├── LICENSE                                 # MIT License
└── CHANGELOG.md                            # Project changelog
```

## Package Structure Details

### Core Package (`packages/core/`)

**Domain Layer (`domain/`):**
- **models/**: Pydantic models representing core entities (APIKey, QuotaState, etc.)
- **components/**: Core business logic components (KeyManager, RoutingEngine, etc.)
- **interfaces/**: Abstract interfaces for infrastructure (ProviderAdapter, StateStore)

**Infrastructure Layer (`infrastructure/`):**
- **state_store/**: State persistence implementations (memory, Redis, MongoDB)
- **observability/**: Logging, metrics, tracing
- **config/**: Configuration management
- **adapters/**: Provider adapter implementations

### Proxy Package (`packages/proxy/`)

**API Layer (`api/`):**
- **v1/**: OpenAI-compatible endpoints
- **management/**: Management API endpoints

**Service Layer (`services/`):**
- Wraps core library for HTTP interface
- Handles request/response transformation

**Middleware (`middleware/`):**
- Authentication, logging, metrics, error handling

## Key Files Explained

**Root `pyproject.toml`:**
```toml
[tool.poetry]
name = "apikeyrouter"
version = "0.1.0"
description = "Intelligent API key routing library and proxy"

[tool.poetry.dependencies]
python = "^3.11"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.4"
pytest-benchmark = "^4.0.0"
ruff = "^0.1.13"
mypy = "^1.8.0"

[workspace]
packages = ["packages/core", "packages/proxy"]
```

**Core Package `pyproject.toml`:**
```toml
[tool.poetry]
name = "apikeyrouter-core"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.11"
pydantic = "^2.5.3"
pydantic-settings = "^2.1.0"
structlog = "^24.1.0"
httpx = "^0.26.0"
motor = {extras = ["srv"], version = "^3.3.2"}
beanie = "^1.23.0"
redis = {extras = ["hiredis"], version = "^5.0.1"}
```

**Proxy Package `pyproject.toml`:**
```toml
[tool.poetry]
name = "apikeyrouter-proxy"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.11"
apikeyrouter-core = {path = "../core", develop = true}
fastapi = "^0.109.0"
uvicorn = {extras = ["standard"], version = "^0.27.0"}
```

## Import Structure

**Core Library Usage:**
```python
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models import APIKey, QuotaState
from apikeyrouter.domain.components import KeyManager, RoutingEngine
```

**Proxy Service:**
```python
from apikeyrouter_proxy.main import app  # FastAPI app
from apikeyrouter_proxy.api.v1 import chat  # Route handlers
```

## Development Workflow

**Local Development:**
```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest

# Run benchmarks
poetry run pytest packages/core/tests/benchmarks/

# Run proxy locally
cd packages/proxy
poetry run uvicorn apikeyrouter_proxy.main:app --reload
```

**Package Publishing:**
- Core library: `apikeyrouter-core` on PyPI
- Proxy service: `apikeyrouter-proxy` on PyPI
- Or install from monorepo: `poetry add apikeyrouter-core --git https://github.com/...`

## Directory Conventions

1. **Tests mirror source structure** - `tests/unit/` mirrors `domain/components/`
2. **Separate integration tests** - `tests/integration/` for cross-component tests
3. **Benchmarks in tests** - `tests/benchmarks/` for performance tests
4. **Fixtures shared** - `tests/fixtures/` for test data
5. **API routes organized by version** - `api/v1/` for versioned endpoints

---

**Select 1-9 or just type your question/feedback:**

1. Proceed to next section (Infrastructure and Deployment)
2. Challenge assumptions
3. Explore alternatives
4. Deep dive analysis
5. Risk assessment
6. Stakeholder perspective
7. Scenario planning
8. Constraint analysis
9. Expert consultation

Or type your feedback/questions about the Source Tree section.
