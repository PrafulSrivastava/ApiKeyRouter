"""Rate limiting middleware for API endpoints."""

import time
from collections import defaultdict
from collections.abc import Callable

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce rate limiting on API endpoints.

    Rate limits:
    - Management API: 100 requests/minute per IP
    - Routing API: Per-key rate limits (handled by core library)
    """

    def __init__(
        self,
        app: Callable,
        management_api_limit: int = 100,
        window_seconds: int = 60,
    ) -> None:
        """Initialize rate limiting middleware.

        Args:
            app: ASGI application instance.
            management_api_limit: Maximum requests per window for management API.
            window_seconds: Time window in seconds for rate limiting.
        """
        super().__init__(app)
        self._management_api_limit = management_api_limit
        self._window_seconds = window_seconds
        # Store request timestamps per IP address
        # Format: {ip_address: [timestamp1, timestamp2, ...]}
        self._request_history: dict[str, list[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address from request.

        Args:
            request: FastAPI request object.

        Returns:
            Client IP address as string.
        """
        # Check for forwarded IP (from proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain
            return forwarded_for.split(",")[0].strip()

        # Check for real IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fall back to direct client IP
        if request.client:
            return request.client.host

        return "unknown"

    def _clean_old_requests(self, ip: str, current_time: float) -> None:
        """Remove requests outside the time window.

        Args:
            ip: Client IP address.
            current_time: Current timestamp.
        """
        cutoff_time = current_time - self._window_seconds
        self._request_history[ip] = [
            timestamp for timestamp in self._request_history[ip] if timestamp > cutoff_time
        ]

    def _check_rate_limit(self, request: Request) -> tuple[bool, int]:
        """Check if request exceeds rate limit.

        Args:
            request: FastAPI request object.

        Returns:
            Tuple of (is_allowed, retry_after_seconds).
            is_allowed: True if request is allowed, False if rate limited.
            retry_after_seconds: Seconds to wait before retry (0 if allowed).
        """
        # Only apply rate limiting to management API
        if not request.url.path.startswith("/api/v1/"):
            return True, 0

        ip = self._get_client_ip(request)
        current_time = time.time()

        # Clean old requests
        self._clean_old_requests(ip, current_time)

        # Check if limit exceeded
        request_count = len(self._request_history[ip])
        if request_count >= self._management_api_limit:
            # Calculate retry after (time until oldest request expires)
            if self._request_history[ip]:
                oldest_request = min(self._request_history[ip])
                retry_after = int(self._window_seconds - (current_time - oldest_request)) + 1
            else:
                retry_after = self._window_seconds
            return False, retry_after

        # Record this request
        self._request_history[ip].append(current_time)
        return True, 0

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse | Response:
        """Process request and enforce rate limiting.

        Args:
            request: FastAPI request object.
            call_next: Next middleware or route handler.

        Returns:
            Response from next handler or 429 if rate limited.
        """
        is_allowed, retry_after = self._check_rate_limit(request)

        if not is_allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded. Too many requests.",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        # Continue to next middleware or route handler
        response = await call_next(request)
        return response
