"""Input validation utilities for security and data integrity."""

import re
from typing import Any

from apikeyrouter.domain.models.request_intent import Message, RequestIntent


class ValidationError(Exception):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: str | None = None) -> None:
        """Initialize ValidationError.

        Args:
            message: Human-readable error message.
            field: Optional field name that failed validation.
        """
        self.message = message
        self.field = field
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return error message with field name if available."""
        if self.field:
            return f"Validation error in field '{self.field}': {self.message}"
        return self.message


# Injection attack patterns to detect
INJECTION_PATTERNS = [
    # SQL injection patterns
    re.compile(
        r"(?i)(union\s+select|select\s+.*\s+from|insert\s+into|delete\s+from|drop\s+table|'\s*or\s*'1'\s*=\s*'1)",
        re.IGNORECASE,
    ),
    # NoSQL injection patterns
    re.compile(r"(?i)(\$where|\$ne|\$gt|\$lt|\$regex|\$exists)", re.IGNORECASE),
    # Command injection patterns
    re.compile(r"[;&|`$(){}[\]<>]", re.IGNORECASE),
    # Script injection patterns
    re.compile(r"(?i)(<script|javascript:|onerror=|onload=)", re.IGNORECASE),
    # Path traversal patterns
    re.compile(r"(\.\./|\.\.\\|%2e%2e%2f)", re.IGNORECASE),
]


def detect_injection_attempt(value: str) -> bool:
    """Detect potential injection attacks in a string value.

    Args:
        value: String value to check for injection patterns.

    Returns:
        True if injection pattern detected, False otherwise.
    """
    if not isinstance(value, str):
        return False

    return any(pattern.search(value) for pattern in INJECTION_PATTERNS)


def validate_key_material(key_material: str) -> None:
    """Validate API key material format and security.

    Args:
        key_material: API key material to validate.

    Raises:
        ValidationError: If validation fails.
    """
    if not key_material or not key_material.strip():
        raise ValidationError("Key material cannot be empty", field="key_material")

    key_material = key_material.strip()

    # Length validation
    if len(key_material) < 10:
        raise ValidationError(
            "Key material must be at least 10 characters long",
            field="key_material",
        )
    if len(key_material) > 500:
        raise ValidationError(
            "Key material must be 500 characters or less",
            field="key_material",
        )

    # Format validation - common API key prefixes
    valid_prefixes = ("sk-", "pk-", "xai-", "claude-", "anthropic-", "gcp-", "aws-")
    if not key_material.startswith(valid_prefixes) and detect_injection_attempt(key_material):
        # Allow keys without known prefixes (for flexibility)
        # But check for suspicious patterns
        raise ValidationError(
            "Key material contains suspicious patterns",
            field="key_material",
        )

    # Check for injection attempts
    if detect_injection_attempt(key_material):
        raise ValidationError(
            "Key material contains potentially malicious content",
            field="key_material",
        )

    # Check for control characters
    if any(ord(c) < 32 and c not in "\t\n\r" for c in key_material):
        raise ValidationError(
            "Key material contains invalid control characters",
            field="key_material",
        )


def validate_provider_id(provider_id: str) -> None:
    """Validate provider ID format.

    Args:
        provider_id: Provider identifier to validate.

    Raises:
        ValidationError: If validation fails.
    """
    if not provider_id or not provider_id.strip():
        raise ValidationError("Provider ID cannot be empty", field="provider_id")

    provider_id = provider_id.strip()

    # Length validation
    if len(provider_id) < 1:
        raise ValidationError("Provider ID cannot be empty", field="provider_id")
    if len(provider_id) > 100:
        raise ValidationError(
            "Provider ID must be 100 characters or less",
            field="provider_id",
        )

    # Format validation: alphanumeric and underscore only
    if not re.match(r"^[a-z0-9_]+$", provider_id.lower()):
        raise ValidationError(
            "Provider ID must contain only lowercase letters, numbers, and underscores",
            field="provider_id",
        )

    # Check for injection attempts
    if detect_injection_attempt(provider_id):
        raise ValidationError(
            "Provider ID contains potentially malicious content",
            field="provider_id",
        )


def validate_metadata(metadata: dict[str, Any] | None) -> None:
    """Validate metadata dictionary structure and content.

    Args:
        metadata: Metadata dictionary to validate.

    Raises:
        ValidationError: If validation fails.
    """
    if metadata is None:
        return  # None is allowed

    if not isinstance(metadata, dict):
        raise ValidationError("Metadata must be a dictionary", field="metadata")

    # Validate metadata size
    if len(metadata) > 100:
        raise ValidationError(
            "Metadata cannot contain more than 100 keys",
            field="metadata",
        )

    # Validate each key-value pair
    for key, value in metadata.items():
        # Validate key
        if not isinstance(key, str):
            raise ValidationError(
                "Metadata keys must be strings",
                field=f"metadata.{key}",
            )

        if len(key) < 1:
            raise ValidationError(
                "Metadata keys cannot be empty",
                field=f"metadata.{key}",
            )

        if len(key) > 100:
            raise ValidationError(
                "Metadata keys must be 100 characters or less",
                field=f"metadata.{key}",
            )

        # Validate key format (alphanumeric, underscore, hyphen)
        if not re.match(r"^[a-zA-Z0-9_-]+$", key):
            raise ValidationError(
                "Metadata keys must contain only letters, numbers, underscores, and hyphens",
                field=f"metadata.{key}",
            )

        # Check for injection attempts in key
        if detect_injection_attempt(key):
            raise ValidationError(
                "Metadata key contains potentially malicious content",
                field=f"metadata.{key}",
            )

        # Validate value
        if value is None:
            continue  # None values are allowed

        # Validate value type (only allow primitive types and lists/dicts of primitives)
        if isinstance(value, str | int | float | bool):
            # Check string values for injection attempts
            if isinstance(value, str):
                if len(value) > 10000:  # Reasonable limit for metadata values
                    raise ValidationError(
                        "Metadata string values must be 10000 characters or less",
                        field=f"metadata.{key}",
                    )
                if detect_injection_attempt(value):
                    raise ValidationError(
                        "Metadata value contains potentially malicious content",
                        field=f"metadata.{key}",
                    )
        elif isinstance(value, list):
            # Validate list values
            if len(value) > 100:
                raise ValidationError(
                    "Metadata list values cannot contain more than 100 items",
                    field=f"metadata.{key}",
                )
            for item in value:
                if not isinstance(item, str | int | float | bool):
                    raise ValidationError(
                        "Metadata list items must be primitive types",
                        field=f"metadata.{key}",
                    )
                if isinstance(item, str) and detect_injection_attempt(item):
                    raise ValidationError(
                        "Metadata list item contains potentially malicious content",
                        field=f"metadata.{key}",
                    )
        elif isinstance(value, dict):
            # Recursively validate nested dictionaries (with depth limit)
            _validate_nested_metadata(value, f"metadata.{key}", max_depth=3, current_depth=1)
        else:
            raise ValidationError(
                "Metadata values must be primitive types, lists, or dictionaries",
                field=f"metadata.{key}",
            )


def _validate_nested_metadata(
    metadata: dict[str, Any],
    field_prefix: str,
    max_depth: int,
    current_depth: int,
) -> None:
    """Recursively validate nested metadata dictionaries.

    Args:
        metadata: Nested metadata dictionary.
        field_prefix: Prefix for field names in error messages.
        max_depth: Maximum nesting depth allowed.
        current_depth: Current nesting depth.

    Raises:
        ValidationError: If validation fails.
    """
    if current_depth > max_depth:
        raise ValidationError(
            f"Metadata nesting depth exceeds maximum of {max_depth}",
            field=field_prefix,
        )

    # Validate nested dictionary (same rules as top-level)
    for key, value in metadata.items():
        nested_field = f"{field_prefix}.{key}"

        # Validate key
        if not isinstance(key, str) or len(key) < 1 or len(key) > 100:
            raise ValidationError(
                "Nested metadata keys must be non-empty strings of 100 characters or less",
                field=nested_field,
            )

        if not re.match(r"^[a-zA-Z0-9_-]+$", key):
            raise ValidationError(
                "Nested metadata keys must contain only letters, numbers, underscores, and hyphens",
                field=nested_field,
            )

        # Validate value
        if isinstance(value, dict):
            _validate_nested_metadata(value, nested_field, max_depth, current_depth + 1)
        elif isinstance(value, str) and detect_injection_attempt(value):
            raise ValidationError(
                "Nested metadata value contains potentially malicious content",
                field=nested_field,
            )


def validate_request_intent(intent: RequestIntent) -> None:
    """Validate RequestIntent structure and content.

    Args:
        intent: RequestIntent to validate.

    Raises:
        ValidationError: If validation fails.
    """
    if not isinstance(intent, RequestIntent):
        raise ValidationError("Intent must be a RequestIntent instance", field="intent")

    # Validate model field
    if not intent.model or not intent.model.strip():
        raise ValidationError("Model identifier cannot be empty", field="model")

    model = intent.model.strip()
    if len(model) > 200:
        raise ValidationError(
            "Model identifier must be 200 characters or less",
            field="model",
        )

    # Check for injection attempts in model
    if detect_injection_attempt(model):
        raise ValidationError(
            "Model identifier contains potentially malicious content",
            field="model",
        )

    # Validate messages field
    if not intent.messages:
        raise ValidationError("Messages list cannot be empty", field="messages")

    if len(intent.messages) > 1000:
        raise ValidationError(
            "Messages list cannot contain more than 1000 messages",
            field="messages",
        )

    # Validate each message
    for i, message in enumerate(intent.messages):
        if not isinstance(message, Message):
            raise ValidationError(
                f"Message at index {i} must be a Message instance",
                field=f"messages[{i}]",
            )

        # Validate message content length
        if isinstance(message.content, str) and len(message.content) > 1000000:  # 1MB limit
            raise ValidationError(
                f"Message content at index {i} exceeds maximum length",
                field=f"messages[{i}].content",
            )

        # Check for injection attempts in message content
        if isinstance(message.content, str) and detect_injection_attempt(message.content):
            raise ValidationError(
                f"Message content at index {i} contains potentially malicious content",
                field=f"messages[{i}].content",
            )

    # Validate parameters field
    if intent.parameters:
        if not isinstance(intent.parameters, dict):
            raise ValidationError("Parameters must be a dictionary", field="parameters")

        # Validate parameter keys and values
        for key, value in intent.parameters.items():
            param_field = f"parameters.{key}"

            # Validate key
            if not isinstance(key, str):
                raise ValidationError(
                    "Parameter keys must be strings",
                    field=param_field,
                )

            if detect_injection_attempt(key):
                raise ValidationError(
                    "Parameter key contains potentially malicious content",
                    field=param_field,
                )

            # Validate value types
            if not isinstance(value, str | int | float | bool | list | type(None)):
                raise ValidationError(
                    "Parameter values must be primitive types or lists",
                    field=param_field,
                )

            # Check string values for injection attempts
            if isinstance(value, str) and detect_injection_attempt(value):
                raise ValidationError(
                    "Parameter value contains potentially malicious content",
                    field=param_field,
                )

            # Validate numeric ranges
            if isinstance(value, int | float):
                if key == "temperature" and (value < 0.0 or value > 2.0):
                    raise ValidationError(
                        "Temperature must be between 0.0 and 2.0",
                        field=param_field,
                    )
                if key == "max_tokens" and (
                    not isinstance(value, int) or value < 1 or value > 1000000
                ):
                    raise ValidationError(
                        "max_tokens must be a positive integer not exceeding 1000000",
                        field=param_field,
                    )
                if key == "top_p" and (value < 0.0 or value > 1.0):
                    raise ValidationError(
                        "top_p must be between 0.0 and 1.0",
                        field=param_field,
                    )
