# Error Handling Strategy

The error handling strategy is based on the first-principles requirement: **"A system fails gracefully if it reduces harm as failure likelihood increases."** This means failures are interpreted semantically, load is reduced under failure, and the system can operate while degraded.

## General Approach

**Error Model:** Custom exception hierarchy with semantic error categories

**Exception Hierarchy:**
```
ApiKeyRouterError (base)
├── ProviderError (provider-related)
│   ├── RateLimitError (429 - quota exhausted)
│   ├── AuthenticationError (401 - invalid key)
│   ├── ServiceUnavailableError (503 - provider down)
│   └── ProviderTimeoutError (timeout)
├── RoutingError (routing-related)
│   ├── NoEligibleKeysError (no keys available)
│   ├── BudgetExceededError (budget limit hit)
│   └── PolicyViolationError (policy constraint violated)
├── StateError (state-related)
│   ├── InvalidStateTransitionError
│   └── StateCorruptionError
└── ConfigurationError (configuration-related)
    ├── InvalidConfigurationError
    └── MissingConfigurationError
```

**Error Propagation:**
- **Domain Layer:** Raises semantic exceptions (ProviderError, RoutingError)
- **Infrastructure Layer:** Catches low-level errors, converts to domain exceptions
- **Application Layer:** Handles domain exceptions, converts to user-facing errors
- **API Layer:** Converts exceptions to HTTP responses with appropriate status codes

**Error Handling Principles:**
1. **Fail Fast:** Detect errors early, before they propagate
2. **Fail Explicitly:** Use specific exception types, not generic exceptions
3. **Fail Safely:** Never expose sensitive information (keys, internal state)
4. **Fail Gracefully:** Reduce load, contain failures, enable recovery

## Logging Standards

**Library:** structlog 24.1.0

**Format:** JSON (structured logging for production, human-readable for development)

**Levels:**
- **DEBUG:** Detailed diagnostic information (routing decisions, state transitions)
- **INFO:** General informational messages (key registered, request completed)
- **WARNING:** Warning messages (quota low, key throttled, degraded mode)
- **ERROR:** Error conditions (request failed, key invalid)
- **CRITICAL:** Critical errors (system cannot continue)

**Required Context:**
- **Correlation ID:** `correlation_id` - Unique ID per request for tracing
- **Request ID:** `request_id` - Unique ID for this specific request
- **Key ID:** `key_id` - Which key was used (if applicable)
- **Provider ID:** `provider_id` - Which provider was used (if applicable)
- **Service Context:** `service=apikeyrouter`, `component=RoutingEngine`, etc.
- **User Context:** Not applicable (library has no user concept)

**Logging Examples:**
```python
# Success
logger.info(
    "request_completed",
    request_id="req_123",
    key_id="key_abc",
    provider_id="openai",
    status_code=200,
    response_time_ms=1250,
    cost=0.015
)

# Failure
logger.error(
    "request_failed",
    request_id="req_123",
    key_id="key_abc",
    provider_id="openai",
    error_type="RateLimitError",
    error_message="Rate limit exceeded",
    retry_after=60,
    will_retry=True,
    alternative_key="key_def"
)

# State Transition
logger.info(
    "key_state_transition",
    key_id="key_abc",
    from_state="Available",
    to_state="Throttled",
    trigger="rate_limit",
    cooldown_until="2025-12-19T10:35:00Z"
)
```

**What NOT to Log:**
- API key material (even encrypted)
- Full request/response bodies (may contain sensitive data)
- Internal routing scores (too verbose)
- User-identifiable information (if applicable)

## Error Handling Patterns

### External API Errors

**Retry Policy:**
- **Rate Limit (429):** Do NOT retry immediately
  - Update key state to Throttled
  - Set cooldown period (from `Retry-After` header or default)
  - Route to different key/provider
  - Retry only after cooldown expires
- **Service Unavailable (503):** Retry with exponential backoff
  - Initial delay: 1 second
  - Max delay: 60 seconds
  - Max attempts: 3
  - Route to different provider after 2 failures
- **Timeout:** Retry with different key
  - Immediate retry with different key
  - Max attempts: 2 per key
  - Fail if all keys timeout
