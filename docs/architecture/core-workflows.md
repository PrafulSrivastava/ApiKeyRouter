# Core Workflows

This section illustrates key system workflows using sequence diagrams. These workflows demonstrate how components interact to achieve intelligent routing, quota awareness, cost control, and graceful failure handling.

## Workflow 1: Successful Request Routing (Happy Path)

This workflow shows the complete flow of an API request through the system, including quota awareness, cost estimation, intelligent routing, and execution.

```mermaid
sequenceDiagram
    participant App as Application
    participant Router as ApiKeyRouter
    participant RE as RoutingEngine
    participant PE as PolicyEngine
    participant KM as KeyManager
    participant QA as QuotaAwarenessEngine
    participant CC as CostController
    participant Adapter as ProviderAdapter
    participant Provider as External Provider
    participant OM as ObservabilityManager
    participant SS as StateStore

    App->>Router: route(request_intent, objective)
    activate Router
    
    Router->>OM: log_request_start(context)
    Router->>PE: evaluate_policy(routing_policy, context)
    PE-->>Router: applicable_policies
    
    Router->>RE: route_request(request_intent, objective, policies)
    activate RE
    
    RE->>KM: get_eligible_keys(provider_id, policy)
    KM->>SS: query_keys(provider_id, state=Available)
    SS-->>KM: eligible_keys[]
    KM-->>RE: eligible_keys[]
    
    loop For each eligible key
        RE->>QA: get_quota_state(key_id)
        QA->>SS: get_quota_state(key_id)
        SS-->>QA: quota_state
        QA->>QA: predict_exhaustion(key_id)
        QA-->>RE: quota_state + exhaustion_prediction
        
        RE->>CC: estimate_request_cost(request_intent, provider_id, key_id)
        CC->>Adapter: get_cost_model(provider_id)
        Adapter-->>CC: cost_model
        CC->>CC: calculate_estimate(request_intent, cost_model)
        CC-->>RE: cost_estimate
        
        RE->>CC: check_budget(request_intent, cost_estimate)
        CC->>SS: get_budget_status(scope)
        SS-->>CC: budget_status
        CC->>CC: would_exceed_budget?(cost_estimate, budget_status)
        CC-->>RE: budget_check_result
    end
    
    RE->>RE: evaluate_keys(eligible_keys, objective, quota_states, costs)
    RE->>RE: select_best_key(objective, scores)
    RE->>RE: generate_explanation(decision)
    RE-->>Router: routing_decision(key_id, provider_id, explanation)
    deactivate RE
    
    Router->>OM: log_routing_decision(decision)
    Router->>SS: save_routing_decision(decision)
    
    Router->>Adapter: execute_request(request_intent, selected_key)
    activate Adapter
    Adapter->>Provider: POST /chat/completions (with API key)
    Provider-->>Adapter: response (200 OK, completion data)
    deactivate Adapter
    Adapter-->>Router: system_response
    
    Router->>QA: update_capacity(key_id, consumed_tokens, cost_estimate)
    QA->>SS: update_quota_state(key_id, consumed)
    QA->>QA: recalculate_capacity_state()
    QA->>SS: save_quota_state(updated_state)
    
    Router->>CC: record_actual_cost(request_id, actual_cost)
    CC->>CC: reconcile_estimate(estimated, actual)
    CC->>SS: update_budget_status(scope, actual_cost)
    
    Router->>OM: log_request_complete(context, success=True)
    Router-->>App: system_response
    
    deactivate Router
```

## Workflow 2: Request Routing with Failure and Intelligent Retry

This workflow demonstrates graceful failure handling, semantic error interpretation, and intelligent retry with different key/provider.

