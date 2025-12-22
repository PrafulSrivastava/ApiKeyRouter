# External APIs

The system routes requests to external API providers. This section documents the key external APIs that will be integrated. The provider abstraction layer enables adding new providers through adapters without core changes.

## OpenAI API

**Purpose:** Primary LLM provider for chat completions and other AI services.

**Documentation:** https://platform.openai.com/docs/api-reference

**Base URL(s):**
- `https://api.openai.com/v1` - Production API
- `https://api.openai.com/v1` - (No separate staging, use API keys for environment separation)

**Authentication:**
- **Method:** Bearer token (API key in `Authorization` header)
- **Format:** `Authorization: Bearer sk-...`
- **Key Management:** API keys obtained from OpenAI dashboard, stored securely in system

**Rate Limits:**
- **Tier-based:** Limits vary by account tier (Free, Pay-as-you-go, Team, Enterprise)
- **Requests per minute (RPM):** Varies (e.g., 3,500 RPM for GPT-4, 10,000 RPM for GPT-3.5)
- **Tokens per minute (TPM):** Model-specific (e.g., 40,000 TPM for GPT-4, 1,000,000 TPM for GPT-3.5)
- **Daily limits:** Account-specific
- **Error Response:** `429 Too Many Requests` with `Retry-After` header

**Key Endpoints Used:**
- `POST /chat/completions` - Chat completions (primary endpoint)
- `POST /completions` - Legacy completions endpoint
- `POST /embeddings` - Text embeddings
- `GET /models` - List available models

**Integration Notes:**
- **Cost Model:** Per-token pricing (input/output tokens priced differently)
- **Streaming Support:** Yes, via `stream: true` parameter
- **Function Calling:** Supported via `tools` parameter
- **Response Format:** JSON with `choices`, `usage`, `model` fields
- **Error Handling:** Standard HTTP status codes (400, 401, 429, 500)
- **Quota Interpretation:** 429 errors indicate rate limit; retry after `Retry-After` seconds
- **Cost Calculation:** `(input_tokens * input_price) + (output_tokens * output_price)` per model

**Pricing Structure (Example - subject to change):**
- GPT-4: ~$0.03/1K input tokens, ~$0.06/1K output tokens
- GPT-3.5-turbo: ~$0.0015/1K input tokens, ~$0.002/1K output tokens
- Pricing varies by model and may change

## Anthropic API

**Purpose:** Alternative LLM provider (Claude models) for chat completions.

**Documentation:** https://docs.anthropic.com/claude/reference

**Base URL(s):**
- `https://api.anthropic.com/v1` - Production API

**Authentication:**
- **Method:** Bearer token (API key in `x-api-key` header)
- **Format:** `x-api-key: sk-ant-...`
- **Key Management:** API keys obtained from Anthropic console, stored securely

**Rate Limits:**
- **Tier-based:** Limits vary by account tier
- **Requests per minute (RPM):** Varies (e.g., 50 RPM for Claude 3 Opus)
- **Tokens per minute (TPM):** Model-specific (e.g., 40,000 TPM for Claude 3 Opus)
- **Daily limits:** Account-specific
- **Error Response:** `429 Too Many Requests` with rate limit information

**Key Endpoints Used:**
- `POST /messages` - Chat completions (primary endpoint)
- `GET /models` - List available models

**Integration Notes:**
- **Cost Model:** Per-token pricing (input/output tokens)
- **Streaming Support:** Yes, via `stream: true` parameter
- **Function Calling:** Supported via `tools` parameter
- **Response Format:** JSON with `content`, `usage`, `model` fields
- **Error Handling:** Standard HTTP status codes (400, 401, 429, 500)
- **Quota Interpretation:** 429 errors indicate rate limit; different header format than OpenAI
- **Cost Calculation:** Similar to OpenAI, per-token pricing

