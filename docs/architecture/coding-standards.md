# Coding Standards

These standards are **MANDATORY for AI agents** and focus on project-specific conventions that prevent common mistakes. General best practices (SOLID, clean code) are assumed.

## Core Standards

**Languages & Runtimes:**
- Python 3.11+ (type hints required for all public APIs)
- Async/await for all I/O operations (no blocking I/O)
- Type checking with mypy (strict mode enabled)

**Style & Linting:**
- **Formatter:** ruff (format on save)
- **Linter:** ruff (replaces flake8, isort, etc.)
- **Type Checker:** mypy (strict mode)
- **Line Length:** 100 characters (not 80)
- **Import Sorting:** ruff (automatic)

**Test Organization:**
- Test files: `test_*.py` or `*_test.py`
- Test location: Mirror source structure in `tests/` directory
- Test naming: `test_<functionality>_<scenario>`

## Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| **Classes** | PascalCase | `ApiKeyRouter`, `QuotaAwarenessEngine` |
| **Functions/Methods** | snake_case | `route_request`, `get_eligible_keys` |
| **Constants** | UPPER_SNAKE_CASE | `MAX_RETRY_ATTEMPTS`, `DEFAULT_TIMEOUT` |
| **Private Methods** | `_leading_underscore` | `_calculate_score`, `_validate_state` |
| **Type Variables** | PascalCase | `T`, `KeyType`, `ProviderType` |
| **Async Functions** | snake_case (no `async_` prefix) | `route`, `execute_request` (not `async_route`) |
| **Provider Adapters** | `{Provider}Adapter` | `OpenAIAdapter`, `AnthropicAdapter` |
| **Domain Models** | PascalCase (no suffix) | `APIKey`, `QuotaState` (not `APIKeyModel`) |

## Critical Rules

**Rule 1: Never Log API Key Material**
- **Description:** API keys (even encrypted) must NEVER appear in logs, error messages, or exceptions
- **Enforcement:** Code review + automated check
- **Example Violation:** `logger.error(f"Key {key_material} failed")`
- **Correct:** `logger.error(f"Key {key_id} failed")`

**Rule 2: All State Transitions Must Be Explicit**
- **Description:** State changes must go through KeyManager/QuotaAwarenessEngine, never direct assignment
- **Enforcement:** Private state fields, public transition methods only
- **Example Violation:** `key.state = Throttled`
- **Correct:** `key_manager.update_key_state(key_id, Throttled, reason="rate_limit")`

**Rule 3: Provider-Specific Logic Only in Adapters**
- **Description:** Core domain logic must never branch on provider identity
- **Enforcement:** No `if provider == "openai"` outside adapter classes
- **Example Violation:** `if provider_id == "openai": return openai_specific_logic()`
- **Correct:** `adapter.execute_request(intent)` (adapter handles provider-specific logic)

**Rule 4: All Async I/O Must Use Async/Await**
- **Description:** No blocking I/O operations (requests, time.sleep, etc.)
- **Enforcement:** Use httpx (async), asyncio.sleep, async database drivers
- **Example Violation:** `requests.get(url)` or `time.sleep(1)`
- **Correct:** `await httpx.get(url)` or `await asyncio.sleep(1)`

**Rule 5: Routing Decisions Must Be Explainable**
- **Description:** Every routing decision must include an explanation field
- **Enforcement:** RoutingDecision model requires explanation field
- **Example Violation:** `RoutingDecision(key_id="key1", explanation=None)`
- **Correct:** `RoutingDecision(key_id="key1", explanation="Lowest cost while maintaining reliability")`

**Rule 6: Cost Estimates Before Execution**
- **Description:** Cost must be estimated before making provider API calls
- **Enforcement:** CostController.estimate_request_cost() called before adapter.execute_request()
- **Example Violation:** `response = await adapter.execute(); cost = calculate_cost(response)`
- **Correct:** `cost_estimate = await cost_controller.estimate(); response = await adapter.execute()`

**Rule 7: No Direct Database Queries in Domain Layer**
- **Description:** Domain components use StateStore interface, never direct database access
- **Enforcement:** StateStore abstraction, no database imports in domain layer
- **Example Violation:** `db.collection.find_one({"key_id": key_id})` in KeyManager
- **Correct:** `state_store.get_key(key_id)` (StateStore implementation handles database)

