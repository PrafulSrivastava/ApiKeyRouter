# Component Specifications

This document provides detailed interface specifications for all core components. These specifications are the contract that implementations must fulfill.

## KeyManager

**File:** `apikeyrouter/domain/components/key_manager.py`

### Interface

```python
class KeyManager:
    """Manages API key lifecycle, state transitions, and eligibility."""
    
    async def register_key(
        self,
        key_material: str,
        provider_id: str,
        metadata: dict[str, Any] | None = None
    ) -> APIKey:
        """
        Register a new API key.
        
        Args:
            key_material: The actual API key (will be encrypted)
            provider_id: Provider this key belongs to
            metadata: Optional metadata (account info, tier, etc.)
            
        Returns:
            APIKey with generated ID and state=Available
            
        Raises:
            InvalidProviderError: If provider_id doesn't exist
            KeyAlreadyExistsError: If key material already registered
        """
    
    async def get_key(self, key_id: str) -> APIKey | None:
        """Retrieve key by ID. Returns None if not found."""
    
    async def update_key_state(
        self,
        key_id: str,
        new_state: KeyState,
        reason: str,
        context: dict[str, Any] | None = None
    ) -> StateTransition:
        """
        Update key state with audit trail.
        
        Args:
            key_id: Key to update
            new_state: Target state
            reason: Reason for state change
            context: Additional context (error codes, retry_after, etc.)
            
        Returns:
            StateTransition record
            
        Raises:
            InvalidStateTransitionError: If transition is not allowed
            KeyNotFoundError: If key_id doesn't exist
        """
    
    async def get_eligible_keys(
        self,
        provider_id: str | None = None,
        policy: Policy | None = None
    ) -> list[APIKey]:
        """
        Get keys eligible for routing based on state and policy.
        
        Args:
            provider_id: Filter by provider (None = all providers)
            policy: Policy to evaluate against
            
        Returns:
            List of eligible keys (state=Available, not in cooldown, policy-compliant)
        """
    
    async def revoke_key(self, key_id: str) -> None:
        """
        Revoke key (graceful degradation).
        
        Key state set to Disabled. System continues operating with remaining keys.
        """
    
    async def rotate_key(
        self,
        old_key_id: str,
        new_key_material: str
    ) -> APIKey:
        """
        Rotate key without breaking system identity.
        
        Old key is disabled, new key inherits quota state and usage history.
        """
    
    async def get_key_state(self, key_id: str) -> KeyState:
        """Get current state of a key."""
```

### State Machine

**Valid Transitions:**
- `Available → Throttled` (rate limit detected)
- `Available → Exhausted` (quota exhausted)
- `Available → Disabled` (manual revocation)
- `Available → Invalid` (authentication failure)
- `Throttled → Available` (cooldown expired)
- `Exhausted → Recovering` (quota reset approaching)
- `Recovering → Available` (quota reset)
- `Any → Disabled` (manual revocation)

**Invalid Transitions:**
- `Disabled → Any` (disabled keys cannot be re-enabled automatically)
- `Invalid → Any` (invalid keys must be replaced)

## QuotaAwarenessEngine

**File:** `apikeyrouter/domain/components/quota_awareness_engine.py`

### Interface

```python
class QuotaAwarenessEngine:
    """Forward-looking quota awareness with predictive exhaustion."""
    
    async def update_capacity(
        self,
        key_id: str,
        consumed: int,
        cost_estimate: CostEstimate | None = None
    ) -> QuotaState:
        """
        Update capacity after request.
        
        Args:
            key_id: Key that was used
            consumed: Amount consumed (tokens, requests, etc.)
            cost_estimate: Optional cost estimate for cost-aware tracking
            
        Returns:
            Updated QuotaState
        """
    
    async def get_quota_state(self, key_id: str) -> QuotaState | None:
        """Get current quota state for a key."""
    
    async def predict_exhaustion(
        self,
        key_id: str
    ) -> ExhaustionPrediction | None:
        """
        Predict when key will exhaust.
        
        Returns:
            ExhaustionPrediction with predicted time and confidence, or None if cannot predict
        """
    
    async def calculate_capacity_estimate(
        self,
        key_id: str
    ) -> CapacityEstimate:
        """
        Calculate remaining capacity with uncertainty.
        
        Returns:
            CapacityEstimate with value, bounds, and confidence
        """
    
    async def handle_quota_response(
        self,
        key_id: str,
        response: HTTPResponse
    ) -> QuotaState:
        """
        Interpret provider response for quota information.
        
        Args:
            key_id: Key that made the request
            response: HTTP response from provider
            
        Returns:
            Updated QuotaState
            
        Notes:
            - 429 responses → Throttled state, update cooldown
            - 200 responses → Update usage, recalculate capacity
        """
    
    async def reset_quota(
        self,
        key_id: str,
        time_window: TimeWindow
    ) -> QuotaState:
        """Reset quota for a time window (called on quota reset events)."""
```

