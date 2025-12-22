# Database Schema

The system uses **MongoDB** for optional persistent storage. By default, the system operates in-memory (stateless deployment). MongoDB is used for:
- Audit logs and state transitions
- Historical routing decisions
- Metrics and analytics
- Optional key/quota state persistence (production mode)

**Database Choice Rationale:**
- **MongoDB** - Document database fits our data models naturally (nested structures, flexible schemas)
- **Optional persistence** - System works without database; MongoDB is production enhancement
- **Async support** - Motor driver provides async/await support for FastAPI
- **Beanie ODM** - Pydantic-based ODM ensures type safety and validation

## Collections and Document Schemas

### Collection: `api_keys`

Stores API key information with encrypted key material.

```json
{
  "_id": "key_abc123",
  "key_material_encrypted": "encrypted_string_here",
  "provider_id": "openai",
  "state": "Available",
  "state_updated_at": "2025-12-19T10:30:00Z",
  "metadata": {
    "account_tier": "pay-as-you-go",
    "organization_id": "org_xyz"
  },
  "created_at": "2025-12-19T09:00:00Z",
  "last_used_at": "2025-12-19T10:25:00Z",
  "usage_count": 1250,
  "failure_count": 3,
  "cooldown_until": null
}
```

**Indexes:**
- `{ provider_id: 1, state: 1 }` - Query eligible keys by provider and state
- `{ state: 1, last_used_at: -1 }` - Query keys by state, sorted by usage
- `{ created_at: -1 }` - Sort by creation time

### Collection: `quota_states`

Tracks quota/capacity state per key with time windows.

```json
{
  "_id": "quota_key_abc123_daily",
  "key_id": "key_abc123",
  "capacity_state": "Constrained",
  "remaining_capacity": {
    "value": 5000,
    "min_value": 4500,
    "max_value": 5500,
    "confidence": 0.85,
    "estimation_method": "linear_projection",
    "last_verified": "2025-12-19T10:00:00Z"
  },
  "total_capacity": 10000,
  "used_capacity": 5000,
  "time_window": {
    "type": "daily",
    "reset_at": "2025-12-20T00:00:00Z"
  },
  "exhaustion_prediction": {
    "predicted_exhaustion_at": "2025-12-19T18:30:00Z",
    "confidence": 0.80,
    "calculation_method": "usage_rate_projection",
    "current_usage_rate": 500.0,
    "calculated_at": "2025-12-19T10:30:00Z"
  },
  "uncertainty": "Medium",
  "updated_at": "2025-12-19T10:30:00Z"
}
```

**Indexes:**
- `{ key_id: 1, time_window.type: 1 }` - Query quota by key and window type
- `{ capacity_state: 1, updated_at: -1 }` - Query keys by capacity state
- `{ "exhaustion_prediction.predicted_exhaustion_at": 1 }` - Query keys approaching exhaustion

### Collection: `providers`

Stores provider configuration and capabilities.

```json
{
  "_id": "provider_openai",
  "name": "openai",
  "adapter_type": "OpenAIAdapter",
  "base_url": "https://api.openai.com/v1",
  "capabilities": {
    "supports_streaming": true,
    "supports_tools": true,
    "supports_images": false,
    "max_tokens": 4096,
    "rate_limit_per_minute": 3500
  },
  "health_state": "Healthy",
  "last_health_check": "2025-12-19T10:30:00Z",
  "metadata": {
    "pricing_tier": "standard"
  }
}
```

**Indexes:**
- `{ name: 1 }` - Unique provider name lookup
- `{ health_state: 1 }` - Query providers by health

### Collection: `routing_decisions`

Audit trail of all routing decisions for observability and debugging.

```json
{
  "_id": "decision_xyz789",
  "request_id": "req_abc123",
  "selected_key_id": "key_abc123",
  "selected_provider_id": "openai",
  "decision_timestamp": "2025-12-19T10:30:00Z",
  "objective": {
    "primary": "cost",
    "secondary": ["reliability"],
    "constraints": {
      "min_reliability": 0.95
    },
    "weights": {
      "cost": 0.7,
      "reliability": 0.3
    }
  },
  "eligible_keys": ["key_abc123", "key_def456"],
  "evaluation_results": {
    "key_abc123": {
      "score": 0.85,
      "cost": 0.01,
      "reliability": 0.98,
      "quota_state": "Abundant"
    },
    "key_def456": {
      "score": 0.72,
      "cost": 0.015,
      "reliability": 0.95,
      "quota_state": "Constrained"
    }
  },
  "explanation": "Selected key_abc123 because it has lowest cost ($0.01) while maintaining reliability threshold (>0.95).",
  "confidence": 0.90,
  "alternatives_considered": [
    {
      "key_id": "key_def456",
      "reason_rejected": "Higher cost"
    }
  ]
}
```

**Indexes:**
- `{ request_id: 1 }` - Lookup decision by request
- `{ selected_key_id: 1, decision_timestamp: -1 }` - Query decisions by key
- `{ decision_timestamp: -1 }` - Recent decisions
- `{ selected_provider_id: 1, decision_timestamp: -1 }` - Decisions by provider

### Collection: `state_transitions`

Complete audit trail of all state changes (keys, quotas, providers).

```json
{
  "_id": "transition_xyz123",
  "entity_type": "APIKey",
  "entity_id": "key_abc123",
  "from_state": "Available",
  "to_state": "Throttled",
  "transition_timestamp": "2025-12-19T10:30:00Z",
  "trigger": "rate_limit",
  "context": {
    "error_code": 429,
    "retry_after": 60,
    "request_id": "req_abc123"
  },
  "user_id": null
}
```

