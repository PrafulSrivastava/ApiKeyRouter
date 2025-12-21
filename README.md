# API Key Router

Intelligent API key routing library and proxy service for managing multiple LLM provider API keys with quota awareness, cost optimization, and intelligent routing.

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

```bash
# Run all tests
poetry run pytest

# Run tests for specific package
poetry run pytest packages/core/tests
poetry run pytest packages/proxy/tests
```

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

**Start services:**
```bash
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

Copy `.env.example` to `.env` and configure as needed:

- **MongoDB**: `MONGODB_URL`, `MONGODB_DATABASE`, `MONGODB_ENABLED`
- **Redis**: `REDIS_URL`, `REDIS_ENABLED` (uncomment redis service in docker-compose.yml first)
- **Proxy**: `PROXY_HOST`, `PROXY_PORT`, `PROXY_RELOAD`
- **Management API**: `MANAGEMENT_API_KEY`, `MANAGEMENT_API_ENABLED`
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

## Contributing

See `CONTRIBUTING.md` for contribution guidelines.

## License

MIT License - see `LICENSE` file for details.