### Capacity States

**State Definitions:**
- **Abundant:** >80% remaining, safe to use
- **Constrained:** 50-80% remaining, use with caution
- **Critical:** 20-50% remaining, avoid unless necessary
- **Exhausted:** <20% or hard limit hit, do not use
- **Recovering:** Exhausted but reset approaching, monitor

## RoutingEngine

**File:** `apikeyrouter/domain/components/routing_engine.py`

### Interface

```python
class RoutingEngine:
    """Makes intelligent routing decisions based on explicit objectives."""
    
    async def route_request(
        self,
        request_intent: RequestIntent,
        objective: RoutingObjective | None = None,
        policies: list[Policy] | None = None
    ) -> RoutingDecision:
        """
        Make routing decision for a request.
        
        Args:
            request_intent: Request to route
            objective: Optional routing objective (default: reliability)
            policies: Optional policies to apply
            
        Returns:
            RoutingDecision with selected key, provider, and explanation
            
        Raises:
            NoEligibleKeysError: If no keys available
            PolicyViolationError: If request violates policy
        """
    
    async def evaluate_keys(
        self,
        eligible_keys: list[APIKey],
        objective: RoutingObjective,
        context: RequestContext
    ) -> dict[str, float]:
        """
        Score keys against objective.
        
        Returns:
            Dictionary mapping key_id to score (0.0 to 1.0)
        """
    
    def explain_decision(self, decision: RoutingDecision) -> str:
        """
        Generate human-readable explanation of routing decision.
        
        Returns:
            Explanation string (e.g., "Selected key1 because lowest cost while maintaining reliability threshold")
        """
    
    async def update_routing_feedback(
        self,
        decision_id: str,
        success: bool,
        metrics: dict[str, Any]
    ) -> None:
        """
        Learn from routing outcomes.
        
        Updates internal models based on actual results vs. predictions.
        """
    
    def get_routing_strategies(self) -> list[RoutingStrategy]:
        """List available routing strategies."""
```

### Routing Objectives

**Supported Objectives:**
- `cost` - Minimize cost
- `reliability` - Maximize success rate
- `fairness` - Distribute load evenly
- `quality` - Prefer higher-quality providers
- `latency` - Minimize response time

**Multi-Objective:**
- Can combine objectives with weights
- Can specify constraints (e.g., "minimize cost while maintaining >95% reliability")

## ProviderAdapter (Abstract Interface)

**File:** `apikeyrouter/domain/interfaces/provider_adapter.py`

### Interface

```python
class ProviderAdapter(ABC):
    """Abstract interface for provider-specific implementations."""
    
    @abstractmethod
    async def execute_request(
        self,
        intent: RequestIntent,
        key: APIKey
    ) -> SystemResponse:
        """
        Execute request with provider.
        
        Args:
            intent: Request intent in system terms
            key: API key to use
            
        Returns:
            SystemResponse (normalized to system format)
            
        Raises:
            ProviderError: Provider-specific errors (normalized)
        """
    
    @abstractmethod
    def normalize_response(
        self,
        provider_response: Any
    ) -> SystemResponse:
        """Normalize provider response to system format."""
    
    @abstractmethod
    def map_error(
        self,
        provider_error: Exception
    ) -> SystemError:
        """Map provider error to system error category."""
    
    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Declare what provider supports."""
    
    @abstractmethod
    async def estimate_cost(
        self,
        request_intent: RequestIntent
    ) -> CostEstimate:
        """Estimate request cost."""
    
    @abstractmethod
    async def get_health(self) -> HealthState:
        """Get provider health status."""
```

