"""CORS configuration middleware."""

import os
from collections.abc import Callable
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


def get_cors_origins() -> list[str]:
    """Get CORS allowed origins from environment variable.

    Returns:
        List of allowed origins. Defaults to localhost for development.
    """
    cors_origins_env = os.getenv("CORS_ORIGINS", "")
    if cors_origins_env:
        # Split by comma and strip whitespace
        return [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]

    # Default: allow localhost for development
    return [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]


class CORSMiddleware(BaseHTTPMiddleware):
    """Middleware to handle CORS (Cross-Origin Resource Sharing).

    Allows requests from configured origins and handles preflight requests.
    """

    def __init__(self, app: Callable[..., Any], allowed_origins: list[str] | None = None) -> None:
        """Initialize CORS middleware.

        Args:
            app: ASGI application instance.
            allowed_origins: List of allowed origins. If None, loads from environment.
        """
        super().__init__(app)
        self._allowed_origins = allowed_origins or get_cors_origins()

    def _is_origin_allowed(self, origin: str) -> bool:
        """Check if origin is allowed.

        Args:
            origin: Request origin header value.

        Returns:
            True if origin is allowed, False otherwise.
        """
        return origin in self._allowed_origins or "*" in self._allowed_origins

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        """Process request and handle CORS.

        Args:
            request: FastAPI request object.
            call_next: Next middleware or route handler.

        Returns:
            Response with CORS headers added.
        """
        origin = request.headers.get("Origin")

        # Handle preflight requests
        if request.method == "OPTIONS":
            response = Response()
            if origin and self._is_origin_allowed(origin):
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers[
                    "Access-Control-Allow-Methods"
                ] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
                response.headers[
                    "Access-Control-Allow-Headers"
                ] = "Content-Type, Authorization, X-API-Key"
                response.headers["Access-Control-Max-Age"] = "3600"
            return response

        # Process normal request
        response = await call_next(request)

        # Add CORS headers to response
        if origin and self._is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Expose-Headers"] = "Content-Type, X-Request-ID"

        return response  # type: ignore[no-any-return]
