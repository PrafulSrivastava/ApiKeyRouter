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

```bash
# Run the proxy service
cd packages/proxy
poetry run uvicorn apikeyrouter_proxy.main:app --reload
```

The service will be available at `http://localhost:8000` with:
- API endpoints: `/v1/chat/completions`, `/v1/completions`, etc.
- Management API: `/api/v1/keys`, `/api/v1/providers`, etc.
- API documentation: `/docs` (Swagger UI)

## Documentation

See the main project [README.md](../../README.md) and [documentation](../../docs/) for more details.




