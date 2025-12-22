# Migration Guide: From LiteLLM

This guide helps you migrate from [LiteLLM](https://github.com/BerriAI/litellm) to ApiKeyRouter.

## Overview

LiteLLM is a Python library that provides a unified interface for multiple LLM providers. ApiKeyRouter provides similar functionality with additional intelligent routing, quota awareness, and cost control features.

### Key Differences

| Aspect | LiteLLM | ApiKeyRouter |
|--------|---------|--------------|
| **Focus** | LLM provider abstraction | Intelligent API key routing |
| **Quota Management** | Reactive counting | Predictive, forward-looking |
| **Routing** | Simple fallback | Multi-objective optimization |
| **Cost Control** | Post-execution tracking | Pre-execution estimation & budgets |
| **State Management** | Implicit | Explicit state machine |
| **Provider Coverage** | Wide (100+ providers) | Core providers (extensible) |
| **Explainability** | None | Routing explanations |

## Migration Steps

### Step 1: Install ApiKeyRouter

```bash
# Install the core library
pip install apikeyrouter-core

# Or from source
git clone https://github.com/your-org/ApiKeyRouter.git
cd ApiKeyRouter/packages/core
poetry install
```

### Step 2: Migrate Provider Setup

#### LiteLLM Setup

```python
# LiteLLM
import litellm

# Set API keys
os.environ["OPENAI_API_KEY"] = "sk-key-1"
os.environ["ANTHROPIC_API_KEY"] = "sk-key-2"

# Use unified API
response = litellm.completion(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

#### ApiKeyRouter Setup

```python
# ApiKeyRouter
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter

router = ApiKeyRouter()

# Register provider
await router.register_provider("openai", OpenAIAdapter())

# Register keys
await router.register_key("sk-key-1", "openai")
await router.register_key("sk-key-2", "openai")

# Use unified API
intent = RequestIntent(
    model="gpt-4",
    messages=[Message(role="user", content="Hello!")],
    provider_id="openai"
)
response = await router.route(intent)
```

### Step 3: Update API Calls

#### Before (LiteLLM)

```python
import litellm

# Simple completion
response = litellm.completion(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "Hello!"}
    ],
    temperature=0.7,
    max_tokens=100
)

print(response.choices[0].message.content)
```

#### After (ApiKeyRouter)

```python
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message

# Simple completion
intent = RequestIntent(
    model="gpt-4",
    messages=[Message(role="user", content="Hello!")],
    provider_id="openai",
    parameters={
        "temperature": 0.7,
        "max_tokens": 100
    }
)
response = await router.route(intent)

print(response.content)
```

### Step 4: Handle Multiple Providers

#### Before (LiteLLM)

```python
import litellm

# LiteLLM automatically routes based on model name
response = litellm.completion(
    model="gpt-4",  # Routes to OpenAI
    messages=[{"role": "user", content": "Hello!"}]
)

response = litellm.completion(
    model="claude-3-opus",  # Routes to Anthropic
    messages=[{"role": "user", "content": "Hello!"}]
)
```

#### After (ApiKeyRouter)

```python
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter
# from apikeyrouter.infrastructure.adapters.anthropic_adapter import AnthropicAdapter

# Register multiple providers
await router.register_provider("openai", OpenAIAdapter())
# await router.register_provider("anthropic", AnthropicAdapter())

# Route to specific provider
intent = RequestIntent(
    model="gpt-4",
    messages=[Message(role="user", content="Hello!")],
    provider_id="openai"  # Explicit provider selection
)
response = await router.route(intent)
```

### Step 5: Configure Fallback Behavior

#### Before (LiteLLM)

```python
import litellm

# LiteLLM fallback
response = litellm.completion(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}],
    fallbacks=["gpt-3.5-turbo", "claude-3-opus"]
)
```

#### After (ApiKeyRouter)

```python
# ApiKeyRouter automatic failover
# If first key fails, automatically tries next eligible key
try:
    response = await router.route(intent, objective="reliability")
