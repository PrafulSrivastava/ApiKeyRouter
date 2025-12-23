"""SystemError model for standardized error handling."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    """Categories of system errors."""

    AuthenticationError = "authentication_error"
    """Authentication failed (401, invalid API key)."""

    RateLimitError = "rate_limit_error"
    """Rate limit exceeded (429)."""

    QuotaExceededError = "quota_exceeded_error"
    """Quota/capacity exhausted."""

    ProviderError = "provider_error"
    """Provider-specific error (5xx, network issues)."""

    TimeoutError = "timeout_error"
    """Request timeout."""

    NetworkError = "network_error"
    """Network connectivity issue."""

    ValidationError = "validation_error"
    """Request validation failed (400)."""

    BudgetExceededError = "budget_exceeded_error"
    """Budget limit exceeded."""

    UnknownError = "unknown_error"
    """Unknown or unclassified error."""


class SystemError(Exception):
    """Standardized system error for provider operations.

    SystemError represents errors that occur during provider operations,
    normalized to a consistent format regardless of the provider.

    Example:
        ```python
        raise SystemError(
            category=ErrorCategory.RateLimitError,
            message="Rate limit exceeded",
            provider_code="rate_limit_exceeded",
            retryable=True
        )
        ```
    """

    def __init__(
        self,
        category: ErrorCategory | str,
        message: str,
        provider_code: str | None = None,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        retry_after: int | None = None,
    ) -> None:
        """Initialize SystemError.

        Args:
            category: Error category (ErrorCategory enum or string).
            message: Human-readable error message.
            provider_code: Original provider error code if available.
            retryable: Whether the error is retryable.
            details: Additional error details.
            retry_after: Retry after this many seconds (from Retry-After header).
        """
        self.category = ErrorCategory(category) if isinstance(category, str) else category
        self.message = message
        self.provider_code = provider_code
        self.retryable = retryable
        self.details = details or {}
        self.retry_after = retry_after
        super().__init__(self.message)

    def __repr__(self) -> str:
        """String representation of the error."""
        return (
            f"SystemError(category={self.category.value}, "
            f"message={self.message!r}, retryable={self.retryable})"
        )

    def __str__(self) -> str:
        """Human-readable error message."""
        return self.message
