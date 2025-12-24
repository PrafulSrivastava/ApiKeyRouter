# Public API Reference – Developer Consumption Guide

This document describes the public API for the ApiKeyRouter library. It covers only what you need to use the library effectively. Internal implementation details are excluded.

---

## 1. Mental Model (High-Level)

- **The library manages multiple API keys across LLM providers** – You register keys, and the library automatically selects which key to use for each request based on availability, cost, and reliability.

- **You describe what you want, not how to get it** – You provide a `RequestIntent` (model, messages, parameters), and the library handles routing, execution, retries, and error recovery.

- **The library optimizes for your objectives** – You can specify whether to prioritize cost, reliability, fairness, or quality. The library selects keys accordingly.

- **Failures are handled automatically** – If a key fails (rate limit, quota exhausted, network error), the library automatically tries alternative keys. You only need to handle the final result.

- **State is managed internally** – The library tracks key states (available, throttled, exhausted), quota consumption, and usage statistics. You don't manage this manually.

- **Costs are tracked automatically** – Each response includes cost estimates. The library tracks usage across keys without requiring manual accounting.

- **Provider-specific details are abstracted** – You work with a consistent interface (`RequestIntent` → `SystemResponse`) regardless of whether you're using OpenAI, Anthropic, or custom providers.

---

## 2. Required Imports

### Minimal Imports (Most Common Use Case)

```python
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message
from apikeyrouter.domain.models.routing_decision import RoutingObjective, ObjectiveType
from apikeyrouter.domain.models.system_error import SystemError, ErrorCategory
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter
from apikeyrouter.infrastructure.config.settings import RouterSettings
```

### Additional Imports (As Needed)

```python
# For custom provider adapters
from apikeyrouter.domain.interfaces.provider_adapter import ProviderAdapter

# For response inspection
from apikeyrouter.domain.models.system_response import SystemResponse, ResponseMetadata, TokenUsage

# For key management
from apikeyrouter.domain.models.api_key import APIKey, KeyState

# For cost tracking
from apikeyrouter.domain.models.cost_estimate import CostEstimate

# For error handling
from apikeyrouter.domain.components.routing_engine import NoEligibleKeysError
from apikeyrouter.domain.components.key_manager import KeyRegistrationError
```

### What You Should NEVER Import

Do not import internal components that are not part of the public API:

- `apikeyrouter.domain.components.*` (except for exceptions like `NoEligibleKeysError`)
- `apikeyrouter.domain.interfaces.*` (except `ProviderAdapter` if creating custom adapters)
- `apikeyrouter.infrastructure.state_store.*` (internal storage implementations)
- `apikeyrouter.infrastructure.observability.*` (internal logging)
- `apikeyrouter.infrastructure.utils.*` (internal utilities)
- Any module with `_` prefix or marked as private

**Rule of thumb:** If it's not listed in this document's "Public API Surface" section, don't import it directly.

---

## 3. Public API Surface

### Initialization / Setup

#### `ApiKeyRouter.__init__()`

**Signature:**
```python
def __init__(
    self,
    state_store: StateStore | None = None,
    observability_manager: ObservabilityManager | None = None,
    config: RouterSettings | dict[str, Any] | None = None,
) -> None
```

**Purpose:** Create a new router instance. This is your entry point to the library.

**When to call it:** Once at application startup, before registering providers or keys.

**What the library handles automatically:**
- Creates in-memory state store (default)
- Sets up observability/logging (default)
- Loads configuration from environment variables if `config=None`
- Initializes all internal components (KeyManager, RoutingEngine, QuotaAwarenessEngine)

**Common misuse or misunderstanding:**
- **Don't create multiple routers** unless you need separate isolated instances. One router manages all your keys.
- **Don't pass custom `state_store` or `observability_manager`** unless you're implementing custom persistence or logging. The defaults work for most use cases.
- **Configuration is optional** – You can pass `RouterSettings` or a dict, but environment variables work fine for most deployments.

**Example:**
```python
# Simplest initialization
router = ApiKeyRouter()

# With custom configuration
config = RouterSettings(
    max_decisions=5000,
    default_cooldown_seconds=120,
    log_level="INFO"
)
router = ApiKeyRouter(config=config)

# With environment variables (recommended for production)
# Set APIKEYROUTER_MAX_DECISIONS=5000, etc.
router = ApiKeyRouter()  # Automatically loads from env
```

