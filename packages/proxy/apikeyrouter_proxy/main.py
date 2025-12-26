"""FastAPI application entry point for ApiKeyRouter Proxy."""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apikeyrouter_proxy.api import management, v1
from apikeyrouter_proxy.middleware.auth import AuthenticationMiddleware
from apikeyrouter_proxy.middleware.cors import CORSMiddleware
from apikeyrouter_proxy.middleware.rate_limit import RateLimitMiddleware
from apikeyrouter_proxy.middleware.security import SecurityHeadersMiddleware

# Initialize structured logger
logger = structlog.get_logger(__name__)

# Global state for resources that need cleanup
_state_store = None
_redis_client = None
_http_clients: list[Any] = []


def get_shutdown_timeout() -> int:
    """Get shutdown timeout from environment variable.

    Returns:
        Shutdown timeout in seconds (default: 30).
    """
    return int(os.getenv("SHUTDOWN_TIMEOUT_SECONDS", "30"))


async def cleanup_resources() -> None:
    """Clean up all application resources during shutdown.

    Closes:
    - MongoDB connections (if state store is initialized)
    - Redis connections (if Redis client is initialized)
    - HTTP client connections (if any persistent clients exist)
    - Background tasks
    """
    logger.info("shutdown_started", message="Beginning graceful shutdown")

    # Close MongoDB connections (if state store exists)
    if _state_store is not None:
        try:
            if hasattr(_state_store, "close"):
                await _state_store.close()
                logger.info("shutdown_resource_closed", resource="mongodb", status="success")
        except Exception as e:
            logger.warning(
                "shutdown_resource_error",
                resource="mongodb",
                error=str(e),
                status="warning",
            )

    # Close Redis connections (if Redis client exists)
    if _redis_client is not None:
        try:
            if hasattr(_redis_client, "close"):
                await _redis_client.close()
            if hasattr(_redis_client, "connection_pool") and _redis_client.connection_pool:
                await _redis_client.connection_pool.disconnect()
            logger.info("shutdown_resource_closed", resource="redis", status="success")
        except Exception as e:
            logger.warning(
                "shutdown_resource_error",
                resource="redis",
                error=str(e),
                status="warning",
            )

    # Close HTTP client connections
    for client in _http_clients:
        try:
            if hasattr(client, "aclose"):
                await client.aclose()
            elif hasattr(client, "close"):
                await client.close()
        except Exception as e:
            logger.warning(
                "shutdown_resource_error",
                resource="http_client",
                error=str(e),
                status="warning",
            )

    if _http_clients:
        logger.info(
            "shutdown_resource_closed",
            resource="http_clients",
            count=len(_http_clients),
            status="success",
        )
        _http_clients.clear()

    logger.info("shutdown_completed", message="Graceful shutdown completed successfully")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan context manager for startup and shutdown.

    Handles:
    - Application startup (initialization)
    - Application shutdown (cleanup with timeout)

    Yields:
        None: Application runs between startup and shutdown.
    """
    # Startup
    logger.info("application_startup", message="ApiKeyRouter Proxy starting up")
    shutdown_timeout = get_shutdown_timeout()
    logger.info("shutdown_timeout_configured", timeout_seconds=shutdown_timeout)

    # Application runs here
    yield

    # Shutdown
    logger.info("shutdown_signal_received", message="Shutdown signal received, starting graceful shutdown")
    try:
        # Wait for cleanup with timeout
        await asyncio.wait_for(cleanup_resources(), timeout=shutdown_timeout)
    except asyncio.TimeoutError:
        logger.warning(
            "shutdown_timeout_exceeded",
            timeout_seconds=shutdown_timeout,
            message=f"Shutdown timeout ({shutdown_timeout}s) exceeded, forcing exit",
        )
        # Force cleanup after timeout
        try:
            await cleanup_resources()
        except Exception as e:
            logger.error(
                "shutdown_force_cleanup_error",
                error=str(e),
                message="Error during forced cleanup",
            )
    except Exception as e:
        logger.error(
            "shutdown_error",
            error=str(e),
            message="Unexpected error during shutdown",
        )


app = FastAPI(
    title="ApiKeyRouter Proxy",
    version="0.1.0",
    description="FastAPI proxy service for intelligent API key routing",
    lifespan=lifespan,
)

# Add middleware in order (last added is first executed)
# Security headers should be added first (outermost)
app.add_middleware(
    SecurityHeadersMiddleware, enable_hsts=os.getenv("ENABLE_HSTS", "false").lower() == "true"
)

# CORS middleware
app.add_middleware(CORSMiddleware)

# Rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# Authentication middleware (innermost, executes last)
app.add_middleware(AuthenticationMiddleware)

# Get UI directory path relative to this module
_ui_dir = Path(__file__).parent.parent / "tests" / "UI"
_ui_index = _ui_dir / "index.html"

# Only mount UI if directory exists (for development/testing)
if _ui_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(_ui_dir)), name="ui")

    @app.get("/", include_in_schema=False)
    async def root():
        if _ui_index.exists():
            return FileResponse(str(_ui_index))
        return {"message": "ApiKeyRouter Proxy API", "docs": "/docs"}

app.include_router(v1.router, prefix="/v1")
app.include_router(management.router, prefix="/api/v1")
