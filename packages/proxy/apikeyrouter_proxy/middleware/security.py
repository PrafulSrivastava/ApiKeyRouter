"""Security headers middleware for API responses."""

from collections.abc import Callable
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses.

    Adds the following security headers:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: max-age=31536000 (HTTPS only, added conditionally)
    """

    def __init__(self, app: Callable[..., Any], enable_hsts: bool = False) -> None:
        """Initialize security headers middleware.

        Args:
            app: ASGI application instance.
            enable_hsts: If True, add Strict-Transport-Security header.
                        Should only be enabled in production with HTTPS.
        """
        super().__init__(app)
        self._enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        """Process request and add security headers to response.

        Args:
            request: FastAPI request object.
            call_next: Next middleware or route handler.

        Returns:
            Response with security headers added.
        """
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Add HSTS header only if enabled and request is HTTPS
        if self._enable_hsts and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response  # type: ignore[no-any-return]