#### `ApiKeyRouter` (async context manager)

**Signature:**
```python
async def __aenter__(self) -> "ApiKeyRouter"
async def __aexit__(self, exc_type, exc_val, exc_tb) -> None
```

**Purpose:** Use the router as an async context manager for automatic cleanup (currently no-op, but reserved for future cleanup operations).

**When to call it:** Optional. Use `async with` if you want explicit lifecycle management.

**What the library handles automatically:** Currently nothing, but this interface is reserved for future resource cleanup.

**Example:**
```python
async with ApiKeyRouter() as router:
    await router.register_provider("openai", OpenAIAdapter())
    # ... use router
# Automatic cleanup (if implemented in future)
```

---

### Provider Registration

#### `ApiKeyRouter.register_provider()`

**Signature:**
```python
async def register_provider(
    self,
    provider_id: str,
    adapter: ProviderAdapter,
    overwrite: bool = False,
) -> None
```

**Purpose:** Register a provider adapter so the router knows how to communicate with a specific LLM provider.

**When to call it:** Once per provider, before registering any keys for that provider. Must be called before `register_key()`.

**What the library handles automatically:**
- Validates the adapter implements all required methods
- Stores the provider-adapter mapping
- Emits observability events for provider registration

**Common misuse or misunderstanding:**
- **You must register a provider before registering keys** – Keys reference a `provider_id`, which must exist.
- **Provider IDs are case-sensitive strings** – Use consistent naming (e.g., "openai", "anthropic").
- **Adapters are stateless** – You can reuse the same adapter instance, or create new ones. The library doesn't care.
- **Use `overwrite=True`** only if you're replacing an existing provider adapter (rare).

**Example:**
```python
# Register OpenAI
openai_adapter = OpenAIAdapter()
await router.register_provider("openai", openai_adapter)

# Register multiple providers
await router.register_provider("openai", OpenAIAdapter())
await router.register_provider("anthropic", AnthropicAdapter())  # If available

# Overwrite existing provider (rare)
await router.register_provider("openai", NewOpenAIAdapter(), overwrite=True)
```

---

### API Key Management

#### `ApiKeyRouter.register_key()`

**Signature:**
```python
async def register_key(
    self,
    key_material: str,
    provider_id: str,
    metadata: dict[str, Any] | None = None,
) -> APIKey
```

**Purpose:** Register an API key for a provider. The library encrypts and stores the key, assigns it a stable ID, and initializes quota tracking.

**When to call it:** Once per API key, after registering the provider. You can register multiple keys for the same provider.

**What the library handles automatically:**
- Encrypts the key material (never stored in plaintext)
- Generates a unique, stable key ID
- Initializes the key state to `Available`
- Sets up quota state tracking
- Emits observability events

**Common misuse or misunderstanding:**
- **The returned `APIKey.id` is what you'll see in responses** – Not the key material itself. The key material is encrypted and never exposed.
- **Metadata is optional** – Use it for provider-specific information (account tier, region, etc.) if needed.
- **Keys are automatically available** – No need to "activate" them. They're ready to use immediately after registration.
- **Register multiple keys for redundancy** – The library will automatically fail over to other keys if one fails.

**Example:**
```python
# Register a single key
key = await router.register_key(
    key_material="sk-your-openai-key-here",
    provider_id="openai"
)
print(f"Registered key ID: {key.id}")

# Register multiple keys for the same provider
await router.register_key("sk-key-1", "openai")
await router.register_key("sk-key-2", "openai")
await router.register_key("sk-key-3", "openai")

# With metadata
await router.register_key(
    key_material="sk-key-4",
    provider_id="openai",
    metadata={"account_tier": "pro", "region": "us-east"}
)
```

---

### Request Routing / Execution

#### `ApiKeyRouter.route()`

**Signature:**
```python
async def route(
    self,
    request_intent: RequestIntent | dict[str, Any],
    objective: RoutingObjective | str | None = None,
) -> SystemResponse
```

**Purpose:** Route a request to an appropriate API key, execute it, and return the normalized response. This is the main method you'll call for every LLM request.

**When to call it:** For every LLM API call you want to make. This replaces direct calls to provider APIs.

