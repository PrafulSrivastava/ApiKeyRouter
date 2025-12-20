"""QuotaAwarenessEngine component for capacity tracking."""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any

from apikeyrouter.domain.interfaces.observability_manager import (
    ObservabilityManager,
)
from apikeyrouter.domain.interfaces.state_store import StateQuery, StateStore, StateStoreError
from apikeyrouter.domain.models.quota_state import (
    CapacityEstimate,
    CapacityState,
    CapacityUnit,
    ExhaustionPrediction,
    QuotaState,
    TimeWindow,
    UncertaintyLevel,
    UsageRate,
)
from apikeyrouter.domain.models.routing_decision import RoutingDecision


class QuotaAwarenessEngine:
    """Implements forward-looking quota awareness and capacity tracking.

    Tracks remaining capacity over time with multi-state model and updates
    capacity after each request. Handles time window resets automatically.
    """

    # Capacity state thresholds (as percentages)
    ABUNDANT_THRESHOLD = 0.80  # >80% remaining
    CONSTRAINED_THRESHOLD = 0.50  # 50-80% remaining
    CRITICAL_THRESHOLD = 0.20  # 20-50% remaining
    # <20% or hard limit hit = Exhausted

    def __init__(
        self,
        state_store: StateStore,
        observability_manager: ObservabilityManager,
        key_manager: Any | None = None,
        default_cooldown_seconds: int = 60,
        prediction_cache_ttl_seconds: int = 300,
    ) -> None:
        """Initialize QuotaAwarenessEngine with dependencies.

        Args:
            state_store: StateStore implementation for quota state persistence.
            observability_manager: ObservabilityManager for events and logging.
            key_manager: Optional KeyManager for coordinating key state updates.
            default_cooldown_seconds: Default cooldown period when retry-after is missing.
            prediction_cache_ttl_seconds: TTL for exhaustion prediction cache in seconds (default: 300 = 5 minutes).
        """
        self._state_store = state_store
        self._observability = observability_manager
        self._key_manager = key_manager
        self._default_cooldown_seconds = default_cooldown_seconds
        self._prediction_cache_ttl_seconds = prediction_cache_ttl_seconds
        # Locks for thread-safe initialization (key_id -> Lock)
        self._init_locks: dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()  # Lock for managing init_locks dict
        # Prediction cache: key_id -> (prediction, cached_at)
        self._prediction_cache: dict[str, tuple[ExhaustionPrediction, datetime]] = {}

    async def update_capacity(
        self,
        key_id: str,
        consumed: int,
        cost_estimate: dict[str, Any] | None = None,
        tokens_consumed: int | None = None,
    ) -> QuotaState:
        """Update capacity after a request has consumed quota.

        Decrements remaining_capacity, increments used_capacity, updates
        capacity_state based on thresholds, and handles time window resets.
        Supports different capacity units (requests, tokens, or mixed).

        Args:
            key_id: The unique identifier of the key.
            consumed: Amount of capacity consumed (in capacity_unit).
                     For Requests unit: number of requests (typically 1).
                     For Tokens unit: number of tokens.
                     For Mixed unit: not used (use tokens_consumed instead).
            cost_estimate: Optional cost estimate for tracking (not yet used).
            tokens_consumed: Optional number of tokens consumed (required for Mixed unit).

        Returns:
            The updated QuotaState.

        Raises:
            ValueError: If tokens_consumed is required but not provided.
            StateStoreError: If save operation fails.
        """
        if consumed < 0:
            raise ValueError("Consumed capacity must be non-negative")
        if tokens_consumed is not None and tokens_consumed < 0:
            raise ValueError("Tokens consumed must be non-negative")

        # Retrieve current quota state from StateStore
        quota_state = await self._state_store.get_quota_state(key_id)

        # Initialize QuotaState if missing
        if quota_state is None:
            quota_state = await self._initialize_quota_state(key_id)

        # Check for time window reset before updating
        now = datetime.utcnow()
        if now >= quota_state.reset_at:
            quota_state = await self._handle_reset(quota_state, now)

        # Update capacity based on capacity_unit
        if quota_state.capacity_unit == CapacityUnit.Requests:
            # For Requests unit: decrement by consumed (typically 1)
            if quota_state.remaining_capacity.value is not None:
                new_remaining = max(0, quota_state.remaining_capacity.value - consumed)
                quota_state.remaining_capacity.value = new_remaining
            quota_state.used_capacity += consumed

        elif quota_state.capacity_unit == CapacityUnit.Tokens:
            # For Tokens unit: decrement by tokens_consumed if provided, otherwise by consumed
            tokens_to_consume = tokens_consumed if tokens_consumed is not None else consumed
            if quota_state.remaining_capacity.value is not None:
                new_remaining = max(0, quota_state.remaining_capacity.value - tokens_to_consume)
                quota_state.remaining_capacity.value = new_remaining
            quota_state.used_capacity += tokens_to_consume
            quota_state.used_tokens += tokens_to_consume

        elif quota_state.capacity_unit == CapacityUnit.Mixed:
            # For Mixed unit: handle both requests and tokens
            if tokens_consumed is None:
                raise ValueError("tokens_consumed is required when capacity_unit is Mixed")

            # Update request capacity (consumed is number of requests, typically 1)
            if quota_state.remaining_capacity.value is not None:
                new_remaining = max(0, quota_state.remaining_capacity.value - consumed)
                quota_state.remaining_capacity.value = new_remaining
            quota_state.used_capacity += consumed
            quota_state.used_requests += consumed

            # Update token capacity
            if quota_state.remaining_tokens is not None and quota_state.remaining_tokens.value is not None:
                new_remaining_tokens = max(0, quota_state.remaining_tokens.value - tokens_consumed)
                quota_state.remaining_tokens.value = new_remaining_tokens
            quota_state.used_tokens += tokens_consumed

        else:
            # Fallback to old behavior for backward compatibility
            if quota_state.remaining_capacity.value is not None:
                new_remaining = max(0, quota_state.remaining_capacity.value - consumed)
                quota_state.remaining_capacity.value = new_remaining
            quota_state.used_capacity += consumed

        # Update updated_at timestamp
        quota_state.updated_at = now

        # Get exhaustion prediction (with caching)
        prediction = await self._get_exhaustion_prediction(key_id)

        # Store previous capacity_state for transition tracking
        previous_capacity_state = quota_state.capacity_state

        # Calculate and update capacity_state based on thresholds and prediction
        quota_state.capacity_state = self._calculate_capacity_state(quota_state, prediction)

        # Create state transition if capacity_state changed
        if previous_capacity_state != quota_state.capacity_state:
            await self._create_capacity_state_transition(
                key_id, previous_capacity_state, quota_state.capacity_state, prediction
            )

        # Save updated QuotaState to StateStore
        try:
            await self._state_store.save_quota_state(quota_state)
        except StateStoreError as e:
            await self._observability.log(
                level="ERROR",
                message=f"Failed to save quota state for key {key_id}: {e}",
                context={"key_id": key_id, "consumed": consumed},
            )
            raise

        # Emit capacity_updated event
        try:
            await self._observability.emit_event(
                event_type="capacity_updated",
                payload={
                    "key_id": key_id,
                    "consumed": consumed,
                    "remaining_capacity": quota_state.remaining_capacity.value,
                    "used_capacity": quota_state.used_capacity,
                    "capacity_state": quota_state.capacity_state.value,
                },
                metadata={
                    "updated_at": quota_state.updated_at.isoformat(),
                },
            )
        except Exception as e:
            # Log error but don't fail update if event emission fails
            await self._observability.log(
                level="WARNING",
                message=f"Failed to emit capacity_updated event: {e}",
                context={"key_id": key_id},
            )

        return quota_state

    async def _initialize_quota_state(self, key_id: str) -> QuotaState:
        """Initialize a new QuotaState for a key.

        Creates a default QuotaState with unknown capacity and daily reset window.
        Defaults to Requests unit for backward compatibility.

        Args:
            key_id: The unique identifier of the key.

        Returns:
            A new QuotaState instance.
        """
        now = datetime.utcnow()
        reset_at = TimeWindow.Daily.calculate_next_reset(now)

        quota_state = QuotaState(
            id=str(uuid.uuid4()),
            key_id=key_id,
            capacity_state=CapacityState.Abundant,
            capacity_unit=CapacityUnit.Requests,
            remaining_capacity=CapacityEstimate(
                value=None,
                confidence=0.0,
                estimation_method="unknown",
            ),
            total_capacity=None,
            used_capacity=0,
            used_tokens=0,
            used_requests=0,
            time_window=TimeWindow.Daily,
            reset_at=reset_at,
            updated_at=now,
        )

        # Save initial quota state
        await self._state_store.save_quota_state(quota_state)

        await self._observability.log(
            level="INFO",
            message=f"Initialized quota state for key {key_id}",
            context={"key_id": key_id, "quota_state_id": quota_state.id},
        )

        return quota_state

    def _calculate_capacity_state(
        self, quota_state: QuotaState, prediction: ExhaustionPrediction | None = None
    ) -> CapacityState:
        """Calculate capacity_state based on remaining capacity thresholds and exhaustion prediction.

        Considers both remaining capacity percentage and exhaustion prediction to determine
        the most appropriate capacity state. Prediction takes precedence when available.

        Args:
            quota_state: The QuotaState to calculate state for.
            prediction: Optional ExhaustionPrediction to consider.

        Returns:
            The calculated CapacityState.
        """
        # First, check if we have an exhaustion prediction
        if prediction is not None:
            # Calculate hours until exhaustion
            now = datetime.utcnow()
            time_until_exhaustion = prediction.predicted_exhaustion_at - now
            hours_until_exhaustion = time_until_exhaustion.total_seconds() / 3600.0

            # Apply prediction-based thresholds
            if hours_until_exhaustion < 4.0:
                # Exhaustion < 4 hours → Critical
                return CapacityState.Critical
            elif hours_until_exhaustion < 24.0:
                # Exhaustion < 24 hours → Constrained
                return CapacityState.Constrained
            else:
                # Exhaustion > 24 hours → Abundant
                return CapacityState.Abundant

        # If no prediction available, fall back to capacity percentage-based calculation
        # If total_capacity is unknown, we can't calculate percentage
        # Default to Abundant if we have remaining capacity, otherwise Exhausted
        if quota_state.total_capacity is None:
            if (
                quota_state.remaining_capacity.value is not None
                and quota_state.remaining_capacity.value > 0
            ):
                return CapacityState.Abundant
            elif (
                quota_state.remaining_capacity.value is not None
                and quota_state.remaining_capacity.value == 0
            ):
                return CapacityState.Exhausted
            else:
                # Unknown capacity - default to Abundant (optimistic)
                return CapacityState.Abundant

        # Calculate percentage: remaining / total
        if quota_state.remaining_capacity.value is None:
            # If we don't know remaining but know total, default to Abundant
            return CapacityState.Abundant

        remaining = quota_state.remaining_capacity.value
        total = quota_state.total_capacity

        if total == 0:
            return CapacityState.Exhausted

        percentage = remaining / total

        # Update capacity_state based on thresholds
        if percentage > self.ABUNDANT_THRESHOLD:
            return CapacityState.Abundant
        elif percentage > self.CONSTRAINED_THRESHOLD:
            return CapacityState.Constrained
        elif percentage > self.CRITICAL_THRESHOLD:
            return CapacityState.Critical
        else:
            # <20% or hard limit hit
            return CapacityState.Exhausted

    async def _handle_reset(
        self, quota_state: QuotaState, current_time: datetime
    ) -> QuotaState:
        """Handle quota reset when time window boundary is reached.

        Args:
            quota_state: The current QuotaState.
            current_time: The current datetime.

        Returns:
            The updated QuotaState after reset.
        """
        # Reset remaining_capacity to total_capacity
        if quota_state.total_capacity is not None:
            quota_state.remaining_capacity = CapacityEstimate(
                value=quota_state.total_capacity,
                confidence=1.0,
                estimation_method="reset",
            )
        else:
            # If total_capacity is unknown, keep remaining_capacity as is
            # but update confidence
            quota_state.remaining_capacity.confidence = 0.0
            quota_state.remaining_capacity.estimation_method = "unknown_after_reset"

        # Reset used_capacity to 0
        quota_state.used_capacity = 0

        # Handle Mixed unit: reset token capacity as well
        if quota_state.capacity_unit == CapacityUnit.Mixed:
            if quota_state.total_tokens is not None:
                quota_state.remaining_tokens = CapacityEstimate(
                    value=quota_state.total_tokens,
                    confidence=1.0,
                    estimation_method="reset",
                )
            else:
                if quota_state.remaining_tokens is not None:
                    quota_state.remaining_tokens.confidence = 0.0
                    quota_state.remaining_tokens.estimation_method = "unknown_after_reset"
            quota_state.used_tokens = 0
            quota_state.used_requests = 0
        elif quota_state.capacity_unit == CapacityUnit.Tokens:
            quota_state.used_tokens = 0

        # Update capacity_state to Abundant
        quota_state.capacity_state = CapacityState.Abundant

        # Calculate next reset_at based on time_window
        if quota_state.time_window == TimeWindow.Custom:
            # For Custom, reset_at should be set externally, don't change it
            pass
        else:
            quota_state.reset_at = quota_state.time_window.calculate_next_reset(
                current_time
            )

        # Update updated_at
        quota_state.updated_at = current_time

        # Emit quota_reset event
        try:
            await self._observability.emit_event(
                event_type="quota_reset",
                payload={
                    "key_id": quota_state.key_id,
                    "quota_state_id": quota_state.id,
                    "time_window": quota_state.time_window.value,
                    "next_reset_at": quota_state.reset_at.isoformat(),
                    "reset_capacity": quota_state.remaining_capacity.value,
                },
                metadata={
                    "reset_timestamp": current_time.isoformat(),
                },
            )
        except Exception as e:
            # Log error but don't fail reset if event emission fails
            await self._observability.log(
                level="WARNING",
                message=f"Failed to emit quota_reset event: {e}",
                context={"key_id": quota_state.key_id},
            )

        return quota_state

    async def get_quota_state(self, key_id: str) -> QuotaState:
        """Retrieve quota state for a key.

        Queries StateStore for QuotaState. If not found, initializes a new
        QuotaState with default values (Abundant state, Daily time window).
        Uses async locks to ensure thread-safe initialization for concurrent queries.

        Args:
            key_id: The unique identifier of the key.

        Returns:
            The QuotaState (initialized if missing).

        Raises:
            StateStoreError: If retrieval or save operation fails.
        """
        # Fast path: try to get existing quota state
        quota_state = await self._state_store.get_quota_state(key_id)
        if quota_state is not None:
            return quota_state

        # Slow path: initialize if missing (with thread-safety)
        # Get or create lock for this key_id
        async with self._locks_lock:
            if key_id not in self._init_locks:
                self._init_locks[key_id] = asyncio.Lock()
            init_lock = self._init_locks[key_id]

        # Use lock to prevent race conditions during initialization
        async with init_lock:
            # Double-check: another coroutine might have initialized it
            quota_state = await self._state_store.get_quota_state(key_id)
            if quota_state is not None:
                return quota_state

            # Initialize new QuotaState
            quota_state = await self._initialize_quota_state(key_id)
            return quota_state

    async def handle_quota_response(
        self,
        key_id: str,
        response: Any,
        provider_id: str | None = None,
    ) -> QuotaState:
        """Handle 429 response as quota exhaustion.

        Detects 429 status code, updates quota state to Exhausted, extracts
        retry-after header, and coordinates with KeyManager to update key state.

        Args:
            key_id: The unique identifier of the key.
            response: HTTP response object (dict, httpx.Response, or object with status_code/headers).
            provider_id: Optional provider ID for event metadata.

        Returns:
            The updated QuotaState.

        Raises:
            ValueError: If response doesn't have 429 status code.
            StateStoreError: If save operation fails.
        """
        # Extract status code from response (handle multiple formats)
        status_code = self._extract_status_code(response)
        if status_code != 429:
            raise ValueError(f"Expected 429 status code, got {status_code}")

        # Extract retry-after header
        retry_after_seconds = await self._extract_retry_after(response)

        # Retrieve or initialize QuotaState
        quota_state = await self.get_quota_state(key_id)

        # Update quota state to Exhausted
        now = datetime.utcnow()
        quota_state.capacity_state = CapacityState.Exhausted

        # Set remaining_capacity to 0 or minimum
        if quota_state.remaining_capacity.value is not None:
            quota_state.remaining_capacity.value = 0
        quota_state.remaining_capacity.confidence = 1.0
        quota_state.remaining_capacity.estimation_method = "429_response"

        # Update updated_at timestamp
        quota_state.updated_at = now

        # Save updated QuotaState to StateStore
        try:
            await self._state_store.save_quota_state(quota_state)
        except StateStoreError as e:
            await self._observability.log(
                level="ERROR",
                message=f"Failed to save quota state after 429: {e}",
                context={"key_id": key_id, "status_code": 429},
            )
            raise

        # Update key state via KeyManager if available
        if self._key_manager is not None:
            try:
                from apikeyrouter.domain.models.api_key import KeyState

                # Calculate cooldown_until
                cooldown_until = now + timedelta(seconds=retry_after_seconds)

                # Update key state to Throttled with cooldown
                await self._key_manager.update_key_state(
                    key_id=key_id,
                    new_state=KeyState.Throttled,
                    reason="quota_exhausted_429",
                    cooldown_seconds=retry_after_seconds,
                    context={
                        "retry_after_seconds": retry_after_seconds,
                        "cooldown_until": cooldown_until.isoformat(),
                    },
                )
            except Exception as e:
                # Log error but don't fail quota state update
                await self._observability.log(
                    level="WARNING",
                    message=f"Failed to update key state after 429: {e}",
                    context={"key_id": key_id},
                )

        # Emit quota_exhausted event
        try:
            await self._observability.emit_event(
                event_type="quota_exhausted",
                payload={
                    "key_id": key_id,
                    "provider_id": provider_id,
                    "status_code": 429,
                    "retry_after_seconds": retry_after_seconds,
                    "capacity_state": quota_state.capacity_state.value,
                },
                metadata={
                    "exhausted_at": now.isoformat(),
                    "cooldown_until": (now + timedelta(seconds=retry_after_seconds)).isoformat(),
                },
            )
        except Exception as e:
            # Log error but don't fail quota state update if event emission fails
            await self._observability.log(
                level="WARNING",
                message=f"Failed to emit quota_exhausted event: {e}",
                context={"key_id": key_id},
            )

        return quota_state

    def _extract_status_code(self, response: Any) -> int:
        """Extract status code from response (handles multiple formats).

        Args:
            response: Response object (dict, httpx.Response, or object with status_code).

        Returns:
            HTTP status code.

        Raises:
            ValueError: If status code cannot be extracted.
        """
        # Handle dict-like response
        if isinstance(response, dict):
            if "status_code" in response:
                return int(response["status_code"])
            if "status" in response:
                return int(response["status"])
            raise ValueError("Response dict missing status_code or status field")

        # Handle object with status_code attribute
        if hasattr(response, "status_code"):
            return int(response.status_code)

        # Handle object with status attribute
        if hasattr(response, "status"):
            return int(response.status)

        raise ValueError(f"Cannot extract status code from response type: {type(response)}")

    async def _extract_retry_after(self, response: Any) -> int:
        """Extract retry-after header from response.

        Args:
            response: Response object (dict, httpx.Response, or object with headers).

        Returns:
            Retry-after value in seconds. Returns default if missing.
        """
        headers = self._extract_headers(response)

        # Look for retry-after header (case-insensitive)
        retry_after_value = None
        for key, value in headers.items():
            if key.lower() == "retry-after":
                retry_after_value = value
                break

        if retry_after_value is None:
            # No retry-after header, use default
            return self._default_cooldown_seconds

        # Parse retry-after value
        try:
            # Try parsing as integer (seconds)
            return int(retry_after_value)
        except (ValueError, TypeError):
            # Try parsing as HTTP date (RFC 7231)
            try:
                from email.utils import parsedate_to_datetime

                retry_date = parsedate_to_datetime(retry_after_value)
                now = datetime.utcnow()
                if retry_date.tzinfo is None:
                    # Assume UTC if no timezone
                    retry_date = retry_date.replace(tzinfo=None)
                else:
                    # Convert to UTC naive
                    retry_date = retry_date.astimezone().replace(tzinfo=None)

                delta = retry_date - now
                return max(0, int(delta.total_seconds()))
            except (ValueError, TypeError):
                # If parsing fails, use default
                await self._observability.log(
                    level="WARNING",
                    message=f"Failed to parse retry-after header: {retry_after_value}",
                    context={"retry_after_value": str(retry_after_value)},
                )
                return self._default_cooldown_seconds

    def _extract_headers(self, response: Any) -> dict[str, str]:
        """Extract headers from response (handles multiple formats).

        Args:
            response: Response object (dict, httpx.Response, or object with headers).

        Returns:
            Dictionary of headers (lowercase keys).
        """
        # Handle dict-like response
        if isinstance(response, dict):
            if "headers" in response:
                headers = response["headers"]
            elif "header" in response:
                headers = response["header"]
            else:
                return {}
        # Handle object with headers attribute
        elif hasattr(response, "headers"):
            headers = response.headers
        else:
            return {}

        # Normalize headers to dict with lowercase keys
        if isinstance(headers, dict):
            return {k.lower(): str(v) for k, v in headers.items()}
        elif hasattr(headers, "get"):
            # httpx.Headers-like object
            return {k.lower(): str(v) for k, v in headers.items()}
        else:
            return {}

    async def calculate_usage_rate(
        self, key_id: str, window_hours: float = 1.0, min_data_points: int = 3
    ) -> UsageRate | None:
        """Calculate usage rate for a key over a time window.

        Queries routing decisions from StateStore for the specified time window,
        counts requests, and calculates rates. Handles insufficient data gracefully
        by returning None if minimum data points are not available.

        Args:
            key_id: The unique identifier of the key to calculate usage rate for.
            window_hours: Time window in hours to analyze (default: 1.0).
            min_data_points: Minimum number of requests required for calculation (default: 3).

        Returns:
            UsageRate object with calculated rates, or None if insufficient data.

        Raises:
            StateStoreError: If query operation fails.
            ValueError: If window_hours is not positive.
        """
        if window_hours <= 0:
            raise ValueError("window_hours must be greater than 0")

        # Calculate time window boundaries
        now = datetime.utcnow()
        window_start = now - timedelta(hours=window_hours)

        # Query routing decisions for this key in the time window
        query = StateQuery(
            entity_type="RoutingDecision",
            key_id=key_id,
            timestamp_from=window_start,
            timestamp_to=now,
        )

        try:
            results = await self._state_store.query_state(query)
        except StateStoreError as e:
            await self._observability.log(
                level="ERROR",
                message=f"Failed to query routing decisions for usage rate: {e}",
                context={"key_id": key_id, "window_hours": window_hours},
            )
            raise

        # Filter to RoutingDecision objects and ensure they match the key
        routing_decisions: list[RoutingDecision] = []
        for result in results:
            if isinstance(result, RoutingDecision) and result.selected_key_id == key_id:
                routing_decisions.append(result)

        # Check if we have sufficient data
        request_count = len(routing_decisions)
        if request_count < min_data_points:
            # Try using a longer time window (up to 24 hours)
            if window_hours < 24.0:
                extended_window = min(24.0, window_hours * 2)
                await self._observability.log(
                    level="INFO",
                    message=f"Insufficient data for {key_id}, trying extended window",
                    context={
                        "key_id": key_id,
                        "request_count": request_count,
                        "min_data_points": min_data_points,
                        "original_window": window_hours,
                        "extended_window": extended_window,
                    },
                )
                return await self.calculate_usage_rate(
                    key_id, window_hours=extended_window, min_data_points=min_data_points
                )
            else:
                # Even with extended window, insufficient data
                await self._observability.log(
                    level="WARNING",
                    message=f"Insufficient data for usage rate calculation: {request_count} requests",
                    context={
                        "key_id": key_id,
                        "request_count": request_count,
                        "min_data_points": min_data_points,
                        "window_hours": window_hours,
                    },
                )
                return None

        # Calculate requests per hour
        requests_per_hour = request_count / window_hours

        # Calculate tokens per hour (if available)
        # Note: RoutingDecision doesn't directly store token info, so we check
        # evaluation_results or return None if not available
        tokens_per_hour: float | None = None
        total_tokens = 0
        tokens_available_count = 0

        for decision in routing_decisions:
            # Check if token information is available in evaluation_results
            # This is a placeholder - token info might be stored elsewhere in the future
            # For now, we'll check evaluation_results for token data
            if decision.evaluation_results:
                # Look for token-related keys in evaluation_results
                token_keys = ["tokens", "token_count", "total_tokens", "consumed_tokens"]
                for token_key in token_keys:
                    if token_key in decision.evaluation_results:
                        token_value = decision.evaluation_results[token_key]
                        if isinstance(token_value, int | float) and token_value >= 0:
                            total_tokens += int(token_value)
                            tokens_available_count += 1
                            break

        # Calculate tokens per hour if we have token data
        tokens_per_hour = total_tokens / window_hours if tokens_available_count > 0 else None

        # Calculate confidence based on data quality
        # Higher confidence with more data points and full window coverage
        confidence = min(1.0, request_count / max(min_data_points * 2, 10))
        if window_hours < 1.0:
            # Shorter windows have lower confidence
            confidence *= 0.8

        # Create and return UsageRate
        usage_rate = UsageRate(
            requests_per_hour=requests_per_hour,
            tokens_per_hour=tokens_per_hour,
            window_hours=window_hours,
            calculated_at=now,
            confidence=confidence,
        )

        await self._observability.log(
            level="INFO",
            message=f"Calculated usage rate for key {key_id}",
            context={
                "key_id": key_id,
                "requests_per_hour": requests_per_hour,
                "tokens_per_hour": tokens_per_hour,
                "window_hours": window_hours,
                "request_count": request_count,
                "confidence": confidence,
            },
        )

        return usage_rate

    async def predict_exhaustion(self, key_id: str) -> ExhaustionPrediction | None:
        """Predict when a key will exhaust its quota based on usage rate.

        Calculates time to exhaustion by dividing remaining capacity by current
        usage rate. Handles edge cases gracefully (zero usage, unknown capacity,
        already exhausted).

        Args:
            key_id: The unique identifier of the key to predict exhaustion for.

        Returns:
            ExhaustionPrediction object with predicted exhaustion time and confidence,
            or None if prediction cannot be made (zero usage, unknown capacity, etc.).

        Raises:
            StateStoreError: If state retrieval fails.
        """
        # Get current quota state
        quota_state = await self.get_quota_state(key_id)

        # Get usage rate
        usage_rate = await self.calculate_usage_rate(key_id, window_hours=1.0)

        # Handle edge case: No usage rate available (zero usage or insufficient data)
        if usage_rate is None:
            await self._observability.log(
                level="INFO",
                message=f"Cannot predict exhaustion for key {key_id}: no usage rate available",
                context={"key_id": key_id},
            )
            return None

        # Determine which capacity and usage rate to use based on capacity_unit
        if quota_state.capacity_unit == CapacityUnit.Tokens:
            # For Tokens unit: use tokens_per_hour and remaining_capacity (in tokens)
            if usage_rate.tokens_per_hour is None or usage_rate.tokens_per_hour == 0.0:
                # Try to estimate tokens from requests if available
                if usage_rate.requests_per_hour > 0.0:
                    # Estimate: assume average tokens per request (conservative estimate: 1000 tokens/request)
                    estimated_tokens_per_hour = usage_rate.requests_per_hour * 1000.0
                    await self._observability.log(
                        level="INFO",
                        message=f"Estimating tokens_per_hour from requests_per_hour for key {key_id}",
                        context={
                            "key_id": key_id,
                            "estimated_tokens_per_hour": estimated_tokens_per_hour,
                            "requests_per_hour": usage_rate.requests_per_hour,
                        },
                    )
                    usage_rate_for_calc = estimated_tokens_per_hour
                else:
                    await self._observability.log(
                        level="INFO",
                        message=f"Cannot predict exhaustion for key {key_id}: zero token usage rate",
                        context={"key_id": key_id},
                    )
                    return None
            else:
                usage_rate_for_calc = usage_rate.tokens_per_hour

            remaining_capacity = quota_state.remaining_capacity.value
            calculation_method = "token_usage_rate_division"

        elif quota_state.capacity_unit == CapacityUnit.Mixed:
            # For Mixed unit: use tokens_per_hour and remaining_tokens
            # Prefer tokens for prediction as it's more granular
            if usage_rate.tokens_per_hour is None or usage_rate.tokens_per_hour == 0.0:
                # Try to estimate tokens from requests if available
                if usage_rate.requests_per_hour > 0.0:
                    estimated_tokens_per_hour = usage_rate.requests_per_hour * 1000.0
                    await self._observability.log(
                        level="INFO",
                        message=f"Estimating tokens_per_hour from requests_per_hour for key {key_id}",
                        context={
                            "key_id": key_id,
                            "estimated_tokens_per_hour": estimated_tokens_per_hour,
                        },
                    )
                    usage_rate_for_calc = estimated_tokens_per_hour
                else:
                    await self._observability.log(
                        level="INFO",
                        message=f"Cannot predict exhaustion for key {key_id}: zero token usage rate",
                        context={"key_id": key_id},
                    )
                    return None
            else:
                usage_rate_for_calc = usage_rate.tokens_per_hour

            # Use remaining_tokens for Mixed unit
            if quota_state.remaining_tokens is None or quota_state.remaining_tokens.value is None:
                await self._observability.log(
                    level="WARNING",
                    message=f"Cannot predict exhaustion for key {key_id}: unknown token capacity",
                    context={"key_id": key_id},
                )
                return None
            remaining_capacity = quota_state.remaining_tokens.value
            calculation_method = "token_usage_rate_division"

        else:
            # For Requests unit: use requests_per_hour and remaining_capacity (in requests)
            if usage_rate.requests_per_hour == 0.0:
                await self._observability.log(
                    level="INFO",
                    message=f"Cannot predict exhaustion for key {key_id}: zero usage rate",
                    context={"key_id": key_id},
                )
                return None

            usage_rate_for_calc = usage_rate.requests_per_hour
            remaining_capacity = quota_state.remaining_capacity.value
            calculation_method = "usage_rate_division"

        # Handle edge case: Unknown capacity
        if remaining_capacity is None:
            await self._observability.log(
                level="WARNING",
                message=f"Cannot predict exhaustion for key {key_id}: unknown capacity",
                context={"key_id": key_id},
            )
            return None

        # Handle edge case: Already exhausted (negative or zero remaining)
        if remaining_capacity <= 0:
            await self._observability.log(
                level="INFO",
                message=f"Key {key_id} already exhausted, cannot predict future exhaustion",
                context={"key_id": key_id, "remaining_capacity": remaining_capacity},
            )
            return None

        # Calculate time to exhaustion in hours
        # Formula: remaining_capacity / usage_rate = hours until exhaustion
        time_to_exhaustion_hours = remaining_capacity / usage_rate_for_calc

        # Handle edge case: Negative time (shouldn't happen, but check anyway)
        if time_to_exhaustion_hours < 0:
            await self._observability.log(
                level="WARNING",
                message=f"Negative time to exhaustion calculated for key {key_id}",
                context={
                    "key_id": key_id,
                    "remaining_capacity": remaining_capacity,
                    "usage_rate": usage_rate_for_calc,
                    "time_to_exhaustion_hours": time_to_exhaustion_hours,
                },
            )
            return None

        # Calculate uncertainty level
        uncertainty_level = self.calculate_uncertainty(quota_state, usage_rate)

        # Apply conservative adjustment based on uncertainty
        # Higher uncertainty = assume higher usage = shorter time to exhaustion
        adjusted_time_to_exhaustion_hours = self._apply_uncertainty_adjustment(
            time_to_exhaustion_hours, uncertainty_level
        )

        # Convert to datetime
        now = datetime.utcnow()
        predicted_exhaustion_at = now + timedelta(hours=adjusted_time_to_exhaustion_hours)

        # Calculate confidence level based on data quality and uncertainty
        # High confidence: exact capacity, high usage rate confidence, sufficient data, low uncertainty
        # Medium confidence: estimated capacity or moderate usage rate confidence, medium uncertainty
        # Low confidence: low usage rate confidence or high uncertainty
        confidence = self._calculate_prediction_confidence(
            quota_state, usage_rate, remaining_capacity
        )

        # Adjust confidence based on uncertainty level
        if uncertainty_level == UncertaintyLevel.High:
            confidence *= 0.7  # Reduce confidence for high uncertainty
        elif uncertainty_level == UncertaintyLevel.Unknown:
            confidence *= 0.5  # Significantly reduce confidence for unknown uncertainty
        elif uncertainty_level == UncertaintyLevel.Medium:
            confidence *= 0.85  # Slight reduction for medium uncertainty

        # Ensure confidence is within bounds
        confidence = max(0.0, min(1.0, confidence))

        # Create prediction with uncertainty level
        # Store the appropriate usage rate in current_usage_rate field
        # For backward compatibility, use requests_per_hour, but note the actual calculation method
        prediction = ExhaustionPrediction(
            key_id=key_id,
            predicted_exhaustion_at=predicted_exhaustion_at,
            confidence=confidence,
            calculation_method=calculation_method,
            current_usage_rate=usage_rate.requests_per_hour,  # For backward compatibility
            remaining_capacity=remaining_capacity,
            calculated_at=now,
            uncertainty_level=uncertainty_level,
        )

        await self._observability.log(
            level="INFO",
            message=f"Predicted exhaustion for key {key_id}",
            context={
                "key_id": key_id,
                "predicted_exhaustion_at": predicted_exhaustion_at.isoformat(),
                "time_to_exhaustion_hours": adjusted_time_to_exhaustion_hours,
                "original_time_to_exhaustion_hours": time_to_exhaustion_hours,
                "remaining_capacity": remaining_capacity,
                "usage_rate": usage_rate_for_calc,
                "requests_per_hour": usage_rate.requests_per_hour,
                "tokens_per_hour": usage_rate.tokens_per_hour,
                "capacity_unit": quota_state.capacity_unit.value,
                "calculation_method": calculation_method,
                "confidence": confidence,
                "uncertainty_level": uncertainty_level.value,
            },
        )

        return prediction

    def _calculate_prediction_confidence(
        self,
        quota_state: QuotaState,
        usage_rate: UsageRate,
        remaining_capacity: int,
    ) -> float:
        """Calculate confidence level for exhaustion prediction.

        Confidence is based on:
        - Capacity estimate type (exact > estimated > bounded > unknown)
        - Usage rate confidence
        - Data quality indicators

        Args:
            quota_state: Current quota state for the key.
            usage_rate: Calculated usage rate.
            remaining_capacity: Remaining capacity value.

        Returns:
            Confidence value between 0.0 and 1.0.
        """
        # Start with usage rate confidence as base
        confidence = usage_rate.confidence

        # Adjust based on capacity estimate type
        estimate_type = quota_state.remaining_capacity.get_estimate_type()
        if estimate_type == "exact":
            # Exact capacity: high confidence multiplier
            confidence *= 1.0
        elif estimate_type == "estimated":
            # Estimated capacity: medium confidence multiplier
            confidence *= 0.8
        elif estimate_type == "bounded":
            # Bounded capacity: lower confidence multiplier
            confidence *= 0.6
        else:
            # Unknown capacity: very low confidence (shouldn't happen, but handle it)
            confidence *= 0.3

        # Adjust based on capacity estimate confidence
        capacity_confidence = quota_state.remaining_capacity.confidence
        confidence *= capacity_confidence

        # Ensure confidence is within bounds
        confidence = max(0.0, min(1.0, confidence))

        return confidence

    def calculate_uncertainty(
        self, quota_state: QuotaState, usage_rate: UsageRate | None
    ) -> UncertaintyLevel:
        """Calculate uncertainty level based on capacity estimate and data quality.

        Uncertainty is determined by:
        - Capacity estimate type (exact > estimated > bounded > unknown)
        - Usage rate data quality (sufficient data, confidence level)
        - Data variability

        Args:
            quota_state: Current quota state for the key.
            usage_rate: Calculated usage rate (None if unavailable).

        Returns:
            UncertaintyLevel indicating the reliability of estimates.
        """
        # Check capacity estimate type
        estimate_type = quota_state.remaining_capacity.get_estimate_type()

        # Base uncertainty from capacity estimate type
        if estimate_type == "exact":
            base_uncertainty = UncertaintyLevel.Low
        elif estimate_type == "estimated":
            base_uncertainty = UncertaintyLevel.Medium
        elif estimate_type == "bounded":
            base_uncertainty = UncertaintyLevel.High
        else:  # unknown
            base_uncertainty = UncertaintyLevel.Unknown

        # If usage rate is unavailable, increase uncertainty
        if usage_rate is None:
            if base_uncertainty == UncertaintyLevel.Low:
                return UncertaintyLevel.Medium
            elif base_uncertainty == UncertaintyLevel.Medium:
                return UncertaintyLevel.High
            else:
                return UncertaintyLevel.Unknown

        # Adjust based on usage rate confidence
        # Low confidence in usage rate increases uncertainty
        if usage_rate.confidence < 0.5:
            if base_uncertainty == UncertaintyLevel.Low:
                return UncertaintyLevel.Medium
            elif base_uncertainty == UncertaintyLevel.Medium:
                return UncertaintyLevel.High
            elif base_uncertainty == UncertaintyLevel.High:
                return UncertaintyLevel.Unknown

        # Adjust based on capacity estimate confidence
        capacity_confidence = quota_state.remaining_capacity.confidence
        if capacity_confidence < 0.5:
            if base_uncertainty == UncertaintyLevel.Low:
                return UncertaintyLevel.Medium
            elif base_uncertainty == UncertaintyLevel.Medium:
                return UncertaintyLevel.High

        return base_uncertainty

    def _apply_uncertainty_adjustment(
        self, time_to_exhaustion_hours: float, uncertainty_level: UncertaintyLevel
    ) -> float:
        """Apply conservative adjustment to time_to_exhaustion based on uncertainty.

        When uncertainty is high, we assume higher usage (shorter time to exhaustion)
        to be conservative.

        Args:
            time_to_exhaustion_hours: Calculated time to exhaustion in hours.
            uncertainty_level: Uncertainty level of the prediction.

        Returns:
            Adjusted time to exhaustion in hours (shorter for higher uncertainty).
        """
        if uncertainty_level == UncertaintyLevel.Low:
            # Low uncertainty: use exact calculation (no adjustment)
            return time_to_exhaustion_hours
        elif uncertainty_level == UncertaintyLevel.Medium:
            # Medium uncertainty: assume 10% higher usage (10% shorter time)
            return time_to_exhaustion_hours * 0.9
        elif uncertainty_level == UncertaintyLevel.High:
            # High uncertainty: assume 25% higher usage (25% shorter time)
            return time_to_exhaustion_hours * 0.75
        else:  # Unknown
            # Unknown uncertainty: assume 50% higher usage (50% shorter time)
            return time_to_exhaustion_hours * 0.5

    async def _get_exhaustion_prediction(
        self, key_id: str
    ) -> ExhaustionPrediction | None:
        """Get exhaustion prediction with caching.

        Retrieves cached prediction if available and not expired, otherwise
        calculates a new prediction and caches it.

        Args:
            key_id: The unique identifier of the key.

        Returns:
            ExhaustionPrediction if available, None otherwise.
        """
        now = datetime.utcnow()

        # Check cache
        if key_id in self._prediction_cache:
            prediction, cached_at = self._prediction_cache[key_id]
            age_seconds = (now - cached_at).total_seconds()

            # Return cached prediction if not expired
            if age_seconds < self._prediction_cache_ttl_seconds:
                return prediction

            # Cache expired, remove it
            del self._prediction_cache[key_id]

        # Calculate new prediction
        try:
            prediction = await self.predict_exhaustion(key_id)
            if prediction is not None:
                # Cache the prediction
                self._prediction_cache[key_id] = (prediction, now)
            return prediction
        except Exception as e:
            # Log error but don't fail capacity update
            await self._observability.log(
                level="WARNING",
                message=f"Failed to get exhaustion prediction for key {key_id}: {e}",
                context={"key_id": key_id},
            )
            return None

    async def _create_capacity_state_transition(
        self,
        key_id: str,
        from_state: CapacityState,
        to_state: CapacityState,
        prediction: ExhaustionPrediction | None,
    ) -> None:
        """Create and save a state transition for capacity state change.

        Args:
            key_id: The unique identifier of the key.
            from_state: Previous capacity state.
            to_state: New capacity state.
            prediction: Optional exhaustion prediction that triggered the transition.
        """
        from apikeyrouter.domain.models.state_transition import StateTransition

        # Build context with prediction info if available
        context: dict[str, Any] = {}
        if prediction is not None:
            now = datetime.utcnow()
            time_until_exhaustion = prediction.predicted_exhaustion_at - now
            hours_until_exhaustion = time_until_exhaustion.total_seconds() / 3600.0
            context.update(
                {
                    "exhaustion_prediction": {
                        "predicted_exhaustion_at": prediction.predicted_exhaustion_at.isoformat(),
                        "hours_until_exhaustion": hours_until_exhaustion,
                        "confidence": prediction.confidence,
                        "uncertainty_level": prediction.uncertainty_level.value,
                    }
                }
            )

        # Create state transition
        transition = StateTransition(
            entity_type="QuotaState",
            entity_id=key_id,
            from_state=from_state.value,
            to_state=to_state.value,
            trigger="exhaustion_prediction" if prediction is not None else "capacity_update",
            context=context,
        )

        # Save state transition
        try:
            await self._state_store.save_state_transition(transition)
        except StateStoreError as e:
            # Log error but don't fail capacity update
            await self._observability.log(
                level="WARNING",
                message=f"Failed to save capacity state transition for key {key_id}: {e}",
                context={"key_id": key_id, "from_state": from_state.value, "to_state": to_state.value},
            )

        # Emit state_transition event
        try:
            await self._observability.emit_event(
                event_type="state_transition",
                payload={
                    "entity_type": "QuotaState",
                    "entity_id": key_id,
                    "from_state": from_state.value,
                    "to_state": to_state.value,
                    "trigger": transition.trigger,
                },
                metadata={
                    "transition_timestamp": transition.transition_timestamp.isoformat(),
                    **context,
                },
            )
        except Exception as e:
            # Log error but don't fail capacity update
            await self._observability.log(
                level="WARNING",
                message=f"Failed to emit state_transition event: {e}",
                context={"key_id": key_id},
            )

