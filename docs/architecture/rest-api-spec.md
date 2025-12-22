# REST API Spec

The proxy service exposes REST endpoints for API routing and system management. The primary API is OpenAI-compatible for seamless integration, with additional management endpoints for configuration and observability.

## OpenAPI 3.0 Specification

```yaml
openapi: 3.0.0
info:
  title: ApiKeyRouter Proxy API
  version: 1.0.0
  description: |
    Intelligent API key routing proxy with OpenAI-compatible endpoints.
    Routes requests across multiple API keys and providers with quota awareness,
    cost control, and intelligent failover.
  contact:
    name: ApiKeyRouter Support
    url: https://github.com/yourorg/apikeyrouter
  license:
    name: MIT
    url: https://opensource.org/licenses/MIT

servers:
  - url: http://localhost:8000
    description: Local development server
  - url: https://api.yourdomain.com
    description: Production server

tags:
  - chat
  - completions
  - embeddings
  - models
  - keys
  - providers
  - policies
  - state
  - health

paths:
  # OpenAI-Compatible Endpoints
  /v1/chat/completions:
    post:
      tags:
        - chat
      summary: Create chat completion
      description: |
        OpenAI-compatible chat completions endpoint. Routes requests intelligently
        across multiple API keys and providers based on quota, cost, and reliability.
      operationId: createChatCompletion
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ChatCompletionRequest'
            examples:
              basic:
                value:
                  model: gpt-4
                  messages:
                    - role: user
                      content: Hello, how are you?
      responses:
        '200':
          description: Successful completion
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ChatCompletionResponse'
              headers:
                X-Request-ID:
                  schema:
                    type: string
                  description: Request correlation ID
                X-Key-Used:
                  schema:
                    type: string
                  description: API key ID used for this request
                X-Provider-Used:
                  schema:
                    type: string
                  description: Provider used for this request
                X-Cost-Estimated:
                  schema:
                    type: number
                  description: Estimated cost in USD
        '400':
          description: Bad request
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '429':
          description: Rate limit exceeded (all keys exhausted)
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '500':
          description: Internal server error
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'

  /v1/completions:
    post:
      tags:
        - completions
      summary: Create completion (legacy)
      description: Legacy completions endpoint for backward compatibility
      operationId: createCompletion
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CompletionRequest'
      responses:
        '200':
          description: Successful completion
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CompletionResponse'
        '400':
          description: Bad request
        '429':
          description: Rate limit exceeded
        '500':
          description: Internal server error

  /v1/embeddings:
    post:
      tags:
        - embeddings
      summary: Create embeddings
      description: Create embeddings for input text
      operationId: createEmbedding
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/EmbeddingRequest'
      responses:
        '200':
          description: Successful embedding
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/EmbeddingResponse'
        '400':
          description: Bad request
        '429':
          description: Rate limit exceeded
        '500':
          description: Internal server error

  /v1/models:
    get:
      tags:
        - models
      summary: List models
      description: List available models from all providers
      operationId: listModels
      responses:
        '200':
          description: List of available models
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ModelsResponse'

  # Management Endpoints
  /api/v1/keys:
    get:
      tags:
        - keys
      summary: List API keys
      description: List all registered API keys (sensitive data redacted)
      operationId: listKeys
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: List of API keys
          content:
            application/json:
              schema:
                type: object
                properties:
                  keys:
                    type: array
                    items:
                      $ref: '#/components/schemas/KeySummary'
    post:
      tags:
        - keys
      summary: Register API key
      description: Register a new API key
      operationId: registerKey
      security:
        - ApiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/KeyRegistrationRequest'
      responses:
        '201':
          description: Key registered successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/KeyResponse'
        '400':
          description: Invalid request
        '409':
          description: Key already exists

  /api/v1/keys/{key_id}:
    get:
      tags:
        - keys
      summary: Get API key details
      description: Get details for a specific API key
      operationId: getKey
      security:
        - ApiKeyAuth: []
      parameters:
        - name: key_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Key details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/KeyResponse'
        '404':
          description: Key not found
    delete:
      tags:
        - keys
      summary: Revoke API key
      description: Revoke an API key (graceful degradation)
      operationId: revokeKey
      security:
        - ApiKeyAuth: []
      parameters:
        - name: key_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '204':
          description: Key revoked successfully
        '404':
          description: Key not found

  /api/v1/providers:
    get:
      tags:
        - providers
      summary: List providers
      description: List all registered providers
      operationId: listProviders
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: List of providers
          content:
            application/json:
              schema:
                type: object
                properties:
                  providers:
                    type: array
                    items:
                      $ref: '#/components/schemas/ProviderSummary'
    post:
      tags:
        - providers
      summary: Register provider
      description: Register a new provider adapter
      operationId: registerProvider
      security:
        - ApiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ProviderRegistrationRequest'
      responses:
        '201':
          description: Provider registered successfully
        '400':
          description: Invalid request

  /api/v1/policies:
    get:
      tags:
        - policies
      summary: List policies
      description: List all routing and cost policies
      operationId: listPolicies
      security:
        - ApiKeyAuth: []
      responses:
        '200':
          description: List of policies
          content:
            application/json:
              schema:
                type: object
                properties:
                  policies:
                    type: array
                    items:
                      $ref: '#/components/schemas/PolicySummary'
    post:
      tags:
        - policies
      summary: Create policy
      description: Create a new routing or cost policy
      operationId: createPolicy
      security:
        - ApiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/PolicyRequest'
      responses:
        '201':
          description: Policy created successfully
        '400':
          description: Invalid policy

  /api/v1/state:
    get:
      tags:
        - state
      summary: Get system state
      description: Get current system state (keys, quotas, routing decisions)
      operationId: getState
      security:
        - ApiKeyAuth: []
      parameters:
        - name: scope
          in: query
          schema:
            type: string
            enum: [keys, quotas, routing, all]
            default: all
      responses:
        '200':
          description: System state summary
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StateSummary'

  /api/v1/requests/{request_id}:
    get:
      tags:
        - state
      summary: Get request trace
      description: Get full trace for a specific request (observability)
      operationId: getRequestTrace
      security:
        - ApiKeyAuth: []
      parameters:
        - name: request_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Request trace
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/RequestTrace'
        '404':
          description: Request not found

  /health:
    get:
      tags:
        - health
      summary: Health check
      description: Check system health
      operationId: healthCheck
      responses:
        '200':
          description: System is healthy
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    example: healthy
                  version:
                    type: string
                  uptime:
                    type: number
        '503':
          description: System is unhealthy
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    example: degraded
                  issues:
                    type: array
                    items:
                      type: string

  /metrics:
    get:
      tags:
        - health
      summary: Prometheus metrics
      description: Prometheus-compatible metrics endpoint
      operationId: getMetrics
      responses:
        '200':
          description: Metrics in Prometheus format
          content:
            text/plain:
              schema:
                type: string

components:
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
      description: Management API authentication key

  schemas:
    ChatCompletionRequest:
      type: object
      required:
        - model
        - messages
      properties:
        model:
          type: string
          description: Model identifier
          example: gpt-4
        messages:
          type: array
          items:
            $ref: '#/components/schemas/Message'
        temperature:
          type: number
          minimum: 0
          maximum: 2
          default: 1
        max_tokens:
          type: integer
          minimum: 1
        stream:
          type: boolean
          default: false
        tools:
          type: array
          items:
            $ref: '#/components/schemas/Tool'
        tool_choice:
          type: string
          enum: [none, auto, required]

    Message:
      type: object
      required:
        - role
        - content
      properties:
        role:
          type: string
          enum: [system, user, assistant, tool]
        content:
          type: string
        name:
          type: string
        tool_calls:
          type: array
          items:
            type: object

    ChatCompletionResponse:
      type: object
      properties:
        id:
          type: string
        object:
          type: string
          example: chat.completion
        created:
          type: integer
        model:
          type: string
        choices:
          type: array
          items:
            $ref: '#/components/schemas/Choice'
        usage:
          $ref: '#/components/schemas/Usage'
        system_fingerprint:
          type: string
          nullable: true
        routing_metadata:
          type: object
          description: ApiKeyRouter-specific metadata
          properties:
            key_used:
              type: string
            provider_used:
              type: string
            cost_estimated:
              type: number
            cost_actual:
              type: number
            routing_explanation:
              type: string

    Choice:
      type: object
      properties:
        index:
          type: integer
        message:
          $ref: '#/components/schemas/Message'
        finish_reason:
          type: string
          enum: [stop, length, tool_calls, content_filter]

    Usage:
      type: object
      properties:
        prompt_tokens:
          type: integer
        completion_tokens:
          type: integer
        total_tokens:
          type: integer

    ErrorResponse:
      type: object
      properties:
        error:
          type: object
          properties:
            message:
              type: string
            type:
              type: string
            code:
              type: string
            param:
              type: string
              nullable: true

    KeyRegistrationRequest:
      type: object
      required:
        - key_material
        - provider_id
      properties:
        key_material:
          type: string
          description: API key (will be encrypted)
        provider_id:
          type: string
          example: openai
        metadata:
          type: object
          description: Optional metadata (account info, tier, etc.)

    KeyResponse:
      type: object
      properties:
        id:
          type: string
        provider_id:
          type: string
        state:
          type: string
          enum: [Available, Throttled, Exhausted, Disabled, Invalid]
        created_at:
          type: string
          format: date-time
        last_used_at:
          type: string
          format: date-time
          nullable: true
        usage_count:
          type: integer
        failure_count:
          type: integer

    KeySummary:
      type: object
      properties:
        id:
          type: string
        provider_id:
          type: string
        state:
          type: string
        created_at:
          type: string
          format: date-time

    ProviderRegistrationRequest:
      type: object
      required:
        - name
        - adapter_type
        - base_url
      properties:
        name:
          type: string
          example: openai
        adapter_type:
          type: string
          example: OpenAIAdapter
        base_url:
          type: string
        capabilities:
          type: object

    ProviderSummary:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        health_state:
          type: string
          enum: [Healthy, Degraded, Down]
        key_count:
          type: integer

    PolicyRequest:
      type: object
      required:
        - name
        - type
        - rules
      properties:
        name:
          type: string
        type:
          type: string
          enum: [routing, cost, key_selection, failure_handling]
        scope:
          type: string
        rules:
          type: array
          items:
            type: object

    PolicySummary:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        type:
          type: string
        enabled:
          type: boolean

    StateSummary:
      type: object
      properties:
        keys:
          type: object
          properties:
            total:
              type: integer
            by_state:
              type: object
        quotas:
          type: object
          properties:
            total_keys:
              type: integer
            exhausted_keys:
              type: integer
            critical_keys:
              type: integer
        routing:
          type: object
          properties:
            total_decisions:
              type: integer
            recent_decisions:
              type: array

    RequestTrace:
      type: object
      properties:
        request_id:
          type: string
        correlation_id:
          type: string
        timestamp:
          type: string
          format: date-time
        routing_decision:
          type: object
        provider_response:
          type: object
        state_transitions:
          type: array
          items:
            type: object
```

