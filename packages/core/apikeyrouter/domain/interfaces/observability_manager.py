"""ObservabilityManager interface for events and logging."""

from abc import ABC, abstractmethod
from typing import Any


class ObservabilityManager(ABC):
    """Abstract interface for observability (events, logging, metrics).

    ObservabilityManager provides structured logging, event emission,
    and metrics collection capabilities.
    """

    @abstractmethod
    async def emit_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Emit an event for observability.

        Args:
            event_type: Type of event (e.g., "key_registered", "state_transition").
            payload: Event payload data.
            metadata: Optional metadata (request_id, timestamp, etc.).

        Raises:
            ObservabilityError: If event emission fails.
        """
        pass

    @abstractmethod
    async def log(
        self,
        level: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Log a message with structured context.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            message: Log message.
            context: Optional structured context data.

        Raises:
            ObservabilityError: If logging fails.
        """
        pass


class ObservabilityError(Exception):
    """Raised when observability operations fail."""

    pass




