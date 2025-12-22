# Tech Stack

## Cloud Infrastructure

**Provider:** Not applicable (library is cloud-agnostic; proxy can be deployed to any platform)

**Key Services:** 
- **Deployment Platforms:** Railway, Render, Vercel (stateless deployment support)
- **Optional Persistence:** Redis (for distributed state), PostgreSQL (for audit logs/metrics)
- **Monitoring:** (To be determined - see options below)

**Deployment Regions:** Multi-region support via deployment platform choice

## Technology Stack Selection

Before finalizing the technology stack table, here are the key decisions needed. For each category, I'll present options with recommendations:

### 1. Python Runtime & Version

**Options:**
- **Python 3.11** - Latest stable, excellent async performance
- **Python 3.10** - Widely supported, good async support
- **Python 3.12** - Latest features, may have compatibility concerns

**Recommendation:** **Python 3.11** - Best balance of performance, stability, and ecosystem support. Async improvements in 3.11 are significant for our use case.

### 2. Package Management

**Options:**
- **Poetry** - Modern dependency management, lock files, project management
- **pip + setuptools** - Standard, simple, widely understood
- **Hatch** - Modern, PEP 517/621 compliant, fast

**Recommendation:** **Poetry** - Better dependency resolution, lock files ensure reproducible builds, good for monorepo structure.

### 3. HTTP Framework (Proxy)

**Options:**
- **FastAPI** - Modern, async, automatic OpenAPI docs, excellent performance
- **Flask** - Simple, widely used, but synchronous by default
- **Starlette** - Lightweight, async, FastAPI is built on it

**Recommendation:** **FastAPI** - Matches competitor (LLM-API-Key-Proxy), excellent async support, automatic API documentation, high performance.

### 4. HTTP Client Library

**Options:**
- **httpx** - Modern async HTTP client, excellent API, supports HTTP/2
- **aiohttp** - Mature async HTTP client, widely used
- **requests** - Synchronous, but simple and well-known

**Recommendation:** **httpx** - Modern async API, better performance, HTTP/2 support, excellent for async/await patterns.

### 5. Configuration Management

**Options:**
- **pydantic-settings** - Type-safe settings, validation, environment variable support
- **python-dotenv** - Simple .env file support
- **dynaconf** - Multi-environment configuration

**Recommendation:** **pydantic-settings** - Type safety, validation, excellent for stateless deployment with environment variables.

### 6. Logging & Observability

**Options:**
- **structlog** - Structured logging, excellent for observability
- **loguru** - Simple, powerful, developer-friendly
- **Standard logging** - Built-in, but less structured

**Recommendation:** **structlog** - Structured logging essential for observability requirements, excellent for JSON output, supports context propagation.

### 7. Testing Framework

**Options:**
- **pytest** - Industry standard, excellent fixtures, plugins
- **unittest** - Built-in, but less feature-rich
- **nose2** - Alternative, but less popular

**Recommendation:** **pytest** - Industry standard, excellent async support, rich plugin ecosystem, great for benchmarking integration.

### 8. Benchmarking Tools

**Options:**
- **pytest-benchmark** - Integrated with pytest, easy to use
- **locust** - Load testing, good for throughput benchmarks
- **py-spy** - Profiling tool for performance analysis

**Recommendation:** **pytest-benchmark** for unit/component benchmarks, **locust** for end-to-end load testing, **py-spy** for profiling.

### 9. Type Checking

**Options:**
- **mypy** - Most popular, mature, good ecosystem support
- **pyright** - Fast, Microsoft-backed, good VS Code integration
- **pyre** - Facebook-backed, but less popular

**Recommendation:** **mypy** - Industry standard, excellent ecosystem support, good for library development.

### 10. Code Quality

**Options:**
- **ruff** - Fast, modern linter/formatter, replaces multiple tools
- **black + flake8 + isort** - Traditional combination
- **pylint** - Comprehensive but slower

**Recommendation:** **ruff** - Fast, modern, combines linting and formatting, excellent performance.

### 11. Optional Persistence (Production)

**Options:**
- **redis** - In-memory store, excellent for distributed state
- **PostgreSQL** - Relational database for audit logs/metrics
- **SQLite** - Lightweight, but limited for production

**Recommendation:** **redis** for state persistence (optional), **PostgreSQL** for audit logs/metrics (optional). Both optional - library works in-memory by default.

### 12. Async Runtime

**Options:**
- **asyncio** (built-in) - Standard library, excellent support
- **uvloop** - Faster event loop, drop-in replacement
- **trio** - Alternative async library, but less ecosystem support

**Recommendation:** **asyncio** (built-in) with **uvloop** as optional optimization for production proxy deployments.

---

## Technology Stack Table

| Category | Technology | Version | Purpose | Rationale |
|----------|------------|---------|---------|-----------|
| **Language** | Python | 3.11 | Primary development language | Best balance of performance, stability, async support |
| **Package Manager** | Poetry | 1.7.1 | Dependency management | Lock files, reproducible builds, monorepo support |
| **HTTP Framework** | FastAPI | 0.109.0 | Proxy service framework | Async, high performance, automatic OpenAPI docs |
| **HTTP Client** | httpx | 0.26.0 | Provider API calls | Modern async API, HTTP/2 support, excellent performance |
| **Configuration** | pydantic-settings | 2.1.0 | Settings management | Type-safe, validation, environment variable support |
| **Logging** | structlog | 24.1.0 | Structured logging | Essential for observability, JSON output, context |
| **Testing** | pytest | 7.4.4 | Testing framework | Industry standard, excellent async support |
| **Benchmarking** | pytest-benchmark | 4.0.0 | Performance benchmarks | Integrated with pytest, easy CI integration |
| **Load Testing** | locust | 2.24.1 | End-to-end performance | Throughput and latency testing |
| **Profiling** | py-spy | 0.3.14 | Performance profiling | Low-overhead profiling for optimization |
| **Type Checking** | mypy | 1.8.0 | Static type checking | Industry standard, library development |
| **Code Quality** | ruff | 0.1.13 | Linting & formatting | Fast, modern, combines multiple tools |
| **Async Runtime** | asyncio | (built-in) | Async runtime | Standard library, excellent support |
| **Async Optimization** | uvloop | 0.19.0 | Fast event loop | Optional performance boost for proxy |
| **State Persistence** | redis | 5.0.1 | Optional distributed state | In-memory store, optional for production |
| **Database** | MongoDB | 7.0 | Optional persistent storage | Document database for audit logs, metrics |
| **MongoDB Driver** | motor | 3.3.2 | Async MongoDB driver | Async/await support for FastAPI |
| **ODM** | beanie | 1.23.0 | MongoDB ODM | Pydantic-based, async, type-safe |
| **Audit Storage** | pydantic | 2.5.3 | Data validation | Type-safe models, validation |
| **HTTP Server** | uvicorn | 0.27.0 | ASGI server | Fast, async, production-ready |

---

**⚠️ IMPORTANT: This Tech Stack is the single source of truth for all development decisions.**