**Rule 8: All Exceptions Must Be Semantic**
- **Description:** Use custom exception types (RateLimitError, not generic Exception)
- **Enforcement:** Exception hierarchy, no bare `except:` clauses
- **Example Violation:** `except Exception as e: handle_error(e)`
- **Correct:** `except RateLimitError as e: handle_rate_limit(e)`

**Rule 9: Configuration via Environment Variables or Pydantic Settings**
- **Description:** No hardcoded configuration values, use pydantic-settings
- **Enforcement:** All config through Settings class or environment variables
- **Example Violation:** `timeout = 30` (hardcoded)
- **Correct:** `timeout = settings.request_timeout` (from pydantic-settings)

**Rule 10: State Store Must Support In-Memory Mode**
- **Description:** StateStore implementations must work without external dependencies (in-memory default)
- **Enforcement:** MemoryStore is default, Redis/MongoDB are optional
- **Example Violation:** Requiring MongoDB connection for library to work
- **Correct:** Library works in-memory, MongoDB optional for persistence

## Python-Specific Guidelines

**Type Hints:**
- **Required:** All public APIs (functions, methods, class attributes)
- **Optional:** Private methods (but recommended)
- **Style:** Use `typing` module, prefer `list[str]` over `List[str]` (Python 3.9+)
- **Async:** Always type async functions: `async def route(...) -> SystemResponse:`

**Async/Await:**
- **Required:** All I/O operations (HTTP, database, file system)
- **Pattern:** Use `async with` for context managers, `async for` for async iterators
- **Error:** Never mix sync and async (no `asyncio.run()` in async functions)

**Pydantic Models:**
- **Usage:** All domain models use Pydantic (validation, serialization)
- **Style:** Use `Field()` for validation, `ConfigDict` for model config
- **Example:**
  ```python
  class APIKey(BaseModel):
      id: str = Field(..., description="Unique key identifier")
      state: KeyState = Field(default=KeyState.Available)
      model_config = ConfigDict(frozen=True)  # Immutable
  ```

**Error Handling:**
- **Pattern:** Use specific exceptions, not generic Exception
- **Logging:** Log errors with context (request_id, key_id, etc.)
- **Reraise:** Use `raise ... from e` for exception chaining

**Testing:**
- **Framework:** pytest with pytest-asyncio for async tests
- **Fixtures:** Use pytest fixtures for test data and mocks
- **Async Tests:** Mark async test functions with `@pytest.mark.asyncio`

## Code Organization

**Imports:**
- **Order:** Standard library → Third-party → Local (enforced by ruff)
- **Style:** Absolute imports preferred, relative imports only for same package
- **Example:**
  ```python
  from typing import Optional
  from pydantic import BaseModel
  from apikeyrouter.domain.models import APIKey
  ```

**File Structure:**
- **One class per file:** For major components (KeyManager, RoutingEngine)
- **Related classes:** Can be in same file if tightly coupled (models, exceptions)
- **Module organization:** Group related functionality (all adapters in `adapters/`)

**Documentation:**
- **Docstrings:** Required for all public APIs (classes, methods, functions)
- **Style:** Google style docstrings
- **Type hints:** Prefer type hints over docstring type annotations
- **Example:**
  ```python
  def route(
      self,
      request_intent: RequestIntent,
      objective: Optional[RoutingObjective] = None
  ) -> SystemResponse:
      """Route request intelligently across available keys.
      
      Args:
          request_intent: Request to route
          objective: Optional routing objective (cost, reliability, etc.)
          
      Returns:
          SystemResponse with completion and metadata
          
      Raises:
          NoEligibleKeysError: If no keys available for routing
          BudgetExceededError: If request would exceed budget
      """
  ```

---

**Select 1-9 or just type your question/feedback:**

1. Proceed to next section (Test Strategy and Standards)
2. Challenge assumptions
3. Explore alternatives
4. Deep dive analysis
5. Risk assessment
6. Stakeholder perspective
7. Scenario planning
8. Constraint analysis
9. Expert consultation

Or type your feedback/questions about the Coding Standards section.