```mermaid
sequenceDiagram
    participant App as Application
    participant Router as ApiKeyRouter
    participant RE as RoutingEngine
    participant FH as FailureHandler
    participant KM as KeyManager
    participant QA as QuotaAwarenessEngine
    participant Adapter as ProviderAdapter
    participant Provider as External Provider
    participant OM as ObservabilityManager
    participant SS as StateStore

    App->>Router: route(request_intent, objective)
    activate Router
    
    Router->>RE: route_request(request_intent, objective)
    RE->>KM: get_eligible_keys(provider_id)
    KM-->>RE: eligible_keys[]
    RE->>QA: get_quota_state(key_id)
    QA-->>RE: quota_state (Abundant)
    RE-->>Router: routing_decision(key_id=key1, provider_id=openai)
    
    Router->>Adapter: execute_request(request_intent, key1)
    Adapter->>Provider: POST /chat/completions
    Provider-->>Adapter: 429 Too Many Requests (Rate Limit)
    Adapter-->>Router: provider_error(429, rate_limit)
    
    Router->>FH: interpret_failure(error, context)
    activate FH
    FH->>FH: classify_error(429) -> RATE_LIMIT
    FH->>FH: extract_retry_after(error) -> 60 seconds
    FH->>FH: determine_cooldown(key1, RATE_LIMIT) -> 60 seconds
    FH-->>Router: failure_interpretation(type=RATE_LIMIT, cooldown=60s, key=key1)
    deactivate FH
    
    Router->>KM: update_key_state(key1, Throttled, reason="Rate limit")
    KM->>SS: save_key(key1, state=Throttled)
    KM->>SS: save_state_transition(key1, Available->Throttled)
    KM->>OM: emit_event(key_state_changed, key1, Throttled)
    
    Router->>QA: handle_quota_response(key1, 429_response)
    QA->>QA: interpret_429_as_quota_exhaustion()
    QA->>SS: update_quota_state(key1, state=Exhausted)
    QA->>SS: save_state_transition(quota_state, Constrained->Exhausted)
    
    Router->>FH: should_retry(failure_interpretation, attempt=1)
    FH-->>Router: should_retry=True (different key)
    
    Note over Router: Retry with different key
    Router->>RE: route_request(request_intent, objective)
    RE->>KM: get_eligible_keys(provider_id, exclude=[key1])
    KM-->>RE: eligible_keys[] (key1 excluded - Throttled)
    RE->>QA: get_quota_state(key2)
    QA-->>RE: quota_state (Abundant)
    RE-->>Router: routing_decision(key_id=key2, provider_id=openai)
    
    Router->>OM: log_retry_decision(original_key=key1, new_key=key2, reason="Rate limit")
    Router->>Adapter: execute_request(request_intent, key2)
    Adapter->>Provider: POST /chat/completions
    Provider-->>Adapter: 200 OK (success)
    Adapter-->>Router: system_response
    
    Router->>QA: update_capacity(key2, consumed_tokens)
    Router->>OM: log_request_complete(context, success=True, retried=True)
    Router-->>App: system_response
    
    deactivate Router
    
    Note over FH,KM: Automatic recovery monitoring
    FH->>KM: monitor_recovery(key1)
    loop Every 10 seconds
        KM->>Adapter: health_check(key1)
        Adapter->>Provider: GET /models (test request)
        alt Provider healthy
            Provider-->>Adapter: 200 OK
            Adapter-->>KM: health_check_result=healthy
            KM->>KM: update_key_state(key1, Available)
            KM->>SS: save_state_transition(key1, Throttled->Available)
        else Still throttled
            Provider-->>Adapter: 429 Too Many Requests
            Adapter-->>KM: health_check_result=throttled
            Note over KM: Keep key in Throttled state
        end
    end
```

## Workflow 3: Predictive Quota Exhaustion and Proactive Routing

This workflow demonstrates forward-looking quota awareness - the system predicts exhaustion and routes away from risky keys before they fail.