except NoEligibleKeysError:
    # All keys exhausted - handle gracefully
    print("No keys available")
```

### Step 6: Add Advanced Features (Optional)

ApiKeyRouter provides features not available in LiteLLM:

#### Cost Optimization

```python
# Route with cost optimization
response = await router.route(intent, objective="cost")
# Automatically selects cheapest available key
```

#### Budget Enforcement

```python
from apikeyrouter.domain.models.budget import BudgetScope, EnforcementMode, TimeWindow
from decimal import Decimal

# Set daily budget
budget = await router.cost_controller.create_budget(
    scope=BudgetScope.Global,
    limit=Decimal("100.00"),
    period=TimeWindow.Daily,
    enforcement_mode=EnforcementMode.Hard
)

# Requests that would exceed budget are automatically rejected
```

#### Quota Awareness

```python
# ApiKeyRouter automatically tracks quota and predicts exhaustion
response = await router.route(intent)

# Check quota state
quota_state = await router.quota_awareness_engine.get_quota_state(key_id)
print(f"Capacity state: {quota_state.capacity_state}")
print(f"Remaining: {quota_state.remaining_capacity.value}")
```

## Code Examples

### Example 1: Basic Completion

#### Before (LiteLLM)

```python
import litellm

response = litellm.completion(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)
```

#### After (ApiKeyRouter)

```python
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message

intent = RequestIntent(
    model="gpt-4",
    messages=[
        Message(role="system", content="You are a helpful assistant"),
        Message(role="user", content="Hello!")
    ],
    provider_id="openai"
)
response = await router.route(intent)

print(response.content)
```

### Example 2: Streaming

#### Before (LiteLLM)

```python
import litellm

