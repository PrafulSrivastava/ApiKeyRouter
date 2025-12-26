"""Startup script for ApiKeyRouter Proxy with graceful shutdown configuration."""

import os

import uvicorn


def main() -> None:
    """Start the proxy server with graceful shutdown configuration."""
    # Get configuration from environment variables
    host = os.getenv("PROXY_HOST", "0.0.0.0")
    port = int(os.getenv("PROXY_PORT", "8000"))
    reload = os.getenv("PROXY_RELOAD", "false").lower() == "true"
    shutdown_timeout = int(os.getenv("SHUTDOWN_TIMEOUT_SECONDS", "30"))

    # Configure uvicorn with graceful shutdown
    config = uvicorn.Config(
        "apikeyrouter_proxy.main:app",
        host=host,
        port=port,
        reload=reload,
        timeout_graceful_shutdown=shutdown_timeout,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )

    server = uvicorn.Server(config)
    server.run()


if __name__ == "__main__":
    main()