```mermaid
sequenceDiagram
    participant App as Application
    participant Router as ApiKeyRouter
    participant RE as RoutingEngine
    participant QA as QuotaAwarenessEngine
    participant KM as KeyManager
    participant SS as StateStore
    participant OM as ObservabilityManager

    App->>Router: route(request_intent, objective)
    activate Router
    
    Router->>RE: route_request(request_intent, objective)
    RE->>KM: get_eligible_keys(provider_id)
    KM-->>RE: eligible_keys[] (key1, key2, key3)
    
    loop For each key
        RE->>QA: get_quota_state(key_id)
        QA->>SS: get_quota_state(key_id)
        SS-->>QA: quota_state
        
        alt Key has low capacity
            QA->>QA: predict_exhaustion(key_id)
            QA->>QA: calculate_usage_rate(key_id) -> 500 req/hour
            QA->>QA: calculate_remaining_capacity(key_id) -> 1000 requests
            QA->>QA: predict_exhaustion_time(rate, capacity) -> 2 hours
            QA->>SS: save_exhaustion_prediction(key_id, predicted_at=+2h)
            QA-->>RE: quota_state(state=Critical, exhaustion_prediction=+2h, confidence=0.85)
        else Key has abundant capacity
            QA-->>RE: quota_state(state=Abundant, exhaustion_prediction=None)
        end
    end
    
    RE->>RE: evaluate_keys(keys, objective, quota_states)
    Note over RE: Key1: Critical (exhausts in 2h), Key2: Abundant, Key3: Constrained
    RE->>RE: apply_routing_policy(objective=reliability)
    Note over RE: Policy: Avoid keys with exhaustion < 4 hours
    RE->>RE: filter_keys_by_policy(keys, policy) -> [key2, key3] (key1 excluded)
    RE->>RE: select_best_key([key2, key3], objective)
    RE->>RE: generate_explanation("Key1 excluded: predicted exhaustion in 2h")
    RE-->>Router: routing_decision(key_id=key2, explanation="Key1 avoided due to exhaustion prediction")
    
    Router->>OM: log_routing_decision(decision)
    OM->>OM: log_quota_awareness_event(key1, "Avoided due to exhaustion prediction")
    
    Router->>Adapter: execute_request(request_intent, key2)
    Adapter-->>Router: system_response
    Router-->>App: system_response
    
    deactivate Router
    
    Note over QA: Background: Monitor key1 for recovery
    QA->>QA: monitor_quota_recovery(key1)
    Note over QA: When quota resets or capacity improves, key1 becomes eligible again
```

## Workflow 4: Cost-Aware Routing with Budget Enforcement

This workflow demonstrates proactive cost control - the system estimates costs, checks budgets, and may reject or downgrade requests to stay within budget.

```mermaid
sequenceDiagram
    participant App as Application
    participant Router as ApiKeyRouter
    participant RE as RoutingEngine
    participant CC as CostController
    participant QA as QuotaAwarenessEngine
    participant Adapter as ProviderAdapter
    participant SS as StateStore
    participant OM as ObservabilityManager

    App->>Router: route(request_intent, objective=reliability)
    activate Router
    
    Router->>RE: route_request(request_intent, objective)
    RE->>KM: get_eligible_keys(provider_id)
    KM-->>RE: eligible_keys[] (key1, key2)
    
    loop For each key
        RE->>CC: estimate_request_cost(request_intent, provider_id, key_id)
        CC->>Adapter: get_cost_model(provider_id)
        Adapter-->>CC: cost_model(pricing_per_token, model_costs)
        CC->>CC: estimate_tokens(request_intent) -> 500 input, 200 output
        CC->>CC: calculate_cost(500 input, 200 output, cost_model) -> $0.015
        CC-->>RE: cost_estimate($0.015, confidence=0.9)
        
        RE->>CC: check_budget(request_intent, cost_estimate)
        CC->>SS: get_budget_status(scope=global)
        SS-->>CC: budget_status(limit=$100, current=$99.50, remaining=$0.50)
        CC->>CC: would_exceed_budget?($0.015, $0.50) -> False (within budget)
        CC-->>RE: budget_check_result(allowed=True, remaining=$0.485)
    end
    
    RE->>RE: evaluate_keys(keys, objective, costs, budgets)
    Note over RE: Key1: $0.015, Key2: $0.020 (both within budget)
    RE->>RE: apply_cost_awareness(objective=reliability, cost_constraint)
    Note over RE: Choose key1 (cheaper, still reliable)
    RE-->>Router: routing_decision(key_id=key1, cost=$0.015)
    
    Router->>CC: reserve_budget(scope=global, amount=$0.015)
    CC->>SS: update_budget_status(scope, reserved=$0.015)
    
    Router->>Adapter: execute_request(request_intent, key1)
    Adapter-->>Router: system_response(actual_tokens=520 input, 180 output)
    
    Router->>CC: record_actual_cost(request_id, actual_cost=$0.014)
    CC->>CC: reconcile_estimate(estimated=$0.015, actual=$0.014)
    CC->>SS: update_budget_status(scope, actual_spend=$0.014)
    CC->>SS: save_cost_reconciliation(request_id, estimated, actual)
    
    Router-->>App: system_response
    
    deactivate Router
    
    Note over App,Router: Scenario: Budget Exceeded
    App->>Router: route(request_intent, objective)
    Router->>RE: route_request(request_intent, objective)
    RE->>CC: estimate_request_cost(request_intent, provider_id, key_id)
    CC-->>RE: cost_estimate($0.10)
    RE->>CC: check_budget(request_intent, cost_estimate)
    CC->>SS: get_budget_status(scope=global)
    SS-->>CC: budget_status(limit=$100, current=$99.95, remaining=$0.05)
    CC->>CC: would_exceed_budget?($0.10, $0.05) -> True (exceeds budget)
    CC-->>RE: budget_check_result(allowed=False, reason="Would exceed budget")
    
    RE->>RE: handle_budget_violation(cost_estimate, budget_status)
    alt Enforcement Mode: Hard (Reject)
        RE-->>Router: routing_error("Budget exceeded", reject=True)
        Router->>OM: log_budget_violation(request_intent, cost_estimate)
        Router-->>App: error_response("Budget exceeded: $0.10 request exceeds remaining $0.05")
    else Enforcement Mode: Soft (Warn but allow)
        RE->>RE: downgrade_request(request_intent) -> cheaper_model
        RE->>CC: estimate_request_cost(downgraded_request, provider_id, key_id)
        CC-->>RE: cost_estimate($0.02) (within budget)
        RE-->>Router: routing_decision(key_id=key1, model=downgraded, cost=$0.02)
        Router->>OM: log_budget_warning(request_intent, original_cost=$0.10, downgraded_cost=$0.02)
        Note over Router: Continue with downgraded request
    end
```