- **Authentication Error (401):** Do NOT retry
  - Mark key as Invalid
  - Remove from routing pool
  - Log for manual intervention
- **Client Error (400):** Do NOT retry
  - Invalid request, retrying won't help
  - Return error to caller

**Circuit Breaker:**
- **Configuration:**
  - Failure threshold: 5 failures in 60 seconds
  - Half-open timeout: 30 seconds
  - Open state timeout: 5 minutes
- **States:**
  - **Closed:** Normal operation, requests allowed
  - **Open:** Too many failures, requests blocked
  - **Half-Open:** Testing recovery, limited requests allowed
- **Scope:** Per key and per provider
- **Recovery:** Automatic transition from Open → Half-Open → Closed

**Timeout Configuration:**
- **Provider Request Timeout:** 30 seconds (configurable)
- **Connection Timeout:** 10 seconds
- **Read Timeout:** 30 seconds
- **Total Request Timeout:** 60 seconds (includes retries)

**Error Translation:**
- **429 Rate Limit:** → `RateLimitError` → Key state: Throttled
- **401 Unauthorized:** → `AuthenticationError` → Key state: Invalid
- **503 Service Unavailable:** → `ServiceUnavailableError` → Provider health: Degraded
- **Timeout:** → `ProviderTimeoutError` → Key health: Degraded
- **Network Error:** → `ProviderTimeoutError` → Retry with different key

### Business Logic Errors

**Custom Exceptions:**
- `NoEligibleKeysError`: No keys available for routing
  - **User-Facing:** "No API keys available. Please add keys or wait for quota reset."
  - **Action:** Return 503 Service Unavailable
- `BudgetExceededError`: Request would exceed budget
  - **User-Facing:** "Budget limit exceeded. Request rejected."
  - **Action:** Return 429 Too Many Requests (with budget info)
- `PolicyViolationError`: Request violates routing policy
  - **User-Facing:** "Request violates routing policy."
  - **Action:** Return 400 Bad Request
- `QuotaExhaustedError`: All keys exhausted
  - **User-Facing:** "All API keys exhausted. Please add keys or wait for quota reset."
  - **Action:** Return 503 Service Unavailable

**User-Facing Errors:**
- **Format:** JSON with error object
  ```json
  {
    "error": {
      "message": "Human-readable error message",
      "type": "NoEligibleKeysError",
      "code": "NO_KEYS_AVAILABLE",
      "details": {
        "provider_id": "openai",
        "available_keys": 0,
        "exhausted_keys": 3
      }
    }
  }
  ```
- **HTTP Status Mapping:**
  - `NoEligibleKeysError` → 503 Service Unavailable
  - `BudgetExceededError` → 429 Too Many Requests
  - `PolicyViolationError` → 400 Bad Request
  - `ProviderError` → 502 Bad Gateway (provider error)
  - `RoutingError` → 503 Service Unavailable (routing failure)

**Error Codes:**
- `NO_KEYS_AVAILABLE` - No eligible keys for routing
- `BUDGET_EXCEEDED` - Budget limit exceeded
- `POLICY_VIOLATION` - Request violates policy
- `QUOTA_EXHAUSTED` - All keys exhausted
- `RATE_LIMIT` - Rate limit exceeded
- `PROVIDER_ERROR` - Provider returned error
- `TIMEOUT` - Request timeout
- `INVALID_KEY` - API key is invalid

### Data Consistency

**Transaction Strategy:**
- **In-Memory State:** Atomic operations (Python GIL ensures thread safety)
- **MongoDB State:** Use transactions for multi-document updates
- **Redis State:** Use atomic operations (SET, INCR, etc.)
- **State Transitions:** Always atomic (state + transition record)

**Compensation Logic:**
- **Failed Request After State Update:**
  - Rollback quota state update
  - Rollback cost tracking
  - Log compensation action
