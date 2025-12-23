"""Authentication middleware for management API endpoints."""

import os
from collections.abc import Callable
from typing import Any

from fastapi import Header, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


def get_management_api_key() -> str | None:
    """Get management API key from environment variable.

    Returns:
        Management API key string or None if not set.
    """
    return os.getenv("APIKEYROUTER_MANAGEMENT_API_KEY")


async def verify_management_api_key(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> bool:
    """Verify management API key from request header.

    This is a FastAPI dependency that can be used to protect routes.

    Args:
        request: FastAPI request object.
        x_api_key: API key from X-API-Key header.

    Returns:
        True if API key is valid.

    Raises:
        HTTPException: 401 if API key is missing or invalid.
    """
    management_api_key = get_management_api_key()

    # Fail secure: if no management API key is configured, deny all access
    if not management_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Management API key not configured. Access denied.",
        )

    # Check if API key is provided
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Verify API key matches
    if x_api_key != management_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid management API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return True


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce authentication on management API endpoints.

    This middleware checks for X-API-Key header on all requests to
    /api/v1/* endpoints and validates it against the management API key.
    """

    def __init__(self, app: Callable[..., Any]) -> None:
        """Initialize authentication middleware.

        Args:
            app: ASGI application instance.
        """
        super().__init__(app)
        self._management_api_key = get_management_api_key()

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        """Process request and enforce authentication.

        Args:
            request: FastAPI request object.
            call_next: Next middleware or route handler.

        Returns:
            Response from next handler or 401 if unauthorized.

        Raises:
            HTTPException: 401 if request is to management API and authentication fails.
        """
        # Only protect management API endpoints
        if request.url.path.startswith("/api/v1/"):
            # Fail secure: if no management API key is configured, deny all access
            if not self._management_api_key:
                return Response(
                    content='{"detail":"Management API key not configured. Access denied."}',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    media_type="application/json",
                    headers={"WWW-Authenticate": "ApiKey"},
                )

            # Get API key from header
            api_key = request.headers.get("X-API-Key")

            if not api_key:
                return Response(
                    content='{"detail":"Missing X-API-Key header"}',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    media_type="application/json",
                    headers={"WWW-Authenticate": "ApiKey"},
                )

            # Verify API key
            if api_key != self._management_api_key:
                return Response(
                    content='{"detail":"Invalid management API key"}',
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    media_type="application/json",
                    headers={"WWW-Authenticate": "ApiKey"},
                )

        # Continue to next middleware or route handler
        response = await call_next(request)
        return response  # type: ignore[no-any-return]