## Workflow 5: Key Registration and State Management

This workflow shows how keys are registered, how state transitions are tracked, and how the system handles key revocation gracefully.

```mermaid
sequenceDiagram
    participant User as User/Admin
    participant Router as ApiKeyRouter
    participant KM as KeyManager
    participant QA as QuotaAwarenessEngine
    participant SS as StateStore
    participant OM as ObservabilityManager
    participant PE as PolicyEngine

    User->>Router: register_key(key_material="sk-...", provider_id="openai", metadata={})
    activate Router
    
    Router->>KM: register_key(key_material, provider_id, metadata)
    activate KM
    
    KM->>KM: generate_key_id() -> "key_abc123"
    KM->>KM: encrypt_key_material(key_material)
    KM->>KM: create_api_key(id, encrypted_material, provider_id, state=Available)
    KM->>SS: save_key(api_key)
    KM->>SS: save_state_transition(key_id, None->Available, trigger="registration")
    KM->>OM: emit_event(key_registered, key_id, provider_id)
    KM-->>Router: api_key(id="key_abc123", state=Available)
    deactivate KM
    
    Router->>QA: initialize_quota_state(key_id, provider_id)
    activate QA
    QA->>QA: create_quota_state(key_id, initial_capacity=unknown, state=Abundant)
    QA->>SS: save_quota_state(quota_state)
    QA-->>Router: quota_state_initialized
    deactivate QA
    
    Router->>OM: log_key_registration(key_id, provider_id)
    Router-->>User: key_registered(key_id="key_abc123", state=Available)
    deactivate Router
    
    Note over User,Router: Key Usage (State Transitions)
    Router->>KM: update_key_state(key_id, new_state=Throttled, reason="Rate limit")
    KM->>SS: get_key(key_id)
    SS-->>KM: current_key(state=Available)
    KM->>KM: validate_state_transition(Available->Throttled) -> Valid
    KM->>SS: save_key(key_id, state=Throttled)
    KM->>SS: save_state_transition(key_id, Available->Throttled, reason="Rate limit")
    KM->>OM: emit_event(key_state_changed, key_id, Available->Throttled)
    KM-->>Router: state_transition_recorded
    
    Note over User,Router: Key Revocation (Graceful Degradation)
    User->>Router: revoke_key(key_id="key_abc123")
    Router->>KM: revoke_key(key_id)
    KM->>SS: get_key(key_id)
    SS-->>KM: current_key
    KM->>KM: validate_state_transition(current_state->Disabled) -> Valid
    KM->>SS: save_key(key_id, state=Disabled)
    KM->>SS: save_state_transition(key_id, current_state->Disabled, reason="Manual revocation")
    KM->>OM: emit_event(key_revoked, key_id)
    KM-->>Router: key_revoked
    
    Router->>RE: invalidate_key_from_routing(key_id)
    Note over RE: Key excluded from future routing decisions
    Router->>OM: log_key_revocation(key_id, impact="Key excluded from routing")
    Router-->>User: key_revoked(key_id, system_continues=True)
    
    Note over Router: System continues operating with remaining keys
    Router->>KM: get_eligible_keys(provider_id)
    KM->>SS: query_keys(provider_id, state=Available, exclude=[key_abc123])
    SS-->>KM: remaining_keys[] (key_abc123 excluded)
    KM-->>Router: eligible_keys[] (system degraded but functional)
```