**What the library handles automatically:**
- Selects the best key based on the routing objective
- Executes the request via the provider adapter
- Handles retries with alternative keys if the first attempt fails
- Updates quota state after successful requests
- Tracks usage statistics
- Normalizes the response to a consistent format
- Emits observability events

**Common misuse or misunderstanding:**
- **You can pass `RequestIntent` object or a dict** – Both work. Dict is convenient for simple cases.
- **`provider_id` must be in the request** – Either in `RequestIntent.parameters["provider_id"]` or in the dict as `"provider_id"`.
- **The `objective` parameter is optional** – Defaults to "fairness" (load balancing). Pass a string like `"cost"` or `"reliability"`, or a `RoutingObjective` object for advanced control.
- **The library handles all retries** – You don't need to implement retry logic. If a key fails, the library automatically tries other keys (up to 3 attempts).
- **Response is always `SystemResponse`** – Regardless of provider, you get the same structure.

**Example:**
```python
# Using RequestIntent object
intent = RequestIntent(
    model="gpt-4",
    messages=[
        Message(role="user", content="Hello!")
    ],
    parameters={"provider_id": "openai", "temperature": 0.7}
)
response = await router.route(intent)

# Using dict (simpler)
response = await router.route({
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}],
    "provider_id": "openai",
    "parameters": {"temperature": 0.7}
})

# With routing objective
response = await router.route(intent, objective="cost")  # Minimize cost
response = await router.route(intent, objective="reliability")  # Maximize reliability

# Advanced objective
objective = RoutingObjective(
    primary="cost",
    secondary=["reliability"],
    constraints={"min_reliability": 0.95}
)
response = await router.route(intent, objective=objective)
```

---

### Policy / Configuration

#### `RouterSettings`

**Signature:**
```python
class RouterSettings(BaseSettings):
    max_decisions: int = 1000
    max_transitions: int = 1000
    default_cooldown_seconds: int = 60
    quota_default_cooldown_seconds: int = 60
    log_level: str = "INFO"
    encryption_key: str | None = None
```

**Purpose:** Configuration settings for the router. Controls state store limits, cooldown periods, logging, and encryption.

**When to use it:** When you need to customize behavior beyond defaults. Most applications can use environment variables instead.

**What the library handles automatically:**
- Loads from environment variables (prefix: `APIKEYROUTER_`)
- Validates all settings
- Applies defaults if not specified

**Common misuse or misunderstanding:**
- **Environment variables are preferred** – Set `APIKEYROUTER_MAX_DECISIONS=5000` instead of passing `RouterSettings` in code.
- **`encryption_key` is required in production** – Set `APIKEYROUTER_ENCRYPTION_KEY` environment variable. In development, the library may auto-generate (not recommended for production).
- **Most settings have sensible defaults** – You rarely need to change them unless you have specific requirements.

**Example:**
```python
# From environment variables (recommended)
# Set: APIKEYROUTER_MAX_DECISIONS=5000
# Set: APIKEYROUTER_LOG_LEVEL=DEBUG
router = ApiKeyRouter()  # Automatically loads from env

# From code
config = RouterSettings(
    max_decisions=5000,
    log_level="DEBUG"
)
router = ApiKeyRouter(config=config)

# From dict
config_dict = {"max_decisions": 5000, "log_level": "DEBUG"}
router = ApiKeyRouter(config=config_dict)
```

#### `RoutingObjective`

**Signature:**
```python
class RoutingObjective(BaseModel):
    primary: str  # "cost", "reliability", "fairness", "quality", "latency"
    secondary: list[str] = []
    constraints: dict[str, Any] = {}
    weights: dict[str, float] = {}
```

**Purpose:** Define what the routing engine should optimize for when selecting keys.

**When to use it:** When you need fine-grained control over routing decisions. For simple cases, pass a string like `"cost"` or `"reliability"`.

**What the library handles automatically:**
- Validates objective types
- Applies multi-objective optimization if secondary objectives are specified
- Enforces constraints (e.g., minimum reliability threshold)

**Common misuse or misunderstanding:**
- **Simple string is usually enough** – `objective="cost"` works for most cases. You don't need a `RoutingObjective` object unless you need advanced features.
- **Primary objective is required** – Secondary objectives are optional and used for tie-breaking.
- **Constraints are hard limits** – If a constraint is violated, the key is excluded from consideration.

