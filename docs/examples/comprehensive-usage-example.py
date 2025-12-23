"""
Comprehensive ApiKeyRouter Usage Example

This example demonstrates the full potential of the ApiKeyRouter library,
showcasing all major features including:
- Multiple providers and keys
- Quota awareness and capacity management
- Cost optimization with budgets
- Policy-driven routing
- Multiple routing objectives
- Error handling and automatic retries
- Observability and state inspection
- Key rotation and lifecycle management

SETUP INSTRUCTIONS:
-------------------
To use this example with real API keys, set the following environment variables:

  export OPENAI_KEY_1=your-actual-openai-key-1-here
  export OPENAI_KEY_2=your-actual-openai-key-2-here
  export OPENAI_KEY_3=your-actual-openai-key-3-here
  export OPENAI_KEY_4=your-actual-openai-key-4-here
  export ANTHROPIC_KEY_1=your-actual-anthropic-key-1-here
  export ANTHROPIC_KEY_2=your-actual-anthropic-key-2-here

Or create a .env file in the project root:
  
  OPENAI_KEY_1=your-actual-openai-key-1-here
  OPENAI_KEY_2=your-actual-openai-key-2-here
  OPENAI_KEY_3=your-actual-openai-key-3-here
  OPENAI_KEY_4=your-actual-openai-key-4-here
  ANTHROPIC_KEY_1=your-actual-anthropic-key-1-here
  ANTHROPIC_KEY_2=your-actual-anthropic-key-2-here

If you use a .env file, you can load it with python-dotenv:
  from dotenv import load_dotenv
  load_dotenv()

If environment variables are not set, the example will use placeholder keys
which demonstrate the structure but won't work for actual API calls.
"""

import asyncio
import os
from datetime import datetime, timedelta

from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.policy import Policy, PolicyScope, PolicyType
from apikeyrouter.domain.models.quota import TimeWindow
from apikeyrouter.domain.models.routing import ObjectiveType, RoutingObjective


def load_api_keys_from_env():
    """
    Load API keys from environment variables.
    
    For this example, you can set these environment variables:
    - OPENAI_KEY_1, OPENAI_KEY_2, OPENAI_KEY_3, OPENAI_KEY_4
    - ANTHROPIC_KEY_1, ANTHROPIC_KEY_2
    
    Or use a .env file with:
    OPENAI_KEY_1=your-actual-openai-key-1-here
    OPENAI_KEY_2=your-actual-openai-key-2-here
    ...
    
    If environment variables are not set, the example will use placeholder keys
    (which won't work for actual API calls but demonstrate the structure).
    
    Returns:
        dict: Dictionary with provider_id as key and list of (key_name, key_material) tuples
    """
    return {
        "openai": [
            ("premium-1", os.getenv("OPENAI_KEY_1", "sk-example-openai-premium-1-not-real")),
            ("premium-2", os.getenv("OPENAI_KEY_2", "sk-example-openai-premium-2-not-real")),
            ("paygo-1", os.getenv("OPENAI_KEY_3", "sk-example-openai-paygo-1-not-real")),
            ("paygo-2", os.getenv("OPENAI_KEY_4", "sk-example-openai-paygo-2-not-real")),
        ],
        "anthropic": [
            ("premium-1", os.getenv("ANTHROPIC_KEY_1", "sk-example-ant-premium-1-not-real")),
            ("premium-2", os.getenv("ANTHROPIC_KEY_2", "sk-example-ant-premium-2-not-real")),
        ]
    }