## Workflow 6: Policy Evaluation and Routing Decision Explanation

This workflow demonstrates how policies are evaluated, how routing decisions are made with explicit objectives, and how explanations are generated.

```mermaid
sequenceDiagram
    participant App as Application
    participant Router as ApiKeyRouter
    participant RE as RoutingEngine
    participant PE as PolicyEngine
    participant KM as KeyManager
    participant QA as QuotaAwarenessEngine
    participant CC as CostController
    participant SS as StateStore

    App->>Router: route(request_intent, objective=RoutingObjective(cost, reliability))
    activate Router
    
    Router->>RE: route_request(request_intent, objective)
    activate RE
    
    RE->>PE: get_applicable_policies(scope=global, type=routing)
    PE->>SS: query_policies(scope=global, type=routing, enabled=True)
    SS-->>PE: policies[] (policy1: cost_optimization, policy2: reliability_minimum)
    PE-->>RE: applicable_policies[]
    
    RE->>KM: get_eligible_keys(provider_id, policy=policy1)
    KM-->>RE: eligible_keys[] (key1, key2, key3)
    
    RE->>PE: evaluate_policy(policy1, context={keys, request})
    PE->>PE: apply_policy_rules(policy1, keys)
    PE-->>RE: policy_result(filtered_keys=[key1, key2, key3], constraints={})
    
    loop For each eligible key
        RE->>QA: get_quota_state(key_id)
        QA-->>RE: quota_state(state, exhaustion_prediction)
        
        RE->>CC: estimate_request_cost(request_intent, provider_id, key_id)
        CC-->>RE: cost_estimate
        
        RE->>RE: score_key(key, objective, quota_state, cost_estimate, policy_result)
        Note over RE: Score = f(cost_weight, reliability_weight, quota_state, policy_constraints)
    end
    
    RE->>RE: rank_keys_by_score(keys, scores)
    Note over RE: key1: score=0.85, key2: score=0.72, key3: score=0.68
    RE->>RE: select_best_key(ranked_keys) -> key1
    
    RE->>RE: generate_explanation(decision, objective, scores, policies)
    Note over RE: Explanation: "Selected key1 because it has lowest cost ($0.01) while maintaining reliability threshold (>0.8). Key2 was cheaper but below reliability threshold. Policy 'cost_optimization' applied."
    RE-->>Router: routing_decision(key_id=key1, explanation="...", scores={key1: 0.85, key2: 0.72, key3: 0.68})
    deactivate RE
    
    Router->>SS: save_routing_decision(decision)
    Router->>OM: log_routing_decision(decision)
    Router-->>App: system_response(decision_explanation="...")
    
    deactivate Router
```

---

## Workflow Design Decisions

1. **Error Handling:** Failures are interpreted semantically and trigger appropriate state transitions
2. **Retry Logic:** Intelligent retries use different keys/providers, not blind retries
3. **Quota Awareness:** System predicts exhaustion and routes proactively, not reactively
4. **Cost Control:** Budgets checked before execution, requests rejected or downgraded if needed
5. **State Transitions:** All state changes are tracked with audit trails
6. **Policy Evaluation:** Policies are evaluated before routing, influencing key selection
7. **Observability:** All decisions and state changes are logged for full traceability

---

**Select 1-9 or just type your question/feedback:**

1. Proceed to next section (REST API Spec - if applicable, or Database Schema)
2. Challenge assumptions
3. Explore alternatives
4. Deep dive analysis
5. Risk assessment
6. Stakeholder perspective
7. Scenario planning
8. Constraint analysis
9. Expert consultation

Or type your feedback/questions about the Core Workflows section.