## API Design Decisions

1. **OpenAI Compatibility:** Primary endpoints (`/v1/chat/completions`, `/v1/completions`) match OpenAI API exactly for drop-in replacement
2. **Extended Metadata:** Responses include `routing_metadata` with key used, cost, and explanation (non-breaking extension)
3. **Management API:** Separate `/api/v1/*` namespace for management endpoints to avoid conflicts
4. **Security:** Management endpoints require API key authentication; routing endpoints use provider API keys
5. **Observability:** Request tracing endpoint enables full observability of routing decisions
6. **Health Checks:** Standard `/health` and `/metrics` endpoints for monitoring

## Authentication

**Routing Endpoints (`/v1/*`):**
- No authentication required (proxy handles provider authentication)
- Provider API keys managed internally by system

**Management Endpoints (`/api/v1/*`):**
- API key authentication via `X-API-Key` header
- Separate management API key (not provider keys)
- Configurable via environment variable

---

**Select 1-9 or just type your question/feedback:**

1. Proceed to next section (Database Schema)
2. Challenge assumptions
3. Explore alternatives
4. Deep dive analysis
5. Risk assessment
6. Stakeholder perspective
7. Scenario planning
8. Constraint analysis
9. Expert consultation

Or type your feedback/questions about the REST API Spec section.