**Example:**
```python
# Simple (most common)
response = await router.route(intent, objective="cost")

# Advanced
objective = RoutingObjective(
    primary="cost",
    secondary=["reliability"],
    constraints={"min_reliability": 0.95, "max_cost_per_request": 0.01},
    weights={"cost": 0.7, "reliability": 0.3}
)
response = await router.route(intent, objective=objective)
```

---

### Observability / Control

#### `SystemResponse`

**Signature:**
```python
class SystemResponse(BaseModel):
    content: str  # LLM response text
    metadata: ResponseMetadata  # Tokens, timing, model used, etc.
    cost: CostEstimate | None  # Cost estimate
    key_used: str  # ID of key that was used
    request_id: str  # Unique request identifier
```

**Purpose:** Normalized response from any provider. All providers return this same structure.

**When to use it:** This is what `route()` returns. Inspect it to get the LLM response, token usage, cost, and metadata.

**What the library handles automatically:**
- Normalizes all provider responses to this format
- Populates all fields (content, metadata, cost, key_used, request_id)
- Ensures consistent structure regardless of provider

**Common misuse or misunderstanding:**
- **`content` is the LLM response text** – This is what you display to users.
- **`metadata.tokens_used` contains token counts** – Use `response.metadata.tokens_used.total_tokens` for total usage.
- **`cost` may be `None`** – Not all providers or requests have cost estimates. Check before using.
- **`key_used` is the key ID, not the key material** – The actual key material is never exposed.

**Example:**
```python
response = await router.route(intent)

# Get LLM response
print(response.content)

# Get token usage
tokens = response.metadata.tokens_used.total_tokens
print(f"Used {tokens} tokens")

# Get cost (if available)
if response.cost:
    print(f"Cost: ${response.cost.amount}")

# Get key that was used
print(f"Key ID: {response.key_used}")

# Get request ID for correlation
print(f"Request ID: {response.request_id}")
```

#### `ResponseMetadata`

**Signature:**
```python
class ResponseMetadata(BaseModel):
    model_used: str
    tokens_used: TokenUsage
    response_time_ms: int
    provider_id: str
    timestamp: datetime
    finish_reason: str | None
    request_id: str | None
    correlation_id: str | None
    additional_metadata: dict[str, Any]
```

**Purpose:** Detailed metadata about the response for observability and debugging.

**When to use it:** Access via `response.metadata` to inspect timing, tokens, model used, etc.

**What the library handles automatically:**
- Populates all timing information
- Tracks token usage (input and output)
- Records which model was actually used
- Includes correlation IDs for distributed tracing

**Example:**
```python
metadata = response.metadata
print(f"Model: {metadata.model_used}")
print(f"Response time: {metadata.response_time_ms}ms")
print(f"Input tokens: {metadata.tokens_used.input_tokens}")
print(f"Output tokens: {metadata.tokens_used.output_tokens}")
print(f"Total tokens: {metadata.tokens_used.total_tokens}")
```

---

## 4. Typical Usage Flow

### Step 1: Initialize the Router

```python
from apikeyrouter import ApiKeyRouter

router = ApiKeyRouter()
```

**What's required:** Nothing. Defaults work for most cases.

**What's optional:** Pass `RouterSettings` or a config dict if you need custom settings. Set environment variables for production.

### Step 2: Register Providers

```python
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

await router.register_provider("openai", OpenAIAdapter())
```

**What's required:** Register at least one provider before registering keys.

**What's optional:** Register multiple providers if you use multiple LLM providers.

### Step 3: Register API Keys

```python
await router.register_key("sk-your-key-1", "openai")
await router.register_key("sk-your-key-2", "openai")
await router.register_key("sk-your-key-3", "openai")
```

**What's required:** Register at least one key per provider you want to use.

**What's optional:** Register multiple keys for redundancy and load distribution. Add metadata if you need provider-specific information.

### Step 4: Make Requests

```python
from apikeyrouter.domain.models.request_intent import RequestIntent, Message

intent = RequestIntent(
    model="gpt-4",
    messages=[Message(role="user", content="Hello!")],
    parameters={"provider_id": "openai", "temperature": 0.7}
)

response = await router.route(intent)
print(response.content)
```

