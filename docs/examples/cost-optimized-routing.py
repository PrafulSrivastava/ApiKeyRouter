"""
Cost-Optimized Routing Example

This example demonstrates cost-aware routing with ApiKeyRouter:
- Cost estimation before execution
- Cost-optimized routing objective
- Cost tracking and comparison
- Using keys with different cost tiers

Prerequisites:
    Install dependencies:
    pip install apikeyrouter-core

Run with: python cost-optimized-routing.py
"""

import asyncio
import os
from decimal import Decimal
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter
from apikeyrouter.domain.models.routing_decision import RoutingObjective


async def main():
    """Main example function demonstrating cost-optimized routing."""
    
    print("=" * 80)
    print("Cost-Optimized Routing Example")
    print("=" * 80)
    print()
    
    # ============================================================================
    # Step 1: Initialize Router
    # ============================================================================
    
    print("Step 1: Initializing ApiKeyRouter...")
    router = ApiKeyRouter()
    await router.register_provider("openai", OpenAIAdapter())
    print("✓ Router initialized")
    print()
    
    # ============================================================================
    # Step 2: Register Keys with Different Cost Tiers
    # ============================================================================
    
    print("Step 2: Registering keys with different cost tiers...")
    
    # Get API keys from environment or use placeholders
    key1 = os.getenv("OPENAI_KEY_1", "sk-placeholder-1")
    key2 = os.getenv("OPENAI_KEY_2", "sk-placeholder-2")
    key3 = os.getenv("OPENAI_KEY_3", "sk-placeholder-3")
    
    # Register keys with cost metadata
    # Premium tier - higher cost but better rate limits
    premium_key = await router.register_key(
        key_material=key1,
        provider_id="openai",
        metadata={
            "tier": "premium",
            "cost_per_1k": "0.03",  # $0.03 per 1k tokens
            "rate_limit": "high"
        }
    )
    print(f"✓ Registered premium key: {premium_key.id} (cost: $0.03/1k)")
    
    # Standard tier - medium cost
    standard_key = await router.register_key(
        key_material=key2,
        provider_id="openai",
        metadata={
            "tier": "standard",
            "cost_per_1k": "0.01",  # $0.01 per 1k tokens
            "rate_limit": "medium"
        }
    )
    print(f"✓ Registered standard key: {standard_key.id} (cost: $0.01/1k)")
    
    # Budget tier - lowest cost
    budget_key = await router.register_key(
        key_material=key3,
        provider_id="openai",
        metadata={
            "tier": "budget",
            "cost_per_1k": "0.005",  # $0.005 per 1k tokens
            "rate_limit": "low"
        }
    )
    print(f"✓ Registered budget key: {budget_key.id} (cost: $0.005/1k)")
    print()
    
    # ============================================================================
    # Step 3: Cost Estimation
    # ============================================================================
    
    print("Step 3: Estimating request costs...")
    
    intent = RequestIntent(
        model="gpt-4",
        messages=[
            Message(role="user", content="Write a short story about a robot learning to paint.")
        ],
        provider_id="openai"
    )
    
    # Get cost controller
    cost_controller = router.cost_controller
    
    # Estimate cost for each key
    print("\n  Cost estimates for each key:")
    for key_id in [premium_key.id, standard_key.id, budget_key.id]:
        try:
            estimate = await cost_controller.estimate_request_cost(
                request_intent=intent,
                provider_id="openai",
                key_id=key_id
            )
            key = await router.key_manager.get_key(key_id)
            tier = key.metadata.get("tier", "unknown")
            print(f"    {tier.capitalize()} key ({key_id[:8]}...): ${estimate.amount} (confidence: {estimate.confidence:.2f})")
        except Exception as e:
            print(f"    Error estimating cost for {key_id[:8]}...: {e}")
    
    print()
    
    # ============================================================================
    # Step 4: Cost-Optimized Routing
    # ============================================================================
    
    print("Step 4: Using cost-optimized routing...")
    
    # Route with cost objective - automatically selects cheapest available key
    print("\n  Routing with 'cost' objective:")
    try:
        response = await router.route(intent, objective="cost")
        print(f"    ✓ Request completed")
        print(f"    Key used: {response.metadata.key_used}")
        
        # Get key metadata to show cost tier
        used_key = await router.key_manager.get_key(response.metadata.key_used)
        tier = used_key.metadata.get("tier", "unknown")
        print(f"    Key tier: {tier}")
        
        if response.cost:
            print(f"    Actual cost: ${response.cost.amount}")
        
        if response.metadata.tokens_used:
            tokens = response.metadata.tokens_used.total_tokens
            print(f"    Tokens used: {tokens}")
            if response.cost:
                cost_per_1k = (response.cost.amount / Decimal(tokens)) * Decimal("1000")
                print(f"    Effective cost per 1k tokens: ${cost_per_1k:.4f}")
        
    except Exception as e:
        print(f"    ✗ Error: {e}")
    
    print()
    
    # ============================================================================
    # Step 5: Cost Comparison
    # ============================================================================
    
    print("Step 5: Comparing routing strategies...")
    
    objectives = [
        ("cost", "Cost optimization"),
        ("reliability", "Reliability optimization"),
        ("fairness", "Fair distribution")
    ]
    
    print("\n  Routing with different objectives:")
    for obj_name, obj_desc in objectives:
        try:
            response = await router.route(intent, objective=obj_name)
            used_key = await router.key_manager.get_key(response.metadata.key_used)
            tier = used_key.metadata.get("tier", "unknown")
            cost = response.cost.amount if response.cost else Decimal("0")
            
            print(f"    {obj_desc}:")
            print(f"      Key tier: {tier}")
            print(f"      Cost: ${cost}")
            print(f"      Key ID: {response.metadata.key_used[:8]}...")
        except Exception as e:
            print(f"    {obj_desc}: Error - {e}")
    
    print()
    
    # ============================================================================
    # Step 6: Multi-Objective Routing
    # ============================================================================
    
    print("Step 6: Multi-objective routing (cost + reliability)...")
    
    # Combine cost and reliability objectives
    objective = RoutingObjective(
        primary="cost",
        secondary=["reliability"],
        weights={"cost": 0.7, "reliability": 0.3},
        constraints={"min_reliability": 0.8}  # Minimum reliability threshold
    )
    
    try:
        response = await router.route(intent, objective=objective)
        used_key = await router.key_manager.get_key(response.metadata.key_used)
        tier = used_key.metadata.get("tier", "unknown")
        cost = response.cost.amount if response.cost else Decimal("0")
        
        print(f"    ✓ Request completed")
        print(f"    Key tier: {tier}")
        print(f"    Cost: ${cost}")
        print(f"    Explanation: {response.metadata.routing_explanation if hasattr(response.metadata, 'routing_explanation') else 'N/A'}")
    except Exception as e:
        print(f"    ✗ Error: {e}")
    
    print()
    
    # ============================================================================
    # Step 7: Cost Tracking Summary
    # ============================================================================
    
    print("Step 7: Cost tracking summary...")
    
    # Get all keys and their usage
    all_keys = await router.state_store.list_keys(provider_id="openai")
    
    total_cost = Decimal("0")
    print("\n  Key usage and costs:")
    for key in all_keys:
        tier = key.metadata.get("tier", "unknown")
        cost_per_1k = Decimal(key.metadata.get("cost_per_1k", "0"))
        
        # Estimate cost based on usage (simplified)
        # In production, actual costs would be tracked
        estimated_cost = Decimal("0")  # Would be calculated from actual usage
        
        print(f"    {tier.capitalize()} key ({key.id[:8]}...):")
        print(f"      Usage count: {key.usage_count}")
        print(f"      Cost per 1k: ${cost_per_1k}")
        print(f"      Estimated total cost: ${estimated_cost}")
        
        total_cost += estimated_cost
    
    print(f"\n  Total estimated cost: ${total_cost}")
    print()
    
    print("=" * 80)
    print("Example completed!")
    print("=" * 80)
    print()
    print("Key takeaways:")
    print("  - Cost-optimized routing automatically selects cheapest available key")
    print("  - Cost estimation happens before execution")
    print("  - Multi-objective routing balances cost with other factors")
    print("  - Cost metadata helps router make informed decisions")
    print()


if __name__ == "__main__":
    asyncio.run(main())