**Indexes:**
- `{ entity_type: 1, entity_id: 1, transition_timestamp: -1 }` - Entity history
- `{ transition_timestamp: -1 }` - Recent transitions
- `{ trigger: 1, transition_timestamp: -1 }` - Transitions by trigger type

### Collection: `request_contexts`

Full request context for observability and correlation.

```json
{
  "_id": "req_abc123",
  "correlation_id": "corr_xyz789",
  "request_timestamp": "2025-12-19T10:30:00Z",
  "provider_id": "openai",
  "key_id": "key_abc123",
  "request_type": "chat_completion",
  "estimated_cost": {
    "amount": 0.015,
    "currency": "USD",
    "confidence": 0.90
  },
  "actual_cost": {
    "amount": 0.014,
    "currency": "USD"
  },
  "response_status": 200,
  "response_time_ms": 1250,
  "success": true,
  "error": null,
  "routing_decision_id": "decision_xyz789"
}
```

**Indexes:**
- `{ correlation_id: 1 }` - Trace requests by correlation ID
- `{ key_id: 1, request_timestamp: -1 }` - Requests by key
- `{ provider_id: 1, request_timestamp: -1 }` - Requests by provider
- `{ request_timestamp: -1 }` - Recent requests
- `{ success: 1, request_timestamp: -1 }` - Failed requests

### Collection: `cost_models`

Provider cost models and pricing information.

```json
{
  "_id": "cost_openai",
  "provider_id": "openai",
  "pricing_structure": {
    "type": "per_token",
    "models": {
      "gpt-4": {
        "input_price_per_1k": 0.03,
        "output_price_per_1k": 0.06
      },
      "gpt-3.5-turbo": {
        "input_price_per_1k": 0.0015,
        "output_price_per_1k": 0.002
      }
    }
  },
  "updated_at": "2025-12-19T09:00:00Z"
}
```

**Indexes:**
- `{ provider_id: 1 }` - Unique provider cost model

### Collection: `budget_limits`

Budget constraints at various scopes.

```json
{
  "_id": "budget_global_daily",
  "scope": "global",
  "scope_id": null,
  "limit_amount": 100.00,
  "currency": "USD",
  "period": {
    "type": "daily",
    "reset_at": "2025-12-20T00:00:00Z"
  },
  "current_spend": 95.50,
  "reserved_amount": 2.00,
  "enforcement_mode": "hard",
  "reset_at": "2025-12-20T00:00:00Z",
  "created_at": "2025-12-19T00:00:00Z"
}
```

**Indexes:**
- `{ scope: 1, scope_id: 1 }` - Query budgets by scope
- `{ reset_at: 1 }` - Budgets needing reset

### Collection: `policies`

Routing and cost policies.

```json
{
  "_id": "policy_cost_optimization",
  "name": "Cost Optimization",
  "type": "routing",
  "scope": "global",
  "rules": [
    {
      "condition": "always",
      "action": "minimize_cost",
      "constraints": {
        "min_reliability": 0.95
      }
    }
  ],
  "priority": 1,
  "enabled": true,
  "created_at": "2025-12-19T09:00:00Z",
  "updated_at": "2025-12-19T10:00:00Z"
}
```

**Indexes:**
- `{ type: 1, scope: 1, enabled: 1 }` - Query applicable policies
- `{ priority: -1 }` - Sort by priority

## Database Connection and Configuration

**Connection String Format:**
```
mongodb://[username:password@]host[:port][/database][?options]
```

**Environment Variables:**
- `MONGODB_URL` - MongoDB connection string (optional, system works without it)
- `MONGODB_DATABASE` - Database name (default: `apikeyrouter`)
- `MONGODB_ENABLED` - Enable MongoDB persistence (default: `false` for stateless mode)

**Connection Pooling:**
- Motor (async driver) handles connection pooling
- Default pool size: 100 connections
- Connection timeout: 30 seconds

## Data Retention and Cleanup

**Retention Policies:**
- **Routing Decisions:** 30 days (configurable)
- **Request Contexts:** 7 days (configurable)
- **State Transitions:** 90 days (for audit compliance)
- **API Keys:** Permanent (until deleted)
- **Quota States:** Current + historical snapshots (30 days)

**Cleanup Strategy:**
- Background job runs daily to remove expired documents
- TTL indexes for automatic expiration (MongoDB feature)
- Manual cleanup via management API

## Migration and Schema Evolution

**Schema Versioning:**
- Documents include `schema_version` field
- Migration scripts handle version upgrades
- Backward compatibility maintained for 2 versions

**Initial Setup:**
- Database and collections created automatically on first connection
- Indexes created via Beanie ODM on startup
- No manual schema setup required

## Performance Considerations

**Read Optimization:**
- Indexes on all query patterns
- Compound indexes for multi-field queries
- Projection to limit returned fields

**Write Optimization:**
- Bulk writes for batch operations
- Write concern: `w: 1` (acknowledged, no replication wait)
- Journaling enabled for durability

**Sharding (Future):**
- Shard by `provider_id` if scale requires
- Shard by date range for time-series data (routing_decisions, request_contexts)

---

**Select 1-9 or just type your question/feedback:**

1. Proceed to next section (Source Tree)
2. Challenge assumptions
3. Explore alternatives
4. Deep dive analysis
5. Risk assessment
6. Stakeholder perspective
7. Scenario planning
8. Constraint analysis
9. Expert consultation

Or type your feedback/questions about the Database Schema section.