**What's required:**
- `model`: The LLM model identifier
- `messages`: At least one message
- `provider_id`: In `parameters` dict or as a separate field

**What's optional:**
- `parameters`: Temperature, max_tokens, etc. (provider-specific)
- `objective`: Routing objective (defaults to "fairness")

### Step 5: Handle Responses and Errors

```python
from apikeyrouter.domain.models.system_error import SystemError, ErrorCategory
from apikeyrouter.domain.components.routing_engine import NoEligibleKeysError

try:
    response = await router.route(intent)
    print(response.content)
except NoEligibleKeysError:
    # No keys available (all exhausted, throttled, or disabled)
    print("No keys available. Add more keys or wait for quota reset.")
except SystemError as e:
    if e.category == ErrorCategory.RateLimitError:
        # Rate limited (library already tried other keys)
        print(f"Rate limited. Retry after {e.retry_after} seconds.")
    elif e.category == ErrorCategory.AuthenticationError:
        # Invalid API key
        print("Authentication failed. Check your API keys.")
    else:
        # Other provider errors
        print(f"Error: {e.message}")
```

**What happens on failures:**
- **Automatic retry with alternative keys** – If a key fails (rate limit, network error, etc.), the library automatically tries other keys (up to 3 attempts).
- **You only see the final result** – Either a successful `SystemResponse` or an exception if all attempts failed.
- **Key states are updated automatically** – Failed keys are marked as throttled/exhausted. The library tracks this internally.

**What you need to handle:**
- **`NoEligibleKeysError`** – All keys are unavailable. You may need to wait or add more keys.
- **`SystemError`** – Final error after all retries. Check `error.category` and `error.retryable` to decide how to proceed.

---

## 5. "You Don't Need to Care About This"

The following are internal mechanisms that the library handles automatically. You can safely ignore them:

### Internal State Management

- **Key state transitions** – The library automatically manages key states (Available → Throttled → Recovering → Available). You never manually set key states.
- **Quota tracking** – The library tracks quota consumption, exhaustion predictions, and capacity estimates. This is all internal.
- **State store implementation** – Whether the library uses in-memory storage, Redis, or MongoDB is an implementation detail. The API is the same.

### Routing Algorithms

- **Key selection logic** – How the library scores and selects keys is internal. You specify objectives, and the library handles the rest.
- **Retry strategies** – The library automatically retries with alternative keys. You don't configure retry logic.
- **Load balancing** – Fairness routing automatically distributes load. You don't need to implement round-robin or other strategies.

### Background Processes

- **Quota state updates** – The library updates quota state after each request. This happens automatically.
- **Health checks** – Provider health is checked internally. You don't need to poll or check health manually.
- **Observability events** – Logging, metrics, and tracing are handled internally. You can configure log levels, but the mechanics are automatic.

### Internal Components

- **KeyManager, RoutingEngine, QuotaAwarenessEngine** – These are internal components. You don't call them directly. The `ApiKeyRouter` class is your only interface.
- **StateStore implementations** – InMemoryStateStore, RedisStore, etc. are internal. You don't instantiate them unless you're implementing custom persistence (advanced use case).
- **Provider adapter internals** – How adapters convert requests/responses is internal. You use `OpenAIAdapter()`, but you don't need to know how it works.

### Error Recovery

- **Automatic failover** – If a key fails, the library automatically tries other keys. You don't implement failover logic.
- **Cooldown management** – Throttled keys are automatically put in cooldown. The library tracks when they're ready again.
- **Quota exhaustion handling** – When keys are exhausted, the library automatically excludes them from routing until quota resets.

### Configuration Internals

- **Encryption** – Key material is automatically encrypted. You don't handle encryption/decryption.
- **Validation** – Request validation happens automatically. Invalid requests raise `ValueError` before execution.
- **Settings loading** – Environment variable loading and validation is automatic.

**Bottom line:** Use `ApiKeyRouter.register_provider()`, `register_key()`, and `route()`. Everything else is handled for you.

---

## Appendix: Exception Reference

### `SystemError`

**When raised:** By provider adapters when provider API calls fail.

