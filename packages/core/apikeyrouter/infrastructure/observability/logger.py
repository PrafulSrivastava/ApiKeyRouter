"""Default observability manager implementation."""

import logging
from datetime import datetime
from typing import Any

import structlog

from apikeyrouter.domain.interfaces.observability_manager import (
    ObservabilityError,
    ObservabilityManager,
)


def sanitize_for_logging(data: Any) -> Any:
    """Sanitize data to remove sensitive information before logging.

    Removes key_material fields from dictionaries and nested structures
    to prevent accidental logging of sensitive data.

    Args:
        data: Data structure to sanitize (dict, list, or primitive).

    Returns:
        Sanitized data structure with key_material fields removed.
    """
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            # Skip key_material fields
            if key == "key_material":
                sanitized[key] = "[REDACTED]"
            else:
                # Recursively sanitize nested structures
                sanitized[key] = sanitize_for_logging(value)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_for_logging(item) for item in data]
    elif isinstance(data, str):
        # Check if string looks like an API key (starts with common prefixes)
        # This is a safety check, but primary protection is removing key_material fields
        if (
            data.startswith(("sk-", "pk-", "xai-", "claude-", "anthropic-")) and len(data) > 20
        ):  # API keys are typically longer
            return "[REDACTED]"
    return data


class DefaultObservabilityManager(ObservabilityManager):
    """Default implementation of ObservabilityManager using structlog with JSON format.

    Provides structured logging with JSON output for machine readability,
    while maintaining human-readable output in development mode.
    """

    def __init__(self, log_level: str = "INFO", json_format: bool = True) -> None:
        """Initialize DefaultObservabilityManager.

        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
            json_format: If True, use JSON format for structured logging.
                        If False, use human-readable format (development mode).
        """
        self._log_level = log_level
        self._json_format = json_format

        # Configure structlog
        processors = [
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
        ]

        if json_format:
            # JSON format for production
            processors.append(structlog.processors.JSONRenderer())
        else:
            # Human-readable format for development
            processors.append(structlog.dev.ConsoleRenderer())

        structlog.configure(
            processors=processors,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        # Configure standard logging for structlog to wrap
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), logging.INFO),
            format="%(message)s"
            if json_format
            else "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        self._logger = structlog.get_logger("apikeyrouter")

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
            metadata: Optional metadata (request_id, timestamp, correlation_id, etc.).

        Raises:
            ObservabilityError: If event emission fails.
        """
        try:
            # Sanitize payload and metadata to remove sensitive data
            sanitized_payload = sanitize_for_logging(payload)

            # Merge metadata into event data
            event_data = {
                **sanitized_payload,
            }
            if metadata:
                sanitized_metadata = sanitize_for_logging(metadata)
                event_data["metadata"] = sanitized_metadata
                # Add timestamp if not present
                if "timestamp" not in sanitized_metadata:
                    event_data["metadata"]["timestamp"] = datetime.utcnow().isoformat()

            self._logger.info(
                "Event emitted",
                event_type=event_type,
                **event_data,
            )
        except Exception as e:
            raise ObservabilityError(f"Failed to emit event: {e}") from e

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
            context: Optional structured context data (request_id, correlation_id, etc.).

        Raises:
            ObservabilityError: If logging fails.
        """
        try:
            # Sanitize context to remove sensitive data
            sanitized_context = sanitize_for_logging(context) if context else None

            # Sanitize message string as well
            sanitized_message = sanitize_for_logging(message)

            log_method = getattr(self._logger, level.lower(), self._logger.info)
            if sanitized_context:
                log_method(sanitized_message, **sanitized_context)
            else:
                log_method(sanitized_message)
        except Exception as e:
            raise ObservabilityError(f"Failed to log message: {e}") from e