### Implementation Requirements

**All adapters must:**
1. Implement all abstract methods
2. Never raise provider-specific exceptions (normalize first)
3. Declare capabilities explicitly (don't assume)
4. Handle provider quirks internally (never leak to core)

## FailureHandler

**File:** `apikeyrouter/domain/components/failure_handler.py`

### Interface

```python
class FailureHandler:
    """Handles failures gracefully with semantic interpretation."""
    
    async def interpret_failure(
        self,
        error: Exception,
        context: RequestContext
    ) -> FailureInterpretation:
        """
        Interpret error semantically.
        
        Returns:
            FailureInterpretation with type, severity, and recommended action
        """
    
    async def update_key_health(
        self,
        key_id: str,
        failure: FailureInterpretation
    ) -> None:
        """Update key health based on failure."""
    
    def should_retry(
        self,
        failure: FailureInterpretation,
        attempt: int
    ) -> bool:
        """
        Determine if retry is safe.
        
        Returns:
            True if retry recommended, False otherwise
        """
    
    async def get_circuit_state(self, key_id: str) -> CircuitState:
        """Get circuit breaker state for a key."""
    
    async def reduce_load_on_failure(
        self,
        key_id: str,
        provider_id: str
    ) -> None:
        """Apply backpressure - reduce load on failing components."""
    
    async def monitor_recovery(self, key_id: str) -> None:
        """Monitor failed components for recovery (background task)."""
```

## CostController

**File:** `apikeyrouter/domain/components/cost_controller.py`

### Interface

```python
class CostController:
    """Proactive cost control with budget enforcement."""
    
    async def estimate_request_cost(
        self,
        request: RequestContext,
        provider_id: str,
        key_id: str
    ) -> CostEstimate:
        """
        Estimate cost before execution.
        
        Returns:
            CostEstimate with amount, currency, and confidence
        """
    
    async def check_budget(
        self,
        request: RequestContext,
        estimated_cost: CostEstimate
    ) -> BudgetCheckResult:
        """
        Check if request would exceed budget.
        
        Returns:
            BudgetCheckResult with allowed=True/False and reason
        """
    
    async def record_actual_cost(
        self,
        request_id: str,
        actual_cost: Decimal
    ) -> None:
        """Record actual cost after execution."""
    
    async def reconcile_estimate(
        self,
        request_id: str,
        estimated: CostEstimate,
        actual: Decimal
    ) -> None:
        """Learn from cost estimation deviations."""
    
    async def get_budget_status(
        self,
        scope: BudgetScope
    ) -> BudgetStatus:
        """Get current budget status for a scope."""
    
    async def enforce_budget(
        self,
        scope: BudgetScope,
        mode: EnforcementMode
    ) -> None:
        """Enforce budget limits (prevent or warn)."""
```

## PolicyEngine

**File:** `apikeyrouter/domain/components/policy_engine.py`

### Interface

```python
class PolicyEngine:
    """Evaluates declarative policies."""
    
    async def evaluate_policy(
        self,
        policy: Policy,
        context: dict[str, Any]
    ) -> PolicyResult:
        """
        Evaluate policy against context.
        
        Returns:
            PolicyResult with filtered keys, constraints, and actions
        """
    
    async def get_applicable_policies(
        self,
        scope: PolicyScope,
        policy_type: PolicyType
    ) -> list[Policy]:
        """Get policies that apply to a scope."""
    
    async def resolve_policy_conflicts(
        self,
        policies: list[Policy]
    ) -> Policy:
        """Resolve conflicts using precedence rules."""
    
    async def validate_policy(
        self,
        policy: Policy
    ) -> ValidationResult:
        """Validate policy configuration."""
    
    async def dry_run_policy(
        self,
        policy: Policy,
        context: dict[str, Any]
    ) -> PolicyImpact:
        """Predict policy impact without applying."""
```

## StateStore (Abstract Interface)

**File:** `apikeyrouter/domain/interfaces/state_store.py`

### Interface

```python
class StateStore(ABC):
    """Abstract interface for state persistence."""
    
    @abstractmethod
    async def save_key(self, key: APIKey) -> None:
        """Save/update key."""
    
    @abstractmethod
    async def get_key(self, key_id: str) -> APIKey | None:
        """Retrieve key."""
    
    @abstractmethod
    async def save_quota_state(self, state: QuotaState) -> None:
        """Save quota state."""
    
    @abstractmethod
    async def get_quota_state(self, key_id: str) -> QuotaState | None:
        """Retrieve quota state."""
    
    @abstractmethod
    async def save_routing_decision(self, decision: RoutingDecision) -> None:
        """Save routing decision."""
    
    @abstractmethod
    async def save_state_transition(self, transition: StateTransition) -> None:
        """Save state transition."""
    
    @abstractmethod
    async def query_state(self, query: StateQuery) -> list[Any]:
        """Query state with filters."""
```

### Implementations

**MemoryStore:** In-memory implementation (default, stateless)
**MongoStore:** MongoDB implementation (optional, for persistence)
**RedisStore:** Redis implementation (optional, for distributed state)

## ObservabilityManager

**File:** `apikeyrouter/infrastructure/observability/logger.py`

### Interface

```python
class ObservabilityManager:
    """Provides observability through logging, metrics, and tracing."""
    
    async def log_request(self, context: RequestContext) -> None:
        """Log request with full context."""
    
    async def log_routing_decision(self, decision: RoutingDecision) -> None:
        """Log routing decision."""
    
    async def log_state_transition(self, transition: StateTransition) -> None:
        """Log state change."""
    
    async def emit_metric(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None
    ) -> None:
        """Emit performance metric."""
    
    async def get_trace(self, request_id: str) -> Trace:
        """Get full trace for a request."""
    
    def subscribe_to_events(
        self,
        event_type: str,
        callback: Callable[[Any], None]
    ) -> None:
        """Subscribe to events (for component integration)."""
```

## ApiKeyRouter (Main Orchestrator)

**File:** `apikeyrouter/router.py`

### Interface

```python
class ApiKeyRouter:
    """Main entry point for library."""
    
    def __init__(
        self,
        state_store: StateStore | None = None,
        observability_manager: ObservabilityManager | None = None,
        config: Configuration | None = None
    ):
        """
        Initialize router.
        
        Args:
            state_store: Optional state store (default: MemoryStore)
            observability_manager: Optional observability (default: basic logger)
            config: Optional configuration (default: from environment)
        """
    
    async def route(
        self,
        request_intent: RequestIntent,
        objective: RoutingObjective | None = None
    ) -> SystemResponse:
        """
        Route request intelligently.
        
        Args:
            request_intent: Request to route (dict or RequestIntent model)
            objective: Optional routing objective
            
        Returns:
            SystemResponse with completion and metadata
            
        Raises:
            NoEligibleKeysError: If no keys available
            BudgetExceededError: If request would exceed budget
            ProviderError: If provider returns error
        """
    
    async def register_provider(
        self,
        provider: Provider,
        adapter: ProviderAdapter
    ) -> None:
        """Register provider with adapter."""
    
    async def register_key(
        self,
        key_material: str,
        provider_id: str,
        metadata: dict[str, Any] | None = None
    ) -> APIKey:
        """Register API key."""
    
    async def get_state_summary(self) -> StateSummary:
        """Get system state summary."""
    
    async def configure_policy(self, policy: Policy) -> None:
        """Configure routing/cost policy."""
```

### Usage Example

```python
from apikeyrouter import ApiKeyRouter

# Initialize
router = ApiKeyRouter()

# Register provider
router.register_provider("openai", OpenAIAdapter())

# Register keys
await router.register_key("sk-key1", "openai")
await router.register_key("sk-key2", "openai")

# Use (automatic key switching)
response = await router.route({
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}]
})

# Response includes metadata
print(response.content)  # LLM response
print(response.metadata.key_used)  # Which key was used
print(response.metadata.routing_explanation)  # Why this key
```

---

**Note:** These are the core interfaces. Implementations must follow these contracts exactly. All methods are async and must handle errors gracefully.