response = litellm.completion(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

#### After (ApiKeyRouter)

```python
# Streaming support depends on adapter implementation
# Check adapter capabilities
capabilities = adapter.get_capabilities()
if capabilities.supports_streaming:
    async for chunk in router.route_stream(intent):
        print(chunk, end="", flush=True)
else:
    # Fallback to non-streaming
    response = await router.route(intent)
    print(response.content)
```

### Example 3: Error Handling

#### Before (LiteLLM)

```python
import litellm
from litellm import RateLimitError, InvalidRequestError

try:
    response = litellm.completion(
        model="gpt-4",
        messages=[{"role": "user", "content": "Hello!"}]
    )
except RateLimitError as e:
    print(f"Rate limit: {e}")
    # Manual retry logic
except InvalidRequestError as e:
    print(f"Invalid request: {e}")
except Exception as e:
    print(f"Error: {e}")
```

#### After (ApiKeyRouter)

```python
from apikeyrouter.domain.components.routing_engine import NoEligibleKeysError
from apikeyrouter.domain.models.system_error import SystemError, ErrorCategory

try:
    response = await router.route(intent)
except NoEligibleKeysError as e:
    # All keys exhausted or rate limited
    print(f"No keys available: {e}")
except SystemError as e:
    if e.category == ErrorCategory.RateLimitError:
        # Automatic retry with different key already attempted
        print(f"Rate limit: {e.message}")
        if e.retry_after:
            await asyncio.sleep(e.retry_after)
    elif e.category == ErrorCategory.ValidationError:
        print(f"Invalid request: {e.message}")
    else:
        print(f"Error: {e.message}")
```

### Example 4: Multiple Keys

#### Before (LiteLLM)

```python
import litellm

# LiteLLM uses environment variables or config
os.environ["OPENAI_API_KEY"] = "sk-key-1"
# LiteLLM doesn't have built-in multi-key routing
```

#### After (ApiKeyRouter)

```python
# Register multiple keys for same provider
await router.register_key("sk-key-1", "openai")
await router.register_key("sk-key-2", "openai")
await router.register_key("sk-key-3", "openai")

# Automatic routing across keys
response = await router.route(intent, objective="fairness")
# Automatically distributes load across keys
```

## API Differences

### Model Selection

| Feature | LiteLLM | ApiKeyRouter |
|---------|---------|--------------|
| **Model Format** | `"gpt-4"`, `"claude-3-opus"` | `"gpt-4"` (with explicit provider) |
| **Provider Selection** | Implicit (from model name) | Explicit (via `provider_id`) |
| **Fallback** | Model-level fallback | Key-level automatic failover |

### Response Format

| Aspect | LiteLLM | ApiKeyRouter |
|--------|---------|--------------|
| **Response Object** | `litellm.ModelResponse` | `SystemResponse` |
| **Content Access** | `response.choices[0].message.content` | `response.content` |
| **Metadata** | `response.usage`, `response.model` | `response.metadata` |
| **Cost** | `response.cost` | `response.cost.amount` |

### Configuration

| Feature | LiteLLM | ApiKeyRouter |
|---------|---------|--------------|
| **API Keys** | Environment variables | Code or API |
| **Settings** | `litellm.set_verbose=True` | `RouterSettings(log_level="DEBUG")` |
| **Custom Headers** | `litellm.headers={}` | Via adapter configuration |

## Troubleshooting

### Issue: Provider Not Supported

**Problem:** LiteLLM supports a provider that ApiKeyRouter doesn't yet.

**Solution:**
1. Check [supported providers](../user-guide.md#supported-providers)
2. Create custom adapter (see [API Reference](../api/API_REFERENCE.md#provideradapter))
3. Request provider support on GitHub

### Issue: Different Response Format

**Problem:** Response format differs from LiteLLM.

**Solution:**
```python
# LiteLLM format
content = response.choices[0].message.content

# ApiKeyRouter format
content = response.content

# Create adapter function if needed
def litellm_compat_response(api_response):
    """Convert ApiKeyRouter response to LiteLLM-like format."""
    return {
        "choices": [{
            "message": {
                "content": api_response.content
            }
        }],
        "usage": {
            "total_tokens": api_response.metadata.tokens_used.total_tokens
        },
        "model": api_response.metadata.model
    }
```

### Issue: Missing Provider Coverage

**Problem:** LiteLLM has 100+ providers, ApiKeyRouter has fewer.

**Solution:**
- ApiKeyRouter focuses on core providers with intelligent routing
- Additional providers can be added via custom adapters
- Check roadmap for planned provider support

### Issue: Streaming Not Working

**Problem:** Streaming behaves differently than LiteLLM.

**Solution:**
```python
# Check adapter capabilities
capabilities = adapter.get_capabilities()
if not capabilities.supports_streaming:
    # Use non-streaming fallback
    response = await router.route(intent)
```

## Feature Parity

### ✅ Fully Supported

- Unified API for multiple providers
- Multiple key support
- Automatic failover
- Error handling
- Response normalization
- Library mode

### ⚠️ Partially Supported

- **Provider Coverage**: LiteLLM has more providers, but ApiKeyRouter has intelligent routing
- **Streaming**: Depends on adapter implementation
- **Function Calling**: Depends on adapter implementation

### ❌ Not Yet Supported

- **100+ Provider Coverage**: ApiKeyRouter focuses on core providers
- **Some LiteLLM-specific Features**: Check adapter capabilities

### ✅ Additional Features (Not in LiteLLM)

- Predictive quota management
- Cost optimization routing
- Budget enforcement
- Multi-objective routing
- Routing explanations
- Explicit state management
- Proxy service mode

## Next Steps

1. **Test the migration** with your existing code
2. **Update error handling** to use ApiKeyRouter exceptions
3. **Configure routing objectives** based on your priorities
4. **Set up budgets** if cost control is important
5. **Read the [User Guide](./user-guide.md)** for advanced features

## Getting Help

- **Documentation**: See [docs/](../) for detailed documentation
- **API Reference**: See [docs/api/API_REFERENCE.md](../api/API_REFERENCE.md)
- **Examples**: See [docs/examples/](../examples/) for code examples
- **Issues**: Open an issue on GitHub for questions or problems

