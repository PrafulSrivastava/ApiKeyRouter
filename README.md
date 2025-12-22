# API Key Router

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Type checking: mypy](https://img.shields.io/badge/type%20checking-mypy-blue.svg)](https://mypy.readthedocs.io/)

Intelligent API key routing library and proxy service for managing multiple LLM provider API keys with quota awareness, cost optimization, and intelligent routing.

## Features

- 🔄 **Intelligent Routing**: Automatically routes requests across multiple API keys based on availability, cost, and reliability
- 📊 **Quota Awareness**: Tracks and manages API quotas, rate limits, and usage across providers
- 💰 **Cost Optimization**: Minimizes costs by selecting the most cost-effective keys while maintaining reliability
- 🔌 **Provider Agnostic**: Works with OpenAI, Anthropic, Gemini, and other LLM providers
- 🚀 **FastAPI Proxy**: OpenAI-compatible HTTP API for easy integration
- 🔒 **Secure**: Encrypted key storage and secure state management
- 📈 **Observable**: Comprehensive logging, metrics, and tracing
- 🐳 **Docker Ready**: Pre-built Docker images and Docker Compose setup

## Project Structure

This project uses a **monorepo structure** with Poetry workspace to manage the core library and proxy service packages together.

```
apikeyrouter/
├── packages/
│   ├── core/              # Core library package (apikeyrouter-core)
│   └── proxy/             # Proxy service package (apikeyrouter-proxy)
├── docs/                  # Documentation
├── pyproject.toml         # Root workspace configuration
└── poetry.lock           # Dependency lock file (generated)
```

### Package Overview

- **apikeyrouter-core**: Core library providing intelligent API key routing, quota management, and cost optimization
- **apikeyrouter-proxy**: FastAPI proxy service that exposes the core library via OpenAI-compatible HTTP endpoints

## Prerequisites

- **Python 3.11+**: Required for all packages
- **Poetry 1.7.1+**: Package manager and dependency management
  - Installation: Follow [Poetry installation guide](https://python-poetry.org/docs/#installation)
  - Verify: `poetry --version`
- **Docker & Docker Compose** (optional, for local MongoDB/Redis):
  - Installation: [Docker Desktop](https://www.docker.com/products/docker-desktop) or [Docker Engine](https://docs.docker.com/engine/install/)
  - Verify: `docker --version` and `docker-compose --version`

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd ApiKeyRouter
   ```

2. **Install dependencies:**
   ```bash
   poetry install
   ```
   This will install dependencies for all workspace packages (core and proxy).

3. **Generate lock file (if not already present):**
   ```bash
   poetry lock
   ```

4. **Set up environment variables (optional):**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Start local services with Docker Compose (optional):**
   ```bash
   docker-compose up -d
   ```
   This starts MongoDB (and optionally Redis) for local development and testing.

## Development Workflow

### Working with the Monorepo

The Poetry workspace allows you to work with both packages simultaneously:

- **Install all dependencies:** `poetry install` (from root)
- **Add dependency to core package:** `poetry add <package> --directory packages/core`
- **Add dependency to proxy package:** `poetry add <package> --directory packages/proxy`
- **Run commands in specific package:** `poetry run <command> --directory packages/core`

### Running Tests

The project includes comprehensive test suites: unit tests, integration tests, and performance benchmarks.

**Run all tests:**
```bash
poetry run pytest
```

**Run tests for specific package:**
```bash
# Core package tests
poetry run pytest packages/core/tests

# Proxy package tests
poetry run pytest packages/proxy/tests
```

**Run specific test types:**

```bash
# Unit tests only
poetry run pytest packages/core/tests/unit

# Integration tests only
poetry run pytest packages/core/tests/integration

# Benchmark/performance tests
poetry run pytest packages/core/tests/benchmarks --benchmark-only

# Run tests with specific markers
poetry run pytest -m unit          # Unit tests
poetry run pytest -m integration  # Integration tests
poetry run pytest -m benchmark    # Benchmark tests
```

**Benchmark Tests:**

Performance benchmarks measure routing decision time, key lookup performance, and quota calculation speed:

```bash
# Run all benchmark tests with performance metrics
poetry run pytest packages/core/tests/benchmarks --benchmark-only

# Run specific benchmark file
poetry run pytest packages/core/tests/benchmarks/benchmark_routing.py --benchmark-only

# Run benchmarks with verbose output
poetry run pytest packages/core/tests/benchmarks --benchmark-only -v

# Compare benchmark results (saves to .benchmarks/)
poetry run pytest packages/core/tests/benchmarks --benchmark-only --benchmark-save=baseline
```

**Performance Targets:**
- Key lookup: p95 < 1ms
- Quota operations: p95 < 5ms
- Routing decisions: p95 < 10ms

**Test Coverage:**

```bash
# Run tests with coverage report
poetry run pytest --cov=packages/core/apikeyrouter --cov-report=html

# View coverage report
# Open htmlcov/index.html in your browser
```

**Note:** Some integration tests require optional dependencies (e.g., `motor` for MongoDB tests). These tests are automatically skipped if dependencies are not installed.

### Code Quality

The project uses **ruff** for linting and formatting, and **mypy** for type checking. All quality checks run automatically in CI.

**Format code:**
```bash
poetry run ruff format .
```

**Lint code:**
```bash
poetry run ruff check .
```

**Type check:**
```bash
poetry run mypy packages/core packages/proxy
```

**Run all quality checks:**
```bash
poetry run ruff format . && poetry run ruff check . && poetry run mypy packages/core packages/proxy
```

**Pre-commit Hooks (Optional):**

Install pre-commit hooks to automatically run quality checks before each commit:

```bash
# Install pre-commit (if not already installed)
poetry add --group dev pre-commit

# Install the git hook scripts
poetry run pre-commit install

# Run hooks manually on all files
poetry run pre-commit run --all-files
```

Pre-commit hooks will automatically:
- Fix trailing whitespace and end-of-file issues
- Format code with ruff
- Check linting with ruff
- Validate YAML, JSON, and TOML files

**Code Style Standards:**

See [`docs/architecture/coding-standards.md`](docs/architecture/coding-standards.md) for detailed coding standards and conventions.

Key standards:
- **Line Length:** 100 characters
- **Formatter:** ruff (format on save recommended)
- **Type Checking:** mypy with strict mode enabled
- **Import Sorting:** Automatic via ruff

### Running the Proxy Service

```bash
cd packages/proxy
poetry run uvicorn apikeyrouter_proxy.main:app --reload
```

### Development Environment Setup

**Docker Compose Services:**

The project includes a `docker-compose.yml` file for local development with optional persistence backends:

- **MongoDB**: Available on `localhost:27017` (for optional persistent storage)
- **Redis**: Optional, commented out by default (uncomment in `docker-compose.yml` to enable)

**Important:** Docker Compose automatically loads all environment variables from the `.env` file. You only need to manage environment variables in one place.

**Start services:**
```bash
# Ensure .env file exists (copy from .env.example if needed)
cp .env.example .env
# Edit .env with your configuration
docker-compose up -d
```

**Stop services:**
```bash
docker-compose down
```

**View logs:**
```bash
docker-compose logs -f
```

**Service Health Checks:**

Both MongoDB and Redis services include health checks that verify they're ready before use. Services will restart automatically if they fail.

**Environment Variables:**

All environment variables are managed through the `.env` file. Docker Compose automatically loads all variables from `.env` - you don't need to configure them separately in `docker-compose.yml`.

Copy `.env.example` to `.env` and configure as needed:

- **Required**: `APIKEYROUTER_ENCRYPTION_KEY` (generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
- **MongoDB**: `MONGODB_URL`, `MONGO_INITDB_DATABASE`
- **Redis**: `REDIS_URL` (uncomment redis service in docker-compose.yml first)
- **Proxy**: `PORT`, `APIKEYROUTER_MANAGEMENT_API_KEY`, `ENABLE_HSTS`, `CORS_ORIGINS`
- **Core Settings**: `APIKEYROUTER_MAX_DECISIONS`, `APIKEYROUTER_LOG_LEVEL`, etc.

See `.env.example` for a complete list of all available environment variables.
- **Observability**: `LOG_LEVEL`, `METRICS_ENABLED`

**Note:** The library works in-memory by default. MongoDB and Redis are optional for testing persistence backends.

## Package Details

### Core Package (`packages/core/`)

The core library provides:
- API key management and state tracking
- Quota awareness and capacity management
- Intelligent routing algorithms
- Cost optimization
- Provider adapter interfaces

**Key Dependencies:**
- `pydantic` - Data validation and models
- `httpx` - Async HTTP client
- `structlog` - Structured logging

### Proxy Package (`packages/proxy/`)

The proxy service provides:
- OpenAI-compatible HTTP API endpoints
- Management API for keys, providers, and policies
- FastAPI-based async HTTP server

**Key Dependencies:**
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `apikeyrouter-core` - Core library (local dependency)

## Security

### Reporting Security Issues

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to [security@example.com] or see [SECURITY.md](SECURITY.md) for details.

### Security Practices

- **Dependency Scanning**: Automated vulnerability scanning runs on every commit
- **Static Analysis**: Bandit scans code for security issues
- **Secret Scanning**: Automated secret scanning prevents accidental commits
- **Dependabot**: Automated security updates for dependencies
- **Security Headers**: All API responses include security headers
- **Encryption**: API keys encrypted at rest using AES-256
- **Input Validation**: All inputs validated to prevent injection attacks
- **Audit Logging**: All security events logged

See [SECURITY.md](SECURITY.md) for detailed security information.

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/your-username/ApiKeyRouter.git
cd ApiKeyRouter

# Install dependencies
poetry install

# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Run the proxy service
cd packages/proxy
poetry run uvicorn apikeyrouter_proxy.main:app --reload
```

### Basic Usage

```python
from apikeyrouter import ApiKeyRouter
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

# Initialize router
router = ApiKeyRouter()

# Register provider and keys
await router.register_provider("openai", OpenAIAdapter())
await router.register_key("sk-your-key-1", "openai")
await router.register_key("sk-your-key-2", "openai")

# Route a request
from apikeyrouter.domain.models import RequestIntent, Message

intent = RequestIntent(
    model="gpt-4",
    messages=[Message(role="user", content="Hello!")],
    provider_id="openai"
)

response = await router.route(intent)
```

See [Quick Start Guide](docs/guides/quick-start.md) for more examples.

## Documentation

- **[API Reference](packages/core/API_REFERENCE.md)**: Complete API documentation
- **[Architecture](docs/architecture/)**: System architecture and design decisions
- **[User Guides](docs/guides/)**: Step-by-step guides and tutorials
- **[Use Cases](docs/use-cases.md)**: Common use cases and examples

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on:

- Code of Conduct
- Development workflow
- Coding standards
- Testing requirements
- Pull request process

### Quick Contribution Guide

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes following our coding standards
4. Write or update tests
5. Commit your changes (`git commit -m 'feat: add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: Check the [docs](docs/) directory
- **Issues**: [GitHub Issues](https://github.com/your-username/ApiKeyRouter/issues)
- **Security**: See [SECURITY.md](SECURITY.md) for reporting security vulnerabilities

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Uses [Pydantic](https://docs.pydantic.dev/) for data validation
- Powered by [Poetry](https://python-poetry.org/) for dependency management

