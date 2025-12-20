"""Configuration settings using pydantic-settings."""

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RouterSettings(BaseSettings):
    """Configuration settings for ApiKeyRouter.

    Settings can be loaded from environment variables or passed as a dictionary.
    Environment variables should be prefixed with 'APIKEYROUTER_' (e.g., APIKEYROUTER_MAX_DECISIONS=1000).

    Example:
        ```python
        # From environment variables
        settings = RouterSettings()

        # From dictionary
        settings = RouterSettings(max_decisions=500)

        # From environment with prefix
        # Set APIKEYROUTER_MAX_DECISIONS=500
        settings = RouterSettings()
        ```
    """

    model_config = SettingsConfigDict(
        env_prefix="APIKEYROUTER_",
        case_sensitive=False,
        extra="ignore",
    )

    # StateStore configuration
    max_decisions: int = Field(
        default=1000,
        description="Maximum number of routing decisions to store in StateStore",
    )
    max_transitions: int = Field(
        default=1000,
        description="Maximum number of state transitions to store in StateStore",
    )

    # KeyManager configuration
    default_cooldown_seconds: int = Field(
        default=60,
        description="Default cooldown period for Throttled state in seconds",
    )

    # QuotaAwarenessEngine configuration
    quota_default_cooldown_seconds: int = Field(
        default=60,
        description="Default cooldown period when retry-after is missing",
    )

    # Observability configuration
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "RouterSettings":
        """Create settings from a dictionary.

        Args:
            config: Dictionary with configuration values.

        Returns:
            RouterSettings instance.
        """
        return cls(**config)




