"""ApiKeyRouter - Main orchestrator for intelligent API key routing."""

import uuid
from datetime import datetime
from typing import Any

from apikeyrouter.domain.components.key_manager import (
    KeyManager,
    KeyRegistrationError,
)
from apikeyrouter.domain.components.quota_awareness_engine import QuotaAwarenessEngine
from apikeyrouter.domain.components.routing_engine import (
    NoEligibleKeysError,
    RoutingEngine,
)
from apikeyrouter.domain.interfaces.observability_manager import ObservabilityManager
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter
from apikeyrouter.domain.interfaces.state_store import StateStore
from apikeyrouter.domain.models.api_key import APIKey
from apikeyrouter.domain.models.request_intent import RequestIntent
from apikeyrouter.domain.models.routing_decision import (
    ObjectiveType,
    RoutingObjective,
)
from apikeyrouter.domain.models.system_error import ErrorCategory, SystemError
from apikeyrouter.domain.models.system_response import SystemResponse
from apikeyrouter.infrastructure.config.settings import RouterSettings
from apikeyrouter.infrastructure.observability.logger import (
    DefaultObservabilityManager,
)
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore


class ApiKeyRouter:
    """Main entry point for library.

    ApiKeyRouter orchestrates components to handle API requests. It provides
    a simple API for applications while coordinating complex internal logic.

    Example:
        ```python
        # Basic initialization
        router = ApiKeyRouter()

        # With custom StateStore
        custom_store = MyCustomStateStore()
        router = ApiKeyRouter(state_store=custom_store)

        # With configuration
        config = RouterSettings(max_decisions=500)
        router = ApiKeyRouter(config=config)

        # Async context manager
        async with ApiKeyRouter() as router:
            # Use router
            pass
        ```
    """

    def __init__(
        self,
        state_store: StateStore | None = None,
        observability_manager: ObservabilityManager | None = None,
        config: RouterSettings | dict[str, Any] | None = None,
    ) -> None:
        """Initialize ApiKeyRouter with dependencies.

        Args:
            state_store: Optional StateStore implementation. If not provided,
                       defaults to InMemoryStateStore.
            observability_manager: Optional ObservabilityManager implementation.
                                 If not provided, defaults to DefaultObservabilityManager.
            config: Optional configuration. Can be:
                   - RouterSettings instance
                   - Dictionary with configuration values
                   - None (loads from environment variables)

        Raises:
            ValueError: If configuration is invalid.
        """
        # Load configuration
        if config is None:
            self._config = RouterSettings()
        elif isinstance(config, dict):
            self._config = RouterSettings.from_dict(config)
        elif isinstance(config, RouterSettings):
            self._config = config
        else:
            raise ValueError(
                f"Invalid config type: {type(config)}. Expected RouterSettings, dict, or None"
            )

        # Initialize StateStore (dependency injection support)
        if state_store is None:
            self._state_store = InMemoryStateStore(
                max_decisions=self._config.max_decisions,
                max_transitions=self._config.max_transitions,
            )
        else:
            self._state_store = state_store

        # Initialize ObservabilityManager (dependency injection support)
        if observability_manager is None:
            self._observability_manager = DefaultObservabilityManager(
                log_level=self._config.log_level
            )
        else:
            self._observability_manager = observability_manager

        # Initialize KeyManager
        self._key_manager = KeyManager(
            state_store=self._state_store,
            observability_manager=self._observability_manager,
            default_cooldown_seconds=self._config.default_cooldown_seconds,
        )

        # Initialize QuotaAwarenessEngine
        self._quota_awareness_engine = QuotaAwarenessEngine(
            state_store=self._state_store,
            observability_manager=self._observability_manager,
            key_manager=self._key_manager,
            default_cooldown_seconds=self._config.quota_default_cooldown_seconds,
        )

        # Provider-adapter mapping storage (must be initialized before RoutingEngine)
        self._providers: dict[str, ProviderAdapter] = {}

        # Initialize RoutingEngine
        self._routing_engine = RoutingEngine(
            key_manager=self._key_manager,
            state_store=self._state_store,
            observability_manager=self._observability_manager,
            quota_awareness_engine=self._quota_awareness_engine,
            providers=self._providers,
        )

    async def __aenter__(self) -> "ApiKeyRouter":
        """Async context manager entry.

        Returns:
            Self for use in async with statement.
        """
        # Perform any async initialization if needed
        # Currently, all components initialize synchronously
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit.

        Args:
            exc_type: Exception type if any.
            exc_val: Exception value if any.
            exc_tb: Exception traceback if any.
        """
        # Perform any async cleanup if needed
        # Currently, no cleanup required
        pass

    @property
    def key_manager(self) -> KeyManager:
        """Get KeyManager instance.

        Returns:
            KeyManager instance.
        """
        return self._key_manager

    @property
    def routing_engine(self) -> RoutingEngine:
        """Get RoutingEngine instance.

        Returns:
            RoutingEngine instance.
        """
        return self._routing_engine

    @property
    def quota_awareness_engine(self) -> QuotaAwarenessEngine:
        """Get QuotaAwarenessEngine instance.

        Returns:
            QuotaAwarenessEngine instance.
        """
        return self._quota_awareness_engine

    @property
    def state_store(self) -> StateStore:
        """Get StateStore instance.

        Returns:
            StateStore instance.
        """
        return self._state_store

    @property
    def observability_manager(self) -> ObservabilityManager:
        """Get ObservabilityManager instance.

        Returns:
            ObservabilityManager instance.
        """
        return self._observability_manager

    async def register_provider(
        self,
        provider_id: str,
        adapter: ProviderAdapter,
        overwrite: bool = False,
    ) -> None:
        """Register a provider with its adapter.

        Registers a provider adapter for use in routing. The provider_id must be
        unique unless overwrite is True. The adapter must be a valid ProviderAdapter
        instance implementing all required methods.

        Args:
            provider_id: Unique identifier for the provider (e.g., "openai", "anthropic").
            adapter: ProviderAdapter implementation for this provider.
            overwrite: If True, allows overwriting an existing provider registration.
                      Defaults to False.

        Raises:
            ValueError: If provider_id is empty or invalid.
            ValueError: If adapter is not a ProviderAdapter instance.
            ValueError: If provider_id already exists and overwrite is False.
            TypeError: If adapter doesn't implement required ProviderAdapter methods.

        Example:
            ```python
            from apikeyrouter import ApiKeyRouter
            from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

            router = ApiKeyRouter()
            adapter = OpenAIAdapter()
            await router.register_provider("openai", adapter)
            ```
        """
        # Validate provider_id
        if not isinstance(provider_id, str):
            raise ValueError(
                f"provider_id must be a non-empty string, got: {type(provider_id)}"
            )
        provider_id = provider_id.strip()
        if not provider_id:
            raise ValueError("provider_id cannot be empty or whitespace only")

        # Validate adapter is a ProviderAdapter instance
        if not isinstance(adapter, ProviderAdapter):
            raise ValueError(
                f"adapter must be an instance of ProviderAdapter, got: {type(adapter)}"
            )

        # Check if adapter implements all required abstract methods
        # This is a runtime check to catch incomplete implementations
        required_methods = [
            "execute_request",
            "normalize_response",
            "map_error",
            "get_capabilities",
            "estimate_cost",
            "get_health",
        ]
        missing_methods = []
        for method_name in required_methods:
            if not hasattr(adapter, method_name):
                missing_methods.append(method_name)
            else:
                method = getattr(adapter, method_name)
                if not callable(method):
                    missing_methods.append(method_name)

        if missing_methods:
            raise TypeError(
                f"adapter is missing required methods: {', '.join(missing_methods)}"
            )

        # Check for duplicate registration
        if provider_id in self._providers and not overwrite:
            raise ValueError(
                f"Provider '{provider_id}' is already registered. "
                "Use overwrite=True to replace it."
            )

        # Store provider-adapter mapping
        self._providers[provider_id] = adapter

        # Log provider registration
        await self._observability_manager.log(
            level="INFO",
            message="Provider registered",
            context={
                "provider_id": provider_id,
                "adapter_type": type(adapter).__name__,
                "overwrite": overwrite,
            },
        )
        # Emit observability event
        await self._observability_manager.emit_event(
            event_type="provider_registered",
            payload={
                "provider_id": provider_id,
                "adapter_type": type(adapter).__name__,
                "overwrite": overwrite,
            },
            metadata={
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    async def register_key(
        self,
        key_material: str,
        provider_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> APIKey:
        """Register a new API key with the system.

        Registers an API key for a provider, delegates to KeyManager for registration,
        and automatically initializes QuotaState for the new key.

        Args:
            key_material: Plain text API key to register.
            provider_id: Provider identifier this key belongs to. Must be registered
                        via register_provider() first.
            metadata: Optional provider-specific metadata.

        Returns:
            The registered APIKey instance.

        Raises:
            ValueError: If provider_id is not registered.
            KeyRegistrationError: If key registration fails (from KeyManager).

        Example:
            ```python
            from apikeyrouter import ApiKeyRouter
            from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

            router = ApiKeyRouter()
            adapter = OpenAIAdapter()
            await router.register_provider("openai", adapter)

            # Register a key
            key = await router.register_key(
                key_material="sk-...",
                provider_id="openai",
                metadata={"account_tier": "pro"}
            )
            print(f"Registered key: {key.id}")
            ```
        """
        # Validate provider_id is registered
        provider_id = provider_id.strip() if isinstance(provider_id, str) else provider_id
        if not provider_id or provider_id not in self._providers:
            registered_providers = list(self._providers.keys())
            raise ValueError(
                f"Provider '{provider_id}' is not registered. "
                f"Registered providers: {registered_providers if registered_providers else 'none'}. "
                "Use register_provider() to register a provider first."
            )

        try:
            # Delegate to KeyManager for key registration
            api_key = await self._key_manager.register_key(
                key_material=key_material,
                provider_id=provider_id,
                metadata=metadata,
            )

            # Initialize QuotaState for the new key
            # get_quota_state will automatically initialize if it doesn't exist
            await self._quota_awareness_engine.get_quota_state(api_key.id)

            # Log key registration
            await self._observability_manager.log(
                level="INFO",
                message="Key registered successfully",
                context={
                    "key_id": api_key.id,
                    "provider_id": provider_id,
                    "state": api_key.state.value if hasattr(api_key.state, "value") else str(api_key.state),
                    "has_metadata": bool(metadata),
                },
            )
            # Emit observability event
            await self._observability_manager.emit_event(
                event_type="key_registered",
                payload={
                    "key_id": api_key.id,
                    "provider_id": provider_id,
                    "state": api_key.state.value if hasattr(api_key.state, "value") else str(api_key.state),
                },
                metadata={
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )

            return api_key

        except KeyRegistrationError as e:
            # Log error and re-raise KeyManager errors as-is (they're already semantic)
            await self._observability_manager.log(
                level="ERROR",
                message="Key registration failed",
                context={
                    "provider_id": provider_id,
                    "error": str(e),
                },
            )
            raise
        except Exception as e:
            # Log unexpected error and wrap
            await self._observability_manager.log(
                level="ERROR",
                message="Unexpected error during key registration",
                context={
                    "provider_id": provider_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise KeyRegistrationError(
                f"Failed to register key: {e}"
            ) from e

    async def route(
        self,
        request_intent: RequestIntent | dict[str, Any],
        objective: RoutingObjective | str | None = None,
    ) -> SystemResponse:
        """Route a request to an appropriate API key and execute it.

        This is the main entry point for making API calls through the router.
        It orchestrates routing decision, request execution, quota updates,
        and error handling with graceful degradation.

        Args:
            request_intent: RequestIntent object or dict containing:
                - model: str (required) - Model identifier
                - messages: list[Message] (required) - Conversation messages
                - provider_id: str (required) - Provider to route to
                - parameters: dict (optional) - Request parameters
            objective: Optional routing objective. Can be:
                - RoutingObjective object
                - String (e.g., "cost", "reliability", "fairness")
                - None (defaults to "fairness")

        Returns:
            SystemResponse with content, metadata, and routing information.

        Raises:
            ValueError: If request_intent is invalid or missing required fields.
            NoEligibleKeysError: If no eligible keys are available.
            SystemError: If request execution fails (from adapter).

        Example:
            ```python
            from apikeyrouter import ApiKeyRouter
            from apikeyrouter.domain.models.request_intent import RequestIntent, Message

            router = ApiKeyRouter()
            await router.register_provider("openai", OpenAIAdapter())
            await router.register_key("sk-...", "openai")

            # Route a request
            intent = RequestIntent(
                model="gpt-4",
                messages=[Message(role="user", content="Hello!")],
                provider_id="openai"
            )
            response = await router.route(intent, objective="reliability")
            print(response.content)
            ```
        """
        # Generate request_id and correlation_id
        request_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())

        # Extract provider_id and convert request_intent to RequestIntent if needed
        provider_id: str | None = None
        if isinstance(request_intent, dict):
            # Extract provider_id from dict
            provider_id = request_intent.get("provider_id")
            if not provider_id:
                raise ValueError(
                    "request_intent must contain 'provider_id' field when passed as dict"
                )
            # Create RequestIntent from dict (excluding provider_id)
            intent_dict = {k: v for k, v in request_intent.items() if k != "provider_id"}
            try:
                request_intent = RequestIntent(**intent_dict)
            except Exception as e:
                raise ValueError(f"Invalid request_intent: {e}") from e
        elif isinstance(request_intent, RequestIntent):
            # For RequestIntent object, try to get provider_id from parameters
            # (workaround until RequestIntent has provider_id field)
            provider_id = request_intent.parameters.get("provider_id")
            if not provider_id:
                raise ValueError(
                    "When passing RequestIntent object, provider_id must be in parameters dict. "
                    "Example: RequestIntent(..., parameters={'provider_id': 'openai'})"
                )
        else:
            raise ValueError(
                f"request_intent must be RequestIntent or dict, got {type(request_intent)}"
            )

        # Normalize objective
        if objective is None:
            objective = RoutingObjective(primary=ObjectiveType.Fairness.value)
        elif isinstance(objective, str):
            objective = RoutingObjective(primary=objective.lower())

        # Log request start
        await self._observability_manager.log(
            level="INFO",
            message="Request routing started",
            context={
                "request_id": request_id,
                "correlation_id": correlation_id,
                "provider_id": provider_id,
                "model": request_intent.model,
            },
        )

        # Prepare request_intent dict for RoutingEngine (it expects a dict with provider_id)
        routing_intent = {
            "provider_id": provider_id,
            "request_id": request_id,
        }

        # Get routing decision from RoutingEngine
        try:
            routing_decision = await self._routing_engine.route_request(
                request_intent=routing_intent,
                objective=objective,
                request_intent_obj=request_intent,
            )
        except NoEligibleKeysError as e:
            # Log and re-raise
            await self._observability_manager.log(
                level="ERROR",
                message="No eligible keys available for routing",
                context={
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "provider_id": provider_id,
                    "error": str(e),
                },
            )
            await self._observability_manager.emit_event(
                event_type="routing_failed",
                payload={
                    "request_id": request_id,
                    "provider_id": provider_id,
                    "reason": "no_eligible_keys",
                    "error": str(e),
                },
                metadata={
                    "correlation_id": correlation_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
            raise

        # Save routing decision to StateStore
        await self._state_store.save_routing_decision(routing_decision)

        # Log routing decision with correlation_id
        await self._observability_manager.log(
            level="INFO",
            message="Routing decision made",
            context={
                "request_id": request_id,
                "correlation_id": correlation_id,
                "key_id": routing_decision.selected_key_id,
                "provider_id": routing_decision.selected_provider_id,
                "objective": objective.primary if hasattr(objective, "primary") else str(objective),
                "explanation": routing_decision.explanation,
                "confidence": routing_decision.confidence,
            },
        )
        await self._observability_manager.emit_event(
            event_type="routing_decision_made",
            payload={
                "request_id": request_id,
                "key_id": routing_decision.selected_key_id,
                "provider_id": routing_decision.selected_provider_id,
                "explanation": routing_decision.explanation,
                "objective": objective.primary if hasattr(objective, "primary") else str(objective),
            },
            metadata={
                "correlation_id": correlation_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        # Get ProviderAdapter for selected provider
        provider_id = routing_decision.selected_provider_id
        if provider_id not in self._providers:
            error_msg = f"Provider '{provider_id}' not found in registered providers"
            await self._observability_manager.log(
                level="ERROR",
                message=error_msg,
                context={
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "provider_id": provider_id,
                },
            )
            raise ValueError(error_msg)

        adapter = self._providers[provider_id]

        # Track tried keys for graceful degradation
        tried_keys: set[str] = {routing_decision.selected_key_id}
        max_retries = 3  # Try up to 3 different keys
        last_error: SystemError | None = None

        # Execute request with graceful degradation
        for attempt in range(max_retries):
            # Get APIKey for selected key_id
            current_key_id = (
                routing_decision.selected_key_id
                if attempt == 0
                else self._get_alternative_key(
                    provider_id, tried_keys, routing_decision.eligible_keys
                )
            )

            if current_key_id is None:
                # No more keys to try
                break

            tried_keys.add(current_key_id)
            api_key = await self._key_manager.get_key(current_key_id)
            if api_key is None:
                await self._observability_manager.log(
                    level="WARNING",
                    message=f"Key '{current_key_id}' not found, trying next key",
                    context={
                        "request_id": request_id,
                        "correlation_id": correlation_id,
                        "key_id": current_key_id,
                        "attempt": attempt + 1,
                    },
                )
                continue

            # Execute request via adapter
            # Note: Adapter handles key decryption internally
            try:
                system_response = await adapter.execute_request(
                    intent=request_intent,
                    key=api_key,
                )
                # Success! Update routing decision with actual key used
                if current_key_id != routing_decision.selected_key_id:
                    routing_decision.selected_key_id = current_key_id
                    await self._state_store.save_routing_decision(routing_decision)

                # Update quota state after successful request
                if system_response.metadata.tokens_used:
                    consumed_tokens = system_response.metadata.tokens_used.total_tokens
                    try:
                        await self._quota_awareness_engine.update_capacity(
                            key_id=current_key_id,
                            consumed=consumed_tokens,
                            cost_estimate=None,  # Can be enhanced later with actual cost
                        )
                    except Exception as e:
                        # Log quota update error but don't fail the request
                        await self._observability_manager.log(
                            level="WARNING",
                            message="Failed to update quota state",
                            context={
                                "request_id": request_id,
                                "correlation_id": correlation_id,
                                "key_id": current_key_id,
                                "error": str(e),
                            },
                        )

                # Update key usage statistics
                api_key.usage_count += 1
                api_key.last_used_at = datetime.utcnow()
                await self._state_store.save_key(api_key)

                # Calculate response time
                response_time_ms = (
                    system_response.metadata.response_time_ms
                    if system_response.metadata.response_time_ms
                    else 0
                )
                tokens_used = (
                    system_response.metadata.tokens_used.total_tokens
                    if system_response.metadata.tokens_used
                    else 0
                )

                # Log successful request completion with metrics
                await self._observability_manager.log(
                    level="INFO",
                    message="Request completed successfully",
                    context={
                        "request_id": request_id,
                        "correlation_id": correlation_id,
                        "key_id": current_key_id,
                        "provider_id": provider_id,
                        "attempt": attempt + 1,
                        "tokens_used": tokens_used,
                        "response_time_ms": response_time_ms,
                        "cost": (
                            system_response.cost.amount
                            if system_response.cost
                            else None
                        ),
                    },
                )
                await self._observability_manager.emit_event(
                    event_type="request_completed",
                    payload={
                        "request_id": request_id,
                        "key_id": current_key_id,
                        "provider_id": provider_id,
                        "tokens_used": tokens_used,
                        "response_time_ms": response_time_ms,
                        "success": True,
                    },
                    metadata={
                        "correlation_id": correlation_id,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

                # Ensure response has correct request_id, correlation_id, and key_used
                system_response.request_id = request_id
                system_response.key_used = current_key_id
                system_response.metadata.correlation_id = correlation_id

                return system_response

            except SystemError as e:
                last_error = e
                # Log error with correlation_id
                await self._observability_manager.log(
                    level="WARNING" if e.retryable else "ERROR",
                    message=f"Request execution failed (attempt {attempt + 1})",
                    context={
                        "request_id": request_id,
                        "correlation_id": correlation_id,
                        "key_id": current_key_id,
                        "error_category": (
                            e.category.value
                            if hasattr(e.category, "value")
                            else str(e.category)
                        ),
                        "error_message": e.message,
                        "retryable": e.retryable,
                        "attempt": attempt + 1,
                    },
                )
                # Update key failure count
                api_key.failure_count += 1
                await self._state_store.save_key(api_key)

                # Emit error event
                await self._observability_manager.emit_event(
                    event_type="request_failed",
                    payload={
                        "request_id": request_id,
                        "key_id": current_key_id,
                        "error_category": (
                            e.category.value
                            if hasattr(e.category, "value")
                            else str(e.category)
                        ),
                        "error_message": e.message,
                        "retryable": e.retryable,
                        "attempt": attempt + 1,
                    },
                    metadata={
                        "correlation_id": correlation_id,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

                # If error is not retryable, don't try other keys
                if not e.retryable:
                    break

                # If this was the last attempt, break
                if attempt == max_retries - 1:
                    break

        # All attempts failed
        if last_error:
            await self._observability_manager.log(
                level="ERROR",
                message="Request failed after all retry attempts",
                context={
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "provider_id": provider_id,
                    "tried_keys": list(tried_keys),
                    "final_error": last_error.message,
                    "max_retries": max_retries,
                },
            )
            await self._observability_manager.emit_event(
                event_type="request_failed",
                payload={
                    "request_id": request_id,
                    "provider_id": provider_id,
                    "tried_keys": list(tried_keys),
                    "final_error": last_error.message,
                    "max_retries": max_retries,
                    "success": False,
                },
                metadata={
                    "correlation_id": correlation_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
            raise last_error

        # Fallback: should not reach here, but handle gracefully
        raise SystemError(
            category=ErrorCategory.ProviderError,
            message="Request failed: no keys available after retries",
            retryable=False,
        )

    def _get_alternative_key(
        self,
        provider_id: str,
        tried_keys: set[str],
        eligible_keys: list[str],
    ) -> str | None:
        """Get an alternative key that hasn't been tried yet.

        Args:
            provider_id: Provider identifier.
            tried_keys: Set of key IDs that have already been tried.
            eligible_keys: List of eligible key IDs from routing decision.

        Returns:
            Key ID to try next, or None if no alternatives available.
        """
        for key_id in eligible_keys:
            if key_id not in tried_keys:
                return key_id
        return None