**Pricing Structure (Example - subject to change):**
- Claude 3 Opus: ~$0.015/1K input tokens, ~$0.075/1K output tokens
- Claude 3 Sonnet: ~$0.003/1K input tokens, ~$0.015/1K output tokens
- Pricing varies by model

## Google Gemini API

**Purpose:** Google's LLM provider (Gemini models) for chat completions.

**Documentation:** https://ai.google.dev/docs

**Base URL(s):**
- `https://generativelanguage.googleapis.com/v1` - Production API

**Authentication:**
- **Method:** API key (query parameter or header) or OAuth
- **Format:** `?key=...` or `Authorization: Bearer ...` (OAuth)
- **Key Management:** API keys from Google AI Studio, OAuth for service accounts

**Rate Limits:**
- **Tier-based:** Free tier and paid tiers with different limits
- **Requests per minute (RPM):** Varies by tier
- **Tokens per minute (TPM):** Model-specific
- **Error Response:** `429 ResourceExhausted` with retry information

**Key Endpoints Used:**
- `POST /models/{model}:generateContent` - Chat completions
- `GET /models` - List available models

**Integration Notes:**
- **Cost Model:** Per-token pricing (may have free tier)
- **Streaming Support:** Yes
- **OAuth Support:** Required for some use cases (Gemini CLI)
- **Response Format:** JSON with different structure than OpenAI
- **Error Handling:** gRPC-style error codes, HTTP status codes
- **Quota Interpretation:** Different error format than OpenAI/Anthropic

## Generic HTTP API Adapter

**Purpose:** Enables routing to any HTTP-based API (not just LLMs). Supports general-purpose API routing.

**Documentation:** Provider-specific

**Base URL(s):** Provider-specific

**Authentication:**
- **Method:** Varies (API key, OAuth, Bearer token, custom headers)
- **Format:** Provider-specific
- **Key Management:** Provider-specific credential storage

**Rate Limits:**
- **Provider-specific:** Each provider has different rate limiting
- **Error Response:** Varies (429, 503, custom error codes)

**Key Endpoints Used:**
- Provider-specific endpoints

**Integration Notes:**
- **Adapter Pattern:** Each provider requires adapter implementation
- **Capability Declaration:** Adapter declares what provider supports
- **Error Normalization:** Provider errors mapped to system error categories
- **Cost Model:** Provider-specific (may not have cost tracking)
- **Extensibility:** New providers added by implementing ProviderAdapter interface

**Example Use Cases:**
- Cloud service APIs (AWS, GCP, Azure)
- Payment APIs (Stripe, PayPal)
- Communication APIs (Twilio, SendGrid)
- Any HTTP-based API with authentication

## Integration Architecture

**Provider Abstraction:**
- All providers accessed through `ProviderAdapter` interface
- Core system never directly calls provider APIs
- Adapters handle provider-specific details (auth, error formats, response parsing)

**Error Handling:**
- Provider errors normalized to system error categories
- 429 errors interpreted as quota/rate limit issues
- 401 errors interpreted as invalid key
- 503 errors interpreted as provider downtime

**Cost Tracking:**
- Cost models per provider (may vary significantly)
- Some providers may not expose cost information
- Uncertainty modeled explicitly when cost unknown

**Rate Limit Handling:**
- Provider-specific rate limit interpretation
- Cooldown periods calculated per provider
- Quota state updated based on provider responses

**Extensibility:**
- New providers added by creating adapter implementation
- Adapter answers fixed questions (capabilities, execution, errors, cost)
- No core code changes required for new providers

---

**Note:** This list represents initial provider support. The system is designed to support any HTTP-based API through the adapter pattern. Additional providers can be added by implementing the `ProviderAdapter` interface.

---

**Select 1-9 or just type your question/feedback:**

1. Proceed to next section (Core Workflows)
2. Challenge assumptions
3. Explore alternatives
4. Deep dive analysis
5. Risk assessment
6. Stakeholder perspective
7. Scenario planning
8. Constraint analysis
9. Expert consultation

Or type your feedback/questions about the External APIs section.