- **Partial State Update:**
  - Detect inconsistency (state doesn't match usage)
  - Reconcile on next request
  - Log reconciliation event

**Idempotency:**
- **Request ID:** Each request has unique ID
- **Idempotent Operations:** State updates are idempotent (same request ID = same result)
- **Retry Safety:** Retrying same request ID doesn't double-count usage
- **Deduplication:** Track processed request IDs (TTL: 1 hour)

## Failure Containment

**Isolation:**
- **Key-Level:** Failure of one key doesn't affect others
- **Provider-Level:** Failure of one provider doesn't affect others
- **Request-Level:** Failure of one request doesn't affect others
- **Component-Level:** Failure of one component (e.g., CostController) doesn't crash system

**Blast Radius:**
- **Single Key Failure:** Affects only that key (other keys continue working)
- **Provider Failure:** Affects only that provider (other providers continue working)
- **Component Failure:** System degrades but continues (e.g., cost tracking disabled, routing continues)

**Load Reduction Under Failure:**
- **Rate Limit Detected:** Stop routing to that key, reduce load
- **Provider Down:** Stop routing to that provider, reduce load
- **High Error Rate:** Circuit breaker opens, no requests to failing component
- **Backpressure:** Reject new requests if system overloaded

## Degradation Modes

**Degraded Operation States:**
1. **Cost Tracking Disabled:** CostController fails → Continue routing without cost tracking
2. **Quota Awareness Degraded:** QuotaAwarenessEngine fails → Use simple availability check
3. **Policy Engine Degraded:** PolicyEngine fails → Use default routing policy
4. **Observability Degraded:** ObservabilityManager fails → Continue operation, log to stdout

**Partial Progress:**
- **Streaming Responses:** Return partial response if stream interrupted
- **Cached Responses:** Return cached response if provider fails
- **Degraded Quality:** Use cheaper/faster model if premium model unavailable

## Recovery Strategy

**Automatic Recovery:**
- **Key Recovery:** Monitor throttled keys, automatically restore to Available when cooldown expires
- **Provider Recovery:** Health check failed providers, automatically restore when healthy
- **Circuit Breaker Recovery:** Automatically transition Open → Half-Open → Closed
- **State Reconciliation:** Background job reconciles state inconsistencies

**Recovery Monitoring:**
- **Health Checks:** Periodic health checks for failed components
- **Gradual Reintroduction:** Slowly reintroduce recovered components (start with 10% traffic)
- **Recovery Logging:** Log all recovery events for observability

## Error Handling Examples

**Example 1: Rate Limit with Automatic Retry**
```python
try:
    response = await adapter.execute_request(intent, key)
except RateLimitError as e:
    # Interpret failure semantically
    failure_handler.interpret_failure(e, context)
    # Update key state (Throttled)
    key_manager.update_key_state(key_id, Throttled, cooldown=e.retry_after)
    # Route to different key (automatic retry)
    return await router.route(intent, objective)  # Different key selected
```

**Example 2: All Keys Exhausted**
```python
try:
    response = await router.route(intent, objective)
except NoEligibleKeysError as e:
    # System can refuse work gracefully
    logger.warning("no_keys_available", provider_id="openai", exhausted_keys=3)
    # Return user-friendly error
    raise HTTPException(
        status_code=503,
        detail={
            "error": {
                "message": "All API keys exhausted. Please add keys or wait for quota reset.",
                "code": "NO_KEYS_AVAILABLE",
                "details": {"exhausted_keys": 3}
            }
        }
    )
```

**Example 3: Budget Exceeded**
```python
try:
    response = await router.route(intent, objective)
except BudgetExceededError as e:
    # Proactive enforcement - prevent overspend
    logger.warning("budget_exceeded", scope="global", limit=100, current=99.95)
    # Return user-friendly error
    raise HTTPException(
        status_code=429,
        detail={
            "error": {
                "message": "Budget limit exceeded. Request rejected.",
                "code": "BUDGET_EXCEEDED",
                "details": {"limit": 100, "current": 99.95, "request_cost": 0.10}
            }
        }
    )
```

---

**Select 1-9 or just type your question/feedback:**

1. Proceed to next section (Coding Standards)
2. Challenge assumptions
3. Explore alternatives
4. Deep dive analysis
5. Risk assessment
6. Stakeholder perspective
7. Scenario planning
8. Constraint analysis
9. Expert consultation

Or type your feedback/questions about the Error Handling Strategy section.
