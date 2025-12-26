"""Authentication middleware for management API endpoints."""

import os
import time
import warnings
from collections import defaultdict
from collections.abc import Callable
from typing import Any

import structlog
from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

# Initialize structured logger
logger = structlog.get_logger(__name__)


def get_management_api_key() -> str | None:
    """Get management API key from environment variable.

    Returns:
        Management API key string or None if not set.
    """
    return os.getenv("MANAGEMENT_API_KEY")


def _get_client_ip(request: Request) -> str:
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


def _parse_bearer_token(authorization: str | None) -> str | None:
    """Parse Bearer token from Authorization header.

    Args:
        authorization: Authorization header value.

    Returns:
        API key string if valid Bearer token, None otherwise.
    """
    if not authorization:
        return None

    # Check if it starts with "Bearer "
    if not authorization.startswith("Bearer "):
        return None

    # Extract token after "Bearer "
    token = authorization[7:].strip()
    return token if token else None


async def require_management_auth(request: Request) -> bool:
    """FastAPI dependency to require management API authentication.

    This dependency can be used to protect routes that require authentication.

    Args:
        request: FastAPI request object.

    Returns:
        True if authentication is successful.

    Raises:
        HTTPException: 401 if API key is missing or invalid, 403 for insufficient permissions.
    """
    management_api_key = get_management_api_key()

    # Fail secure: if no management API key is configured, deny all access
    if not management_api_key:
        logger.warning(
            "management_api_key_not_configured",
            endpoint=request.url.path,
            method=request.method,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Management API key not configured. Access denied.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get Authorization header
    authorization = request.headers.get("Authorization")

    # Check if Authorization header is missing
    if not authorization:
        client_ip = _get_client_ip(request)
        logger.warning(
            "authentication_failed",
            reason="missing_authorization_header",
            endpoint=request.url.path,
            method=request.method,
            client_ip=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Parse Bearer token
    api_key = _parse_bearer_token(authorization)

    # Check if Bearer token format is invalid
    if not api_key:
        client_ip = _get_client_ip(request)
        logger.warning(
            "authentication_failed",
            reason="invalid_authorization_format",
            endpoint=request.url.path,
            method=request.method,
            client_ip=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected: Bearer {api_key}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify API key matches
    if api_key != management_api_key:
        client_ip = _get_client_ip(request)
        logger.warning(
            "authentication_failed",
            reason="invalid_api_key",
            endpoint=request.url.path,
            method=request.method,
            client_ip=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid management API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Log successful authentication
    client_ip = _get_client_ip(request)
    logger.info(
        "authentication_success",
        endpoint=request.url.path,
        method=request.method,
        client_ip=client_ip,
    )

    # Attach authentication status to request state
    request.state.authenticated = True
    request.state.management_api_key = api_key

    return True


class ManagementAPIAuthMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce authentication on management API endpoints.

    This middleware checks for Authorization: Bearer {api_key} header on all requests to
    /api/v1/* endpoints and validates it against the management API key.
    Includes rate limiting for authentication attempts to prevent brute force attacks.
    """

    def __init__(
        self,
        app: Callable[..., Any],
        auth_rate_limit: int = 5,
        auth_rate_window_seconds: int = 60,
    ) -> None:
        """Initialize authentication middleware.

        Args:
            app: ASGI application instance.
            auth_rate_limit: Maximum failed authentication attempts per window per IP.
            auth_rate_window_seconds: Time window in seconds for rate limiting.
        """
        super().__init__(app)
        self._management_api_key = get_management_api_key()
        self._auth_rate_limit = auth_rate_limit
        self._auth_rate_window_seconds = auth_rate_window_seconds
        # Store failed authentication attempt timestamps per IP address
        # Format: {ip_address: [timestamp1, timestamp2, ...]}
        self._auth_attempt_history: dict[str, list[float]] = defaultdict(list)

        # Warn in development if key is not set
        if not self._management_api_key:
            is_production = os.getenv("ENVIRONMENT", "").lower() == "production"
            if not is_production:
                warnings.warn(
                    "MANAGEMENT_API_KEY not set. Management API access will be denied. "
                    "This is acceptable in development but must be set in production.",
                    UserWarning,
                    stacklevel=2,
                )
            else:
                logger.error(
                    "management_api_key_not_configured",
                    message="MANAGEMENT_API_KEY must be set in production",
                )

    def _clean_old_auth_attempts(self, ip: str, current_time: float) -> None:
        """Remove authentication attempts outside the time window.

        Args:
            ip: Client IP address.
            current_time: Current timestamp.
        """
        cutoff_time = current_time - self._auth_rate_window_seconds
        self._auth_attempt_history[ip] = [
            timestamp
            for timestamp in self._auth_attempt_history[ip]
            if timestamp > cutoff_time
        ]

    def _check_auth_rate_limit(self, ip: str) -> tuple[bool, int]:
        """Check if authentication attempts exceed rate limit.

        Args:
            ip: Client IP address.

        Returns:
            Tuple of (is_allowed, retry_after_seconds).
            is_allowed: True if request is allowed, False if rate limited.
            retry_after_seconds: Seconds to wait before retry (0 if allowed).
        """
        current_time = time.time()

        # Clean old attempts
        self._clean_old_auth_attempts(ip, current_time)

        # Check if limit exceeded
        attempt_count = len(self._auth_attempt_history[ip])
        if attempt_count >= self._auth_rate_limit:
            # Calculate retry after (time until oldest attempt expires)
            if self._auth_attempt_history[ip]:
                oldest_attempt = min(self._auth_attempt_history[ip])
                retry_after = int(
                    self._auth_rate_window_seconds - (current_time - oldest_attempt)
                ) + 1
            else:
                retry_after = self._auth_rate_window_seconds
            return False, retry_after

        return True, 0

    def _record_failed_auth_attempt(self, ip: str) -> None:
        """Record a failed authentication attempt.

        Args:
            ip: Client IP address.
        """
        current_time = time.time()
        self._auth_attempt_history[ip].append(current_time)

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:
        """Process request and enforce authentication.

        Args:
            request: FastAPI request object.
            call_next: Next middleware or route handler.

        Returns:
            Response from next handler or 401 if unauthorized.
        """
        # Only protect management API endpoints
        # Exclude public endpoints
        path = request.url.path
        public_endpoints = ["/v1/chat/completions", "/health", "/healthz", "/status"]

        if path.startswith("/api/v1/") and path not in public_endpoints:
            client_ip = _get_client_ip(request)

            # Check rate limit for authentication attempts
            is_allowed, retry_after = self._check_auth_rate_limit(client_ip)
            if not is_allowed:
                logger.warning(
                    "authentication_rate_limit_exceeded",
                    endpoint=path,
                    method=request.method,
                    client_ip=client_ip,
                    retry_after=retry_after,
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": "Too many authentication attempts. Please try again later.",
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )

            # Fail secure: if no management API key is configured, deny all access
            if not self._management_api_key:
                self._record_failed_auth_attempt(client_ip)
                logger.warning(
                    "authentication_failed",
                    reason="management_api_key_not_configured",
                    endpoint=path,
                    method=request.method,
                    client_ip=client_ip,
                )
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Management API key not configured. Access denied."},
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Get Authorization header
            authorization = request.headers.get("Authorization")

            # Check if Authorization header is missing
            if not authorization:
                self._record_failed_auth_attempt(client_ip)
                logger.warning(
                    "authentication_failed",
                    reason="missing_authorization_header",
                    endpoint=path,
                    method=request.method,
                    client_ip=client_ip,
                )
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Missing Authorization header"},
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Parse Bearer token
            api_key = _parse_bearer_token(authorization)

            # Check if Bearer token format is invalid
            if not api_key:
                self._record_failed_auth_attempt(client_ip)
                logger.warning(
                    "authentication_failed",
                    reason="invalid_authorization_format",
                    endpoint=path,
                    method=request.method,
                    client_ip=client_ip,
                )
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid Authorization header format. Expected: Bearer {api_key}"},
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Verify API key
            if api_key != self._management_api_key:
                self._record_failed_auth_attempt(client_ip)
                logger.warning(
                    "authentication_failed",
                    reason="invalid_api_key",
                    endpoint=path,
                    method=request.method,
                    client_ip=client_ip,
                )
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid management API key"},
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Log successful authentication
            client_ip = _get_client_ip(request)
            logger.info(
                "authentication_success",
                endpoint=path,
                method=request.method,
                client_ip=client_ip,
            )

            # Attach authentication status to request state
            request.state.authenticated = True
            request.state.management_api_key = api_key

        # Continue to next middleware or route handler
        response = await call_next(request)
        return response  # type: ignore[no-any-return]


# Alias for backward compatibility
AuthenticationMiddleware = ManagementAPIAuthMiddleware