**Categories:**
- `ErrorCategory.AuthenticationError` – Invalid API key (401)
- `ErrorCategory.RateLimitError` – Rate limit exceeded (429)
- `ErrorCategory.QuotaExceededError` – Quota exhausted
- `ErrorCategory.ProviderError` – Provider server error (5xx)
- `ErrorCategory.TimeoutError` – Request timeout
- `ErrorCategory.NetworkError` – Network connectivity issue
- `ErrorCategory.ValidationError` – Invalid request (400)
- `ErrorCategory.BudgetExceededError` – Budget limit exceeded
- `ErrorCategory.UnknownError` – Unclassified error

**Properties:**
- `category: ErrorCategory` – Error category
- `message: str` – Human-readable message
- `retryable: bool` – Whether the error is retryable
- `retry_after: int | None` – Retry after this many seconds (from Retry-After header)
- `details: dict[str, Any]` – Additional error details

**Example:**
```python
try:
    response = await router.route(intent)
except SystemError as e:
    if e.retryable and e.retry_after:
        await asyncio.sleep(e.retry_after)
        # Retry logic (library already tried other keys)
    print(f"Error: {e.message} ({e.category.value})")
```

### `NoEligibleKeysError`

**When raised:** When no keys are available for routing (all exhausted, throttled, disabled, or invalid).

**Example:**
```python
try:
    response = await router.route(intent)
except NoEligibleKeysError:
    print("No keys available. Add more keys or wait.")
```

### `KeyRegistrationError`

**When raised:** When key registration fails (invalid key material, provider not registered, etc.).

**Example:**
```python
try:
    key = await router.register_key("invalid-key", "openai")
except KeyRegistrationError as e:
    print(f"Registration failed: {e}")
```

### `ValueError`

**When raised:** When request validation fails (missing required fields, invalid parameters, etc.).

**Example:**
```python
try:
    response = await router.route({"model": "gpt-4"})  # Missing messages
except ValueError as e:
    print(f"Invalid request: {e}")
```

---

## Appendix: Model Reference

### `RequestIntent`

**Fields:**
- `model: str` – LLM model identifier (required)
- `messages: list[Message]` – Conversation messages (required, at least 1)
- `parameters: dict[str, Any]` – Request parameters (optional)
  - Must include `"provider_id"` in parameters or pass separately

**Example:**
```python
intent = RequestIntent(
    model="gpt-4",
    messages=[Message(role="user", content="Hello!")],
    parameters={"provider_id": "openai", "temperature": 0.7, "max_tokens": 100}
)
```

### `Message`

**Fields:**
- `role: str` – "system", "user", "assistant", or "tool" (required)
- `content: str` – Message content (required)
- `name: str | None` – Optional name (e.g., function name)
- `function_call: dict[str, Any] | None` – Function call information
- `tool_calls: list[dict[str, Any]] | None` – Tool calls
- `tool_call_id: str | None` – Tool call ID (for tool role)

**Example:**
```python
user_msg = Message(role="user", content="What is 2+2?")
system_msg = Message(role="system", content="You are a helpful assistant")
```

### `APIKey`

**Fields (read-only after registration):**
- `id: str` – Stable key identifier (not the key material)
- `state: KeyState` – Current state (Available, Throttled, Exhausted, etc.)
- `provider_id: str` – Provider this key belongs to
- `usage_count: int` – Total requests made with this key
- `failure_count: int` – Total failures encountered
- `last_used_at: datetime | None` – Last successful usage timestamp
- `metadata: dict[str, Any]` – Provider-specific metadata

**Note:** You don't construct `APIKey` objects directly. They're returned from `register_key()`.

### `KeyState`

**Values:**
- `Available` – Key is ready to use
- `Throttled` – Key is rate-limited (in cooldown)
- `Exhausted` – Key quota is exhausted
- `Recovering` – Key is recovering from exhaustion
- `Disabled` – Key is manually disabled
- `Invalid` – Key is invalid (authentication failure)

**Note:** You don't set key states manually. The library manages them automatically.

---

## Summary

**What you need to know:**
1. Create `ApiKeyRouter()`
2. Register providers with `register_provider()`
3. Register keys with `register_key()`
4. Make requests with `route()`
5. Handle `SystemError` and `NoEligibleKeysError`

**What you can ignore:**
- Internal state management
- Routing algorithms
- Background processes
- Component internals
- Error recovery mechanics

The library handles complexity so you don't have to.

