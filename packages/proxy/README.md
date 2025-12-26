# apikeyrouter-proxy

FastAPI proxy service that exposes the core API key routing library via OpenAI-compatible HTTP endpoints.

## Overview

The `apikeyrouter-proxy` package provides:
- OpenAI-compatible API endpoints (`/v1/chat/completions`, `/v1/completions`, etc.)
- Management API for keys, providers, and policies
- FastAPI-based async HTTP service
- Built on top of `apikeyrouter-core`

## Installation

```bash
poetry add apikeyrouter-proxy
```

Or install from source:

```bash
cd packages/proxy
poetry install
```

## Usage

### Basic Usage

```bash
# Run the proxy service
cd packages/proxy
poetry run uvicorn apikeyrouter_proxy.main:app --reload
```

### With Graceful Shutdown (Recommended)

```bash
# Run using the startup script with graceful shutdown configuration
cd packages/proxy
poetry run python -m apikeyrouter_proxy.run
```

Or configure uvicorn directly:

```bash
# Configure graceful shutdown timeout (default: 30 seconds)
export SHUTDOWN_TIMEOUT_SECONDS=60
poetry run uvicorn apikeyrouter_proxy.main:app --timeout-graceful-shutdown 60
```

### Configuration

The proxy supports graceful shutdown with configurable timeout:

- `SHUTDOWN_TIMEOUT_SECONDS`: Time to wait for in-flight requests to complete (default: 30)
- `PROXY_HOST`: Server host (default: 0.0.0.0)
- `PROXY_PORT`: Server port (default: 8000)
- `PROXY_RELOAD`: Enable auto-reload for development (default: false)

The service will be available at `http://localhost:8000` with:
- API endpoints: `/v1/chat/completions`, `/v1/completions`, etc.
- Management API: `/api/v1/keys`, `/api/v1/providers`, etc.
- API documentation: `/docs` (Swagger UI)

### Graceful Shutdown

The proxy implements graceful shutdown that:
- Stops accepting new connections on SIGTERM
- Waits for in-flight requests to complete (configurable timeout)
- Closes database, Redis, and HTTP client connections gracefully
- Logs all shutdown events for observability

## Documentation

See the main project [README.md](../../README.md) and [documentation](../../docs/) for more details.





