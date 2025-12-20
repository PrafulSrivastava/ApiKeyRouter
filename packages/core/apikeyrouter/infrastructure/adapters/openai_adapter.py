"""OpenAI provider adapter implementation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.models.api_key import APIKey
from apikeyrouter.domain.models.cost_estimate import CostEstimate
from apikeyrouter.domain.models.health_state import HealthState, HealthStatus
from apikeyrouter.domain.models.request_intent import Message, RequestIntent
from apikeyrouter.domain.models.system_error import ErrorCategory, SystemError
from apikeyrouter.domain.models.system_response import (
    ResponseMetadata,
    SystemResponse,
    TokenUsage,
)
from apikeyrouter.infrastructure.utils.encryption import (
    EncryptionError,
    decrypt_key_material,
)


class OpenAIAdapter(ProviderAdapter):
    """OpenAI provider adapter implementation.

    Handles communication with OpenAI's API, converting system-defined
    RequestIntent to OpenAI format and normalizing responses to SystemResponse.

    Example:
        ```python
        adapter = OpenAIAdapter()
        intent = RequestIntent(
            model="gpt-4",
            messages=[Message(role="user", content="Hello!")]
        )
        key = APIKey(id="key-1", key_material="encrypted_key", ...)
        response = await adapter.execute_request(intent, key)
        ```
    """

    BASE_URL = "https://api.openai.com/v1"
    """OpenAI API base URL."""

    TIMEOUT = 30.0
    """Request timeout in seconds."""

    HEALTH_CHECK_TIMEOUT = 5.0
    """Health check request timeout in seconds (shorter than normal)."""

    HEALTH_CHECK_TTL = 30.0
    """Health status cache TTL in seconds."""

    # OpenAI pricing per 1K tokens (as of 2024, approximate - should be updated from official pricing)
    # Format: {model_name: {"input": price_per_1k, "output": price_per_1k}}
    PRICING: dict[str, dict[str, Decimal]] = {
        "gpt-4": {
            "input": Decimal("0.03"),
            "output": Decimal("0.06"),
        },
        "gpt-4-turbo": {
            "input": Decimal("0.01"),
            "output": Decimal("0.03"),
        },
        "gpt-4-turbo-preview": {
            "input": Decimal("0.01"),
            "output": Decimal("0.03"),
        },
        "gpt-4-0125-preview": {
            "input": Decimal("0.01"),
            "output": Decimal("0.03"),
        },
        "gpt-4-1106-preview": {
            "input": Decimal("0.01"),
            "output": Decimal("0.03"),
        },
        "gpt-3.5-turbo": {
            "input": Decimal("0.0015"),
            "output": Decimal("0.002"),
        },
        "gpt-3.5-turbo-0125": {
            "input": Decimal("0.0005"),
            "output": Decimal("0.0015"),
        },
        "gpt-3.5-turbo-1106": {
            "input": Decimal("0.001"),
            "output": Decimal("0.002"),
        },
    }
    """OpenAI model pricing per 1K tokens (USD)."""

    DEFAULT_OUTPUT_TOKENS = 500
    """Default output token estimate when max_tokens not specified."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        health_check_ttl: float | None = None,
    ) -> None:
        """Initialize OpenAI adapter.

        Args:
            base_url: Optional base URL override (for testing).
            timeout: Optional timeout override (for testing).
            health_check_ttl: Optional health check cache TTL override (for testing).
        """
        self.base_url = base_url or self.BASE_URL
        self.timeout = timeout or self.TIMEOUT
        self.health_check_ttl = health_check_ttl or self.HEALTH_CHECK_TTL
        self._health_cache: dict[str, tuple[HealthState, float]] = {}
        """Health status cache: {cache_key: (HealthState, timestamp)}"""

    async def execute_request(
        self,
        intent: RequestIntent,
        key: APIKey,
    ) -> SystemResponse:
        """Execute request with OpenAI API.

        Args:
            intent: Request intent in system terms.
            key: API key to use for authentication.

        Returns:
            SystemResponse: Normalized response in system format.

        Raises:
            SystemError: If request fails (authentication, rate limit, etc.).
        """
        # Decrypt API key material
        try:
            api_key = decrypt_key_material(key.key_material)
        except EncryptionError as e:
            raise SystemError(
                category=ErrorCategory.AuthenticationError,
                message=f"Failed to decrypt API key: {e}",
                provider_code="decryption_failed",
                retryable=False,
            ) from e

        # Convert RequestIntent to OpenAI API format
        openai_request = self._convert_to_openai_format(intent)

        # Generate request ID for correlation
        request_id = str(uuid.uuid4())

        # Make HTTP request
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=openai_request,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                response_data = response.json()

        except httpx.HTTPStatusError as e:
            # Map HTTP status errors to SystemError
            raise self.map_error(e) from e
        except httpx.TimeoutException as e:
            raise SystemError(
                category=ErrorCategory.TimeoutError,
                message=f"Request to OpenAI timed out after {self.timeout}s",
                provider_code="timeout",
                retryable=True,
            ) from e
        except httpx.NetworkError as e:
            raise SystemError(
                category=ErrorCategory.NetworkError,
                message=f"Network error connecting to OpenAI: {e}",
                provider_code="network_error",
                retryable=True,
            ) from e
        except Exception as e:
            # Catch any other unexpected errors
            raise SystemError(
                category=ErrorCategory.UnknownError,
                message=f"Unexpected error: {e}",
                provider_code="unknown",
                retryable=False,
            ) from e

        # Store key_id and request_id for normalization
        # We'll need to pass these through the response data or use instance state
        # For now, add them to response_data as metadata
        response_data["_key_id"] = key.id
        response_data["_request_id"] = request_id

        # Normalize response to SystemResponse
        return self.normalize_response(response_data)

    def _convert_to_openai_format(self, intent: RequestIntent) -> dict[str, Any]:
        """Convert RequestIntent to OpenAI API format.

        Args:
            intent: System request intent.

        Returns:
            Dictionary in OpenAI API format.
        """
        # Convert messages
        messages = [
            {
                "role": msg.role,
                "content": msg.content,
                **({k: v for k, v in {"name": msg.name, "function_call": msg.function_call, "tool_calls": msg.tool_calls, "tool_call_id": msg.tool_call_id}.items() if v is not None}),
            }
            for msg in intent.messages
        ]

        # Build OpenAI request
        openai_request: dict[str, Any] = {
            "model": intent.model,
            "messages": messages,
        }

        # Add parameters if present
        if intent.parameters:
            # Map common parameters
            if "temperature" in intent.parameters:
                openai_request["temperature"] = intent.parameters["temperature"]
            if "max_tokens" in intent.parameters:
                openai_request["max_tokens"] = intent.parameters["max_tokens"]
            if "top_p" in intent.parameters:
                openai_request["top_p"] = intent.parameters["top_p"]
            if "stream" in intent.parameters:
                openai_request["stream"] = intent.parameters["stream"]
            # Add any other parameters
            for key, value in intent.parameters.items():
                if key not in ("temperature", "max_tokens", "top_p", "stream"):
                    openai_request[key] = value

        return openai_request

    def normalize_response(
        self,
        provider_response: Any,
    ) -> SystemResponse:
        """Normalize OpenAI response to system format.

        Args:
            provider_response: Raw OpenAI API response (dict or JSON).

        Returns:
            SystemResponse: Normalized response in system format.
        """
        # Handle dict or parse JSON if needed
        if isinstance(provider_response, str):
            import json

            response_data = json.loads(provider_response)
        else:
            response_data = provider_response

        # Extract content from OpenAI response
        # OpenAI format: {"choices": [{"message": {"content": "..."}}]}
        choices = response_data.get("choices", [])
        if not choices:
            raise SystemError(
                category=ErrorCategory.ProviderError,
                message="OpenAI response has no choices",
                provider_code="no_choices",
                retryable=False,
            )

        first_choice = choices[0]
        message = first_choice.get("message", {})
        content = message.get("content", "")

        # Extract token usage
        usage_data = response_data.get("usage", {})
        tokens_used = TokenUsage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
        )

        # Extract model used
        model_used = response_data.get("model", "unknown")

        # Extract finish reason
        finish_reason = first_choice.get("finish_reason")

        # Extract key_id and request_id from response metadata if present
        key_id = response_data.get("_key_id", "unknown")
        request_id = response_data.get("_request_id", str(uuid.uuid4()))

        # Build ResponseMetadata
        metadata = ResponseMetadata(
            model_used=model_used,
            tokens_used=tokens_used,
            response_time_ms=0,  # Will be populated by caller if available
            provider_id="openai",
            timestamp=datetime.utcnow(),
            finish_reason=finish_reason,
            request_id=request_id,
            additional_metadata={
                "id": response_data.get("id"),
                "object": response_data.get("object"),
                "created": response_data.get("created"),
            },
        )

        # Build SystemResponse
        return SystemResponse(
            content=content,
            metadata=metadata,
            cost=None,  # Will be populated in future story
            key_used=key_id,
            request_id=request_id,
        )

    def map_error(self, provider_error: Exception) -> SystemError:
        """Map OpenAI/provider error to system error category.

        Args:
            provider_error: Exception from provider API or SDK.

        Returns:
            SystemError: Normalized error with appropriate category.
        """
        # Handle httpx.HTTPStatusError
        if isinstance(provider_error, httpx.HTTPStatusError):
            status_code = provider_error.response.status_code
            response = provider_error.response

            # Extract retry-after header if available
            retry_after = self._extract_retry_after(response)

            # Extract error details from response body
            error_details = self._extract_error_details(response)

            # Build base message from error details or default
            error_message = error_details.get("message") or response.text or ""

            # Map status codes to error categories
            if status_code == 401:
                return SystemError(
                    category=ErrorCategory.AuthenticationError,
                    message=error_message or "OpenAI API authentication failed - invalid API key",
                    provider_code=error_details.get("code") or "invalid_api_key",
                    retryable=False,
                    details=error_details,
                    retry_after=retry_after,
                )
            elif status_code == 429:
                return SystemError(
                    category=ErrorCategory.RateLimitError,
                    message=error_message or "OpenAI API rate limit exceeded",
                    provider_code=error_details.get("code") or "rate_limit_exceeded",
                    retryable=True,
                    details=error_details,
                    retry_after=retry_after,
                )
            elif status_code == 400:
                return SystemError(
                    category=ErrorCategory.ValidationError,
                    message=error_message or f"OpenAI API validation error: {response.text}",
                    provider_code=error_details.get("code") or "validation_error",
                    retryable=False,
                    details=error_details,
                    retry_after=retry_after,
                )
            elif 500 <= status_code < 600:
                return SystemError(
                    category=ErrorCategory.ProviderError,
                    message=error_message or f"OpenAI API server error ({status_code})",
                    provider_code=error_details.get("code") or f"server_error_{status_code}",
                    retryable=True,
                    details=error_details,
                    retry_after=retry_after,
                )
            else:
                return SystemError(
                    category=ErrorCategory.ProviderError,
                    message=error_message or f"OpenAI API error ({status_code}): {response.text}",
                    provider_code=error_details.get("code") or f"http_error_{status_code}",
                    retryable=status_code >= 500,
                    details=error_details,
                    retry_after=retry_after,
                )

        # Handle other httpx errors
        if isinstance(provider_error, httpx.TimeoutException):
            return SystemError(
                category=ErrorCategory.TimeoutError,
                message="Request to OpenAI timed out",
                provider_code="timeout",
                retryable=True,
            )

        if isinstance(provider_error, httpx.NetworkError):
            return SystemError(
                category=ErrorCategory.NetworkError,
                message=f"Network error connecting to OpenAI: {provider_error}",
                provider_code="network_error",
                retryable=True,
            )

        # Unknown error
        return SystemError(
            category=ErrorCategory.UnknownError,
            message=f"Unknown error from OpenAI: {provider_error}",
            provider_code="unknown",
            retryable=False,
            details={"original_error": str(provider_error)},
        )

    def _extract_retry_after(self, response: httpx.Response) -> int | None:
        """Extract retry-after value from response headers.

        Args:
            response: HTTP response object.

        Returns:
            Retry after seconds, or None if not present.
        """
        retry_after_header = response.headers.get("retry-after")
        if not retry_after_header:
            return None

        try:
            # Retry-After can be either seconds (integer) or HTTP date
            # Try parsing as integer first
            return int(retry_after_header)
        except ValueError:
            # If not an integer, try parsing as HTTP date
            try:
                from email.utils import parsedate_to_datetime

                retry_date = parsedate_to_datetime(retry_after_header)
                if retry_date:
                    from datetime import datetime

                    now = datetime.now(UTC)
                    delta = retry_date - now
                    return int(delta.total_seconds()) if delta.total_seconds() > 0 else None
            except (ValueError, TypeError):
                pass

        return None

    def _extract_error_details(self, response: httpx.Response) -> dict[str, Any]:
        """Extract error details from response body.

        Args:
            response: HTTP response object.

        Returns:
            Dictionary with error details (message, code, type, etc.).
        """
        details: dict[str, Any] = {}

        try:
            # Try to parse JSON response body
            error_data = response.json()
            if isinstance(error_data, dict):
                # OpenAI error format: {"error": {"message": "...", "type": "...", "code": "..."}}
                if "error" in error_data and isinstance(error_data["error"], dict):
                    error_obj = error_data["error"]
                    details["message"] = error_obj.get("message")
                    details["type"] = error_obj.get("type")
                    details["code"] = error_obj.get("code")
                    details["param"] = error_obj.get("param")
                else:
                    # Fallback: use top-level fields
                    details["message"] = error_data.get("message")
                    details["code"] = error_data.get("code")
                    details["type"] = error_data.get("type")
        except (ValueError, TypeError):
            # If JSON parsing fails, use response text
            if response.text:
                details["message"] = response.text

        return details

    def get_capabilities(self) -> Any:  # type: ignore[override]
        """Declare what OpenAI supports.

        Returns:
            ProviderCapabilities: Capability declaration (placeholder for now).
        """
        # TODO: Implement ProviderCapabilities model in future story
        return {
            "supports_streaming": True,
            "supports_tools": True,
            "supports_images": False,
            "max_tokens": None,
            "rate_limit_per_minute": None,
            "custom_capabilities": {},
        }

    async def estimate_cost(self, request_intent: RequestIntent) -> CostEstimate:
        """Estimate cost for a request.

        Args:
            request_intent: Request intent containing model, messages, and parameters.

        Returns:
            CostEstimate: Cost estimate with amount, confidence, and token estimates.

        Raises:
            SystemError: If model pricing is not available.
        """
        model = request_intent.model

        # Get pricing for model
        pricing = self.PRICING.get(model)
        if not pricing:
            # Try to find a base model match (e.g., "gpt-4-0613" -> "gpt-4")
            base_model = model.split("-")[0] + "-" + model.split("-")[1] if "-" in model else model
            pricing = self.PRICING.get(base_model)

        if not pricing:
            raise SystemError(
                category=ErrorCategory.ValidationError,
                message=f"Unknown model for cost estimation: {model}",
                provider_code="unknown_model",
                retryable=False,
            )

        # Estimate input tokens
        input_tokens = self._estimate_input_tokens(request_intent.messages)

        # Estimate output tokens
        output_tokens = self._estimate_output_tokens(request_intent)

        # Calculate costs
        input_price_per_1k = pricing["input"]
        output_price_per_1k = pricing["output"]

        input_cost = (Decimal(input_tokens) / Decimal(1000)) * input_price_per_1k
        output_cost = (Decimal(output_tokens) / Decimal(1000)) * output_price_per_1k
        total_cost = input_cost + output_cost

        # Determine confidence level
        # Medium confidence for token estimates, higher if max_tokens is specified
        confidence = 0.7 if request_intent.get_max_tokens() is None else 0.85

        return CostEstimate(
            amount=total_cost,
            currency="USD",
            confidence=confidence,
            estimation_method="token_count_approximation",
            input_tokens_estimate=input_tokens,
            output_tokens_estimate=output_tokens,
            breakdown={
                "input_cost": input_cost,
                "output_cost": output_cost,
            },
        )

    def _estimate_input_tokens(self, messages: list[Message]) -> int:
        """Estimate input tokens from messages.

        Uses approximate token counting: ~4 characters per token for English text.
        Also accounts for message overhead (role, formatting, etc.).

        Args:
            messages: List of messages in the conversation.

        Returns:
            Estimated number of input tokens.
        """
        total_chars = 0
        for msg in messages:
            # Count content characters
            total_chars += len(msg.content or "")
            # Add overhead for role and formatting (~10 tokens per message)
            total_chars += 40  # Approximate overhead

        # Approximate: 4 characters ≈ 1 token for English text
        # Add base overhead for API structure
        estimated_tokens = (total_chars // 4) + 3  # +3 for base API overhead

        return max(estimated_tokens, 1)  # At least 1 token

    def _estimate_output_tokens(self, intent: RequestIntent) -> int:
        """Estimate output tokens from request intent.

        Args:
            intent: Request intent with parameters.

        Returns:
            Estimated number of output tokens.
        """
        max_tokens = intent.get_max_tokens()
        if max_tokens is not None:
            # If max_tokens specified, estimate as 80% of max (typical usage)
            return int(max_tokens * 0.8)

        # Default estimate when max_tokens not specified
        return self.DEFAULT_OUTPUT_TOKENS

    async def get_health(self) -> HealthState:
        """Get OpenAI health status.

        Performs a lightweight health check by making a request to OpenAI's
        models endpoint. Results are cached for 30 seconds to avoid excessive
        API calls.

        Returns:
            HealthState: Health state with status, last_check, and latency.
        """
        import time

        cache_key = "openai_health"
        current_time = time.time()

        # Check cache first
        if cache_key in self._health_cache:
            cached_state, cached_timestamp = self._health_cache[cache_key]
            if current_time - cached_timestamp < self.health_check_ttl:
                # Return cached value
                return cached_state

        # Perform health check
        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=self.HEALTH_CHECK_TIMEOUT) as client:
                # Use lightweight models endpoint for health check
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Content-Type": "application/json"},
                )

                latency_ms = int((time.time() - start_time) * 1000)

                # Determine health status based on response
                if response.status_code == 200:
                    status = HealthStatus.Healthy
                elif response.status_code == 429:
                    status = HealthStatus.Degraded
                elif response.status_code >= 500:
                    status = HealthStatus.Down
                else:
                    # Other 4xx errors - treat as degraded
                    status = HealthStatus.Degraded

                health_state = HealthState(
                    status=status,
                    last_check=datetime.utcnow(),
                    latency_ms=latency_ms,
                    details={
                        "status_code": response.status_code,
                        "endpoint": "/models",
                    },
                )

        except httpx.TimeoutException:
            # Timeout - provider is down
            health_state = HealthState(
                status=HealthStatus.Down,
                last_check=datetime.utcnow(),
                latency_ms=None,
                details={"error": "Health check timeout"},
            )

        except httpx.NetworkError:
            # Network error - provider is down
            health_state = HealthState(
                status=HealthStatus.Down,
                last_check=datetime.utcnow(),
                latency_ms=None,
                details={"error": "Network error during health check"},
            )

        except Exception as e:
            # Unknown error - provider is down
            health_state = HealthState(
                status=HealthStatus.Down,
                last_check=datetime.utcnow(),
                latency_ms=None,
                details={"error": f"Unexpected error: {e}"},
            )

        # Update cache
        self._health_cache[cache_key] = (health_state, current_time)

        return health_state