async def comprehensive_example():
    """
    Comprehensive example demonstrating all ApiKeyRouter capabilities.
    """

    # ============================================================================
    # PART 1: INITIALIZATION AND SETUP
    # ============================================================================

    print("=" * 80)
    print("PART 1: INITIALIZATION AND SETUP")
    print("=" * 80)

    # Initialize the router
    router = ApiKeyRouter()

    # Register multiple providers
    from apikeyrouter.adapters import AnthropicAdapter, OpenAIAdapter

    router.register_provider("openai", OpenAIAdapter())
    router.register_provider("anthropic", AnthropicAdapter())

    print("✓ Registered providers: OpenAI, Anthropic")

    # ============================================================================
    # PART 2: KEY REGISTRATION WITH METADATA
    # ============================================================================

    print("\n" + "=" * 80)
    print("PART 2: KEY REGISTRATION WITH METADATA")
    print("=" * 80)

    # Load API keys from environment variables (or use placeholders)
    # IMPORTANT: Set your actual API keys as environment variables:
    #   export OPENAI_KEY_1=your-actual-key-1-here
    #   export OPENAI_KEY_2=your-actual-key-2-here
    #   etc.
    # Or use a .env file with python-dotenv
    api_keys = load_api_keys_from_env()

    # Check if we're using placeholder keys
    using_placeholders = any("placeholder" in key_material for keys in api_keys.values() for _, key_material in keys)
    if using_placeholders:
        print("⚠️  WARNING: Using placeholder API keys. Set environment variables for real keys:")
        print("   OPENAI_KEY_1, OPENAI_KEY_2, OPENAI_KEY_3, OPENAI_KEY_4")
        print("   ANTHROPIC_KEY_1, ANTHROPIC_KEY_2")
        print("   Or create a .env file with your actual keys.\n")

    # Define key configurations with metadata
    # The actual key material comes from environment variables
    key_configs = [
        # OpenAI Premium Keys
        {
            "key_material": api_keys["openai"][0][1],  # premium-1
            "provider_id": "openai",
            "metadata": {
                "tier": "premium",
                "account_type": "enterprise",
                "monthly_limit": 1000000,  # 1M tokens/month
                "rate_limit": 10000,  # 10K requests/minute
                "cost_per_1k_tokens": 0.03,  # GPT-4 pricing
                "region": "us-east-1",
                "team": "production"
            }
        },
        {
            "key_material": api_keys["openai"][1][1],  # premium-2
            "provider_id": "openai",
            "metadata": {
                "tier": "premium",
                "account_type": "enterprise",
                "monthly_limit": 1000000,
                "rate_limit": 10000,
                "cost_per_1k_tokens": 0.03,
                "region": "us-west-2",
                "team": "production"
            }
        },
        # OpenAI Pay-as-you-go Keys
        {
            "key_material": api_keys["openai"][2][1],  # paygo-1
            "provider_id": "openai",
            "metadata": {
                "tier": "pay-as-you-go",
                "account_type": "individual",
                "monthly_limit": 100000,  # 100K tokens/month
                "rate_limit": 500,  # 500 requests/minute
                "cost_per_1k_tokens": 0.06,  # Higher per-token cost
                "region": "us-east-1",
                "team": "development"
            }
        },
        {
            "key_material": api_keys["openai"][3][1],  # paygo-2
            "provider_id": "openai",
            "metadata": {
                "tier": "pay-as-you-go",
                "account_type": "individual",
                "monthly_limit": 100000,
                "rate_limit": 500,
                "cost_per_1k_tokens": 0.06,
                "region": "us-west-2",
                "team": "development"
            }
        },
        # Anthropic Premium Keys
        {
            "key_material": api_keys["anthropic"][0][1],  # premium-1
            "provider_id": "anthropic",
            "metadata": {
                "tier": "premium",
                "account_type": "enterprise",
                "monthly_limit": 500000,  # 500K tokens/month
                "rate_limit": 5000,  # 5K requests/minute
                "cost_per_1k_tokens": 0.015,  # Claude pricing
                "region": "us-east-1",
                "team": "production"
            }
        },
        {
            "key_material": api_keys["anthropic"][1][1],  # premium-2
            "provider_id": "anthropic",
            "metadata": {
                "tier": "premium",
                "account_type": "enterprise",
                "monthly_limit": 500000,
                "rate_limit": 5000,
                "cost_per_1k_tokens": 0.015,
                "region": "us-west-2",
                "team": "production"
            }
        }
    ]

    # Register all keys
    registered_keys = {}
    for config in key_configs:
        key = router.register_key(
            key_material=config["key_material"],
            provider_id=config["provider_id"],
            metadata=config["metadata"]
        )
        registered_keys[key.id] = key
        # Mask the key material in output for security
        key_material = config["key_material"]
        masked_key = key_material[:8] + "..." + key_material[-4:] if len(key_material) > 12 else "***"
        print(f"✓ Registered {config['provider_id']} key: {key.id} "
              f"(key: {masked_key}, tier: {config['metadata']['tier']}, "
              f"team: {config['metadata']['team']})")

    print(f"\n✓ Total keys registered: {len(registered_keys)}")

    # ============================================================================
    # PART 3: QUOTA CONFIGURATION
    # ============================================================================

    print("\n" + "=" * 80)
    print("PART 3: QUOTA CONFIGURATION")
    print("=" * 80)

    # Configure quota awareness for each key
    # Premium keys have monthly quotas, paygo keys have daily quotas
    for key_id, key in registered_keys.items():
        metadata = key.metadata

        if metadata.get("tier") == "premium":
            # Monthly quota window
            router.configure_quota(
                key_id=key_id,
                time_window=TimeWindow.Monthly,
                total_capacity=metadata.get("monthly_limit", 1000000),
                reset_at=datetime.now().replace(day=1, hour=0, minute=0, second=0) + timedelta(days=32)
            )
            print(f"✓ Configured monthly quota for {key_id}: {metadata.get('monthly_limit')} tokens")
        else:
            # Daily quota window
            router.configure_quota(
                key_id=key_id,
                time_window=TimeWindow.Daily,
                total_capacity=metadata.get("monthly_limit", 100000),  # Using monthly as daily for demo
                reset_at=datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
            )
            print(f"✓ Configured daily quota for {key_id}: {metadata.get('monthly_limit')} tokens")

    # ============================================================================
    # PART 4: POLICY CONFIGURATION
    # ============================================================================

    print("\n" + "=" * 80)
    print("PART 4: POLICY CONFIGURATION")
    print("=" * 80)

    # Policy 1: Cost optimization for development team
    cost_optimization_policy = Policy(
        name="development_cost_optimization",
        type=PolicyType.Cost,
        scope=PolicyScope.Team,
        scope_value="development",
        rules=[
            {
                "action": "prefer_lowest_cost",
                "max_cost_per_request": 0.10,  # $0.10 max per request
                "fallback_to_reliable": True
            }
        ],
        enabled=True
    )
    router.configure_policy(cost_optimization_policy)
    print("✓ Configured cost optimization policy for development team")

    # Policy 2: Reliability-first for production team
    reliability_policy = Policy(
        name="production_reliability",
        type=PolicyType.Routing,
        scope=PolicyScope.Team,
        scope_value="production",
        rules=[
            {
                "action": "prefer_high_reliability",
                "min_success_rate": 0.95,  # 95% minimum success rate
                "prefer_premium_tier": True,
                "allow_fallback": True
            }
        ],
        enabled=True
    )
    router.configure_policy(reliability_policy)
    print("✓ Configured reliability-first policy for production team")

    # Policy 3: Budget enforcement
    budget_policy = Policy(
        name="monthly_budget_limit",
        type=PolicyType.Cost,
        scope=PolicyScope.Global,
        rules=[
            {
                "action": "enforce_budget",
                "budget_limit": 1000.00,  # $1000/month
                "budget_window": "monthly",
                "enforcement_mode": "prevent",  # Prevent requests that would exceed budget
                "alert_threshold": 0.80  # Alert at 80% of budget
            }
        ],
        enabled=True
    )
    router.configure_policy(budget_policy)
    print("✓ Configured monthly budget limit: $1000")

    # Policy 4: Key selection constraints
    key_selection_policy = Policy(
        name="prefer_regional_keys",
        type=PolicyType.KeySelection,
        scope=PolicyScope.Global,
        rules=[
            {
                "action": "prefer_region",
                "preferred_regions": ["us-east-1"],
                "fallback_regions": ["us-west-2"]
            }
        ],
        enabled=True
    )
    router.configure_policy(key_selection_policy)
    print("✓ Configured regional preference policy")

    # ============================================================================
    # PART 5: ROUTING WITH DIFFERENT OBJECTIVES
    # ============================================================================

    print("\n" + "=" * 80)
    print("PART 5: ROUTING WITH DIFFERENT OBJECTIVES")
    print("=" * 80)

    # Example request intent
    request_intent = {
        "provider_id": "openai",
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Explain quantum computing in simple terms."}
        ],
        "temperature": 0.7,
        "max_tokens": 500
    }

    # 5.1: Cost-optimized routing
    print("\n--- 5.1: Cost-Optimized Routing ---")
    cost_objective = RoutingObjective(
        primary=ObjectiveType.Cost.value,
        secondary=ObjectiveType.Reliability.value,
        weights={"cost": 0.8, "reliability": 0.2}
    )

    response = await router.route(
        request_intent=request_intent,
        objective=cost_objective
    )

    print(f"Response: {response.content[:100]}...")
    print(f"Key used: {response.metadata.key_used}")
    print(f"Provider: {response.metadata.provider_used}")
    print(f"Estimated cost: ${response.metadata.cost_estimated:.4f}")
    print(f"Actual cost: ${response.metadata.cost_actual:.4f}")
    print(f"Routing explanation: {response.metadata.routing_explanation}")

    # 5.2: Reliability-optimized routing
    print("\n--- 5.2: Reliability-Optimized Routing ---")
    reliability_objective = RoutingObjective(
        primary=ObjectiveType.Reliability.value,
        secondary=ObjectiveType.Cost.value,
        weights={"reliability": 0.9, "cost": 0.1}
    )

    response = await router.route(
        request_intent=request_intent,
        objective=reliability_objective
    )

    print(f"Response: {response.content[:100]}...")
    print(f"Key used: {response.metadata.key_used}")
    print(f"Routing explanation: {response.metadata.routing_explanation}")

    # 5.3: Fairness-based routing (round-robin)
    print("\n--- 5.3: Fairness-Based Routing (Round-Robin) ---")
    fairness_objective = RoutingObjective(
        primary=ObjectiveType.Fairness.value
    )

    # Make multiple requests to see round-robin behavior
    for i in range(3):
        response = await router.route(
            request_intent=request_intent,
            objective=fairness_objective
        )
        print(f"Request {i+1}: Key {response.metadata.key_used} used")

    # 5.4: Multi-objective routing (cost + reliability + speed)
    print("\n--- 5.4: Multi-Objective Routing ---")
    multi_objective = RoutingObjective(
        primary=ObjectiveType.Cost.value,
        secondary=ObjectiveType.Reliability.value,
        tertiary=ObjectiveType.Speed.value,
        weights={"cost": 0.5, "reliability": 0.3, "speed": 0.2}
    )

    response = await router.route(
        request_intent=request_intent,
        objective=multi_objective
    )

    print(f"Key used: {response.metadata.key_used}")
    print(f"Routing explanation: {response.metadata.routing_explanation}")

    # ============================================================================
    # PART 6: AUTOMATIC FAILOVER AND ERROR HANDLING
    # ============================================================================

    print("\n" + "=" * 80)
    print("PART 6: AUTOMATIC FAILOVER AND ERROR HANDLING")
    print("=" * 80)

    # Simulate a key failure scenario
    print("\n--- 6.1: Simulating Key Failure ---")

    # Get current state
    state_summary = router.get_state_summary()
    print(f"Available keys before failure: {state_summary.keys.available}")

    # Manually throttle a key to simulate failure
    # (In real scenario, this would happen automatically on rate limit/error)
    key_to_throttle = list(registered_keys.values())[0]
    router.update_key_state(
        key_id=key_to_throttle.id,
        new_state="Throttled",
        reason="Simulated rate limit for demonstration"
    )
    print(f"✓ Throttled key: {key_to_throttle.id}")

    # Make a request - should automatically use a different key
    response = await router.route(
        request_intent=request_intent,
        objective=RoutingObjective(primary=ObjectiveType.Reliability.value)
    )

    print(f"Request succeeded with key: {response.metadata.key_used}")
    print("Failed key was automatically bypassed")

    # Restore the key
    router.update_key_state(
        key_id=key_to_throttle.id,
        new_state="Available",
        reason="Recovery from simulated failure"
    )
    print(f"✓ Restored key: {key_to_throttle.id}")

    # ============================================================================
    # PART 7: QUOTA AWARENESS AND CAPACITY MANAGEMENT
    # ============================================================================

    print("\n" + "=" * 80)
    print("PART 7: QUOTA AWARENESS AND CAPACITY MANAGEMENT")
    print("=" * 80)

    # Check quota states for all keys
    print("\n--- 7.1: Current Quota States ---")
    state_summary = router.get_state_summary()

    for key_id, key in registered_keys.items():
        quota_state = router.get_quota_state(key_id)
        if quota_state:
            print(f"Key {key_id}:")
            print(f"  Capacity State: {quota_state.capacity_state}")
            print(f"  Remaining: {quota_state.remaining_capacity} tokens")
            print(f"  Used: {quota_state.used_capacity} tokens")
            print(f"  Time Window: {quota_state.time_window}")
            if quota_state.exhaustion_prediction:
                print(f"  Predicted Exhaustion: {quota_state.exhaustion_prediction.predicted_at}")

    # Simulate high usage to trigger quota state transitions
    print("\n--- 7.2: Simulating High Usage ---")

    # Make multiple requests to consume quota
    for i in range(5):
        response = await router.route(
            request_intent=request_intent,
            objective=RoutingObjective(primary=ObjectiveType.Cost.value)
        )
        # Quota is automatically updated after each request
        print(f"Request {i+1}: Used {response.metadata.tokens_used} tokens, "
              f"Cost: ${response.metadata.cost_actual:.4f}")

    # Check quota states again
    print("\n--- 7.3: Updated Quota States ---")
    for key_id, key in registered_keys.items():
        quota_state = router.get_quota_state(key_id)
        if quota_state:
            print(f"Key {key_id}: {quota_state.capacity_state} "
                  f"({quota_state.remaining_capacity} remaining)")

    # ============================================================================
    # PART 8: COST TRACKING AND BUDGET ENFORCEMENT
    # ============================================================================

    print("\n" + "=" * 80)
    print("PART 8: COST TRACKING AND BUDGET ENFORCEMENT")
    print("=" * 80)

    # Get budget status
    print("\n--- 8.1: Budget Status ---")
    budget_status = router.get_budget_status(scope="global")
    print(f"Total spent: ${budget_status.total_spent:.2f}")
    print(f"Budget limit: ${budget_status.budget_limit:.2f}")
    print(f"Remaining: ${budget_status.remaining:.2f}")
    print(f"Usage percentage: {budget_status.usage_percentage:.1f}%")
    print(f"Status: {budget_status.status}")

    # Make a request with cost estimation
    print("\n--- 8.2: Cost Estimation Before Request ---")
    cost_estimate = router.estimate_request_cost(
        request_intent=request_intent,
        provider_id="openai"
    )
    print(f"Estimated cost: ${cost_estimate.estimated_cost:.4f}")
    print(f"Cost range: ${cost_estimate.min_cost:.4f} - ${cost_estimate.max_cost:.4f}")
    print(f"Confidence: {cost_estimate.confidence}")

    # Check if request would exceed budget
    budget_check = router.check_budget(
        request_intent=request_intent,
        estimated_cost=cost_estimate
    )
    print(f"Budget check: {'Allowed' if budget_check.allowed else 'Blocked'}")
    if not budget_check.allowed:
        print(f"Reason: {budget_check.reason}")

    # ============================================================================
    # PART 9: KEY LIFECYCLE MANAGEMENT
    # ============================================================================

    print("\n" + "=" * 80)
    print("PART 9: KEY LIFECYCLE MANAGEMENT")
    print("=" * 80)

    # 9.1: Key rotation
    print("\n--- 9.1: Key Rotation ---")
    key_to_rotate = list(registered_keys.values())[0]
    new_key_material = "sk-example-rotated-key-not-real"

    rotated_key = router.rotate_key(
        old_key_id=key_to_rotate.id,
        new_key_material=new_key_material
    )

    print(f"✓ Rotated key {key_to_rotate.id} to new key {rotated_key.id}")
    print("  Old key state: Disabled")
    print(f"  New key state: {rotated_key.state}")
    print("  Usage history preserved")

    # 9.2: Key revocation
    print("\n--- 9.2: Key Revocation ---")
    key_to_revoke = list(registered_keys.values())[1]

    router.revoke_key(key_id=key_to_revoke.id)
    print(f"✓ Revoked key: {key_to_revoke.id}")
    print("  Key state: Disabled")
    print("  Key excluded from routing")

    # Verify key is excluded
    state_summary = router.get_state_summary()
    print(f"Available keys after revocation: {state_summary.keys.available}")

    # ============================================================================
    # PART 10: OBSERVABILITY AND STATE INSPECTION
    # ============================================================================

    print("\n" + "=" * 80)
    print("PART 10: OBSERVABILITY AND STATE INSPECTION")
    print("=" * 80)

    # 10.1: System state summary
    print("\n--- 10.1: System State Summary ---")
    state_summary = router.get_state_summary()

    print("Keys:")
    print(f"  Total: {state_summary.keys.total}")
    print(f"  Available: {state_summary.keys.available}")
    print(f"  Throttled: {state_summary.keys.throttled}")
    print(f"  Exhausted: {state_summary.keys.exhausted}")
    print(f"  Disabled: {state_summary.keys.disabled}")

    print("\nQuotas:")
    print(f"  Total keys tracked: {state_summary.quotas.total_keys}")
    print(f"  Exhausted keys: {state_summary.quotas.exhausted_keys}")
    print(f"  Critical keys: {state_summary.quotas.critical_keys}")
    print(f"  Constrained keys: {state_summary.quotas.constrained_keys}")

    print("\nRouting:")
    print(f"  Total decisions: {state_summary.routing.total_decisions}")
    print(f"  Recent decisions: {len(state_summary.routing.recent_decisions)}")

    # 10.2: Request trace
    print("\n--- 10.2: Request Trace ---")
    # Get trace for the last request
    if state_summary.routing.recent_decisions:
        last_decision = state_summary.routing.recent_decisions[0]
        trace = router.get_request_trace(request_id=last_decision.request_id)

        print(f"Request ID: {trace.request_id}")
        print(f"Correlation ID: {trace.correlation_id}")
        print(f"Timestamp: {trace.timestamp}")
        print("Routing Decision:")
        print(f"  Key selected: {trace.routing_decision.key_id}")
        print(f"  Provider: {trace.routing_decision.provider_id}")
        print(f"  Objective: {trace.routing_decision.objective}")
        print(f"  Explanation: {trace.routing_decision.explanation}")
        print(f"State Transitions: {len(trace.state_transitions)}")

    # 10.3: Key details
    print("\n--- 10.3: Key Details ---")
    for key_id, key in list(registered_keys.items())[:2]:  # Show first 2 keys
        key_details = router.get_key(key_id)
        if key_details:
            print(f"\nKey: {key_details.id}")
            print(f"  Provider: {key_details.provider_id}")
            print(f"  State: {key_details.state}")
            print(f"  Created: {key_details.created_at}")
            print(f"  Last used: {key_details.last_used_at}")
            print(f"  Usage count: {key_details.usage_count}")
            print(f"  Failure count: {key_details.failure_count}")
            print(f"  Metadata: {key_details.metadata}")

    # ============================================================================
    # PART 11: MULTI-PROVIDER ROUTING
    # ============================================================================

    print("\n" + "=" * 80)
    print("PART 11: MULTI-PROVIDER ROUTING")
    print("=" * 80)

    # Route to different providers
    print("\n--- 11.1: OpenAI Request ---")
    openai_request = {
        "provider_id": "openai",
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "Hello from OpenAI!"}]
    }
    response = await router.route(
        request_intent=openai_request,
        objective=RoutingObjective(primary=ObjectiveType.Cost.value)
    )
    print(f"Provider: {response.metadata.provider_used}")
    print(f"Response: {response.content[:50]}...")

    print("\n--- 11.2: Anthropic Request ---")
    anthropic_request = {
        "provider_id": "anthropic",
        "model": "claude-3-opus",
        "messages": [{"role": "user", "content": "Hello from Anthropic!"}]
    }
    response = await router.route(
        request_intent=anthropic_request,
        objective=RoutingObjective(primary=ObjectiveType.Cost.value)
    )
    print(f"Provider: {response.metadata.provider_used}")
    print(f"Response: {response.content[:50]}...")

    # ============================================================================
    # PART 12: BATCH REQUESTS AND CONCURRENT PROCESSING
    # ============================================================================

    print("\n" + "=" * 80)
    print("PART 12: BATCH REQUESTS AND CONCURRENT PROCESSING")
    print("=" * 80)

    # Make multiple concurrent requests
    print("\n--- 12.1: Concurrent Requests ---")
    requests = [
        {
            "provider_id": "openai",
            "model": "gpt-4",
            "messages": [{"role": "user", "content": f"Request {i}"}]
        }
        for i in range(5)
    ]

    # Execute concurrently
    tasks = [
        router.route(
            request_intent=req,
            objective=RoutingObjective(primary=ObjectiveType.Fairness.value)
        )
        for req in requests
    ]

    responses = await asyncio.gather(*tasks)

    print(f"✓ Completed {len(responses)} concurrent requests")
    for i, response in enumerate(responses):
        print(f"  Request {i+1}: Key {response.metadata.key_used}, "
              f"Cost: ${response.metadata.cost_actual:.4f}")

    # ============================================================================
    # PART 13: POLICY-DRIVEN ROUTING
    # ============================================================================

    print("\n" + "=" * 80)
    print("PART 13: POLICY-DRIVEN ROUTING")
    print("=" * 80)

    # Make requests with different team contexts to trigger different policies
    print("\n--- 13.1: Development Team Request (Cost-Optimized) ---")
    dev_request = {
        **request_intent,
        "team": "development"  # Triggers cost optimization policy
    }
    response = await router.route(
        request_intent=dev_request,
        objective=RoutingObjective(primary=ObjectiveType.Cost.value)
    )
    print(f"Key used: {response.metadata.key_used}")
    print(f"Cost: ${response.metadata.cost_actual:.4f}")
    print(f"Explanation: {response.metadata.routing_explanation}")

    print("\n--- 13.2: Production Team Request (Reliability-First) ---")
    prod_request = {
        **request_intent,
        "team": "production"  # Triggers reliability policy
    }
    response = await router.route(
        request_intent=prod_request,
        objective=RoutingObjective(primary=ObjectiveType.Reliability.value)
    )
    print(f"Key used: {response.metadata.key_used}")
    print(f"Cost: ${response.metadata.cost_actual:.4f}")
    print(f"Explanation: {response.metadata.routing_explanation}")

    # ============================================================================
    # SUMMARY
    # ============================================================================

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    final_state = router.get_state_summary()
    print("\nFinal System State:")
    print(f"  Total keys: {final_state.keys.total}")
    print(f"  Available keys: {final_state.keys.available}")
    print(f"  Total routing decisions: {final_state.routing.total_decisions}")

    budget_status = router.get_budget_status(scope="global")
    print("\nBudget Status:")
    print(f"  Total spent: ${budget_status.total_spent:.2f}")
    print(f"  Remaining: ${budget_status.remaining:.2f}")
    print(f"  Usage: {budget_status.usage_percentage:.1f}%")

    print("\n✓ Comprehensive example completed successfully!")
    print("=" * 80)


# ============================================================================
# PROXY MODE EXAMPLE
# ============================================================================

async def proxy_mode_example():
    """
    Example demonstrating proxy service usage via HTTP API.
    """
    print("\n" + "=" * 80)
    print("PROXY MODE EXAMPLE")
    print("=" * 80)

    import httpx

    # Proxy service is running on localhost:8000
    base_url = "http://localhost:8000"

    # Example 1: OpenAI-compatible chat completion
    print("\n--- Proxy: Chat Completion ---")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": "gpt-4",
                "messages": [
                    {"role": "user", "content": "Hello from proxy!"}
                ]
            }
        )
        result = response.json()
        print(f"Response: {result['choices'][0]['message']['content']}")
        print(f"Key used: {response.headers.get('X-Key-Used')}")
        print(f"Cost: ${result.get('routing_metadata', {}).get('cost_estimated', 0):.4f}")

    # Example 2: Get system state
    print("\n--- Proxy: System State ---")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/api/v1/state",
            headers={"X-API-Key": "your-management-api-key"}
        )
        state = response.json()
        print(f"Available keys: {state['keys']['available']}")
        print(f"Total decisions: {state['routing']['total_decisions']}")

    # Example 3: Register a new key via API
    print("\n--- Proxy: Register Key ---")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/api/v1/keys",
            headers={"X-API-Key": "your-management-api-key"},
            json={
                "key_material": "sk-example-new-key-not-real",
                "provider_id": "openai",
                "metadata": {"tier": "premium"}
            }
        )
        key = response.json()
        print(f"✓ Registered key: {key['id']}")


if __name__ == "__main__":
    # Run comprehensive example
    asyncio.run(comprehensive_example())

    # Uncomment to run proxy mode example (requires proxy service running)
    # asyncio.run(proxy_mode_example())

