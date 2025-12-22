"""
Budget Enforcement Example

This example demonstrates budget management with ApiKeyRouter:
- Creating budgets with different scopes
- Hard and soft enforcement modes
- Budget checking before execution
- Handling budget violations

Prerequisites:
    Install dependencies:
    pip install apikeyrouter-core

Run with: python budget-enforcement.py
"""

import asyncio
import os
from decimal import Decimal
from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.models.request_intent import RequestIntent, Message
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter
from apikeyrouter.domain.models.budget import BudgetScope, EnforcementMode, TimeWindow
from apikeyrouter.domain.components.cost_controller import BudgetExceededError


async def main():
    """Main example function demonstrating budget enforcement."""
    
    print("=" * 80)
    print("Budget Enforcement Example")
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
    # Step 2: Register Keys
    # ============================================================================
    
    print("Step 2: Registering API keys...")
    
    key1 = os.getenv("OPENAI_KEY_1", "sk-placeholder-1")
    key2 = os.getenv("OPENAI_KEY_2", "sk-placeholder-2")
    
    await router.register_key(key1, "openai", metadata={"cost_per_1k": "0.03"})
    await router.register_key(key2, "openai", metadata={"cost_per_1k": "0.01"})
    
    print("✓ Keys registered")
    print()
    
    # ============================================================================
    # Step 3: Create Budgets
    # ============================================================================
    
    print("Step 3: Creating budgets...")
    
    cost_controller = router.cost_controller
    
    # Global daily budget with hard enforcement
    global_budget = await cost_controller.create_budget(
        scope=BudgetScope.Global,
        limit=Decimal("100.00"),  # $100 daily limit
        period=TimeWindow.Daily,
        enforcement_mode=EnforcementMode.Hard  # Reject requests that exceed budget
    )
    print(f"✓ Created global budget: ${global_budget.limit} per day (hard enforcement)")
    print(f"  Budget ID: {global_budget.id}")
    
    # Per-provider budget with soft enforcement
    provider_budget = await cost_controller.create_budget(
        scope=BudgetScope.PerProvider,
        limit=Decimal("50.00"),  # $50 per provider
        period=TimeWindow.Daily,
        enforcement_mode=EnforcementMode.Soft,  # Allow but log violations
        scope_id="openai"
    )
    print(f"✓ Created provider budget: ${provider_budget.limit} per day for 'openai' (soft enforcement)")
    print(f"  Budget ID: {provider_budget.id}")
    
    print()
    
    # ============================================================================
    # Step 4: Budget Checking
    # ============================================================================
    
    print("Step 4: Checking budgets before execution...")
    
    intent = RequestIntent(
        model="gpt-4",
        messages=[
            Message(role="user", content="Explain quantum computing in simple terms.")
        ],
        provider_id="openai"
    )
    
    # Get a key for cost estimation
    keys = await router.state_store.list_keys(provider_id="openai")
    if keys:
        key_id = keys[0].id
        
        # Estimate cost
        cost_estimate = await cost_controller.estimate_request_cost(
            request_intent=intent,
            provider_id="openai",
            key_id=key_id
        )
        print(f"  Estimated cost: ${cost_estimate.amount}")
        
        # Check budget
        budget_check = await cost_controller.check_budget(
            request_intent=intent,
            cost_estimate=cost_estimate,
            provider_id="openai",
            key_id=key_id
        )
        
        print(f"  Budget check result:")
        print(f"    Allowed: {budget_check.allowed}")
        if budget_check.violated_budgets:
            print(f"    Violated budgets: {budget_check.violated_budgets}")
        if budget_check.remaining_budgets:
            print(f"    Remaining budgets: {budget_check.remaining_budgets}")
    
    print()
    
    # ============================================================================
    # Step 5: Hard Enforcement
    # ============================================================================
    
    print("Step 5: Testing hard enforcement...")
    
    # Simulate spending most of the budget
    await cost_controller.update_spending(global_budget.id, Decimal("99.00"))
    print(f"  Updated spending: $99.00 / ${global_budget.limit}")
    
    # Try to make a request that would exceed budget
    try:
        response = await router.route(intent, objective="cost")
        print(f"  ✓ Request succeeded")
        print(f"    Cost: ${response.cost.amount if response.cost else Decimal('0')}")
    except BudgetExceededError as e:
        print(f"  ✗ Budget exceeded (expected with hard enforcement)")
        print(f"    Message: {e.message}")
        print(f"    Remaining budget: ${e.remaining_budget}")
        print(f"    Violated budgets: {e.violated_budgets}")
        print(f"    Cost estimate: ${e.cost_estimate}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    print()
    
    # ============================================================================
    # Step 6: Soft Enforcement
    # ============================================================================
    
    print("Step 6: Testing soft enforcement...")
    
    # Reset spending for provider budget
    await cost_controller.update_spending(provider_budget.id, Decimal("0.00"))
    
    # Simulate spending most of provider budget
    await cost_controller.update_spending(provider_budget.id, Decimal("49.00"))
    print(f"  Updated provider spending: $49.00 / ${provider_budget.limit}")
    
    # Try to make a request that would exceed soft budget
    # Soft enforcement allows the request but logs the violation
    try:
        response = await router.route(intent, objective="cost")
        print(f"  ✓ Request succeeded (soft enforcement allows it)")
        print(f"    Cost: ${response.cost.amount if response.cost else Decimal('0')}")
        print(f"    Note: Budget violation logged but request allowed")
    except BudgetExceededError as e:
        print(f"  ✗ Budget exceeded: {e.message}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    print()
    
    # ============================================================================
    # Step 7: Budget Management
    # ============================================================================
    
    print("Step 7: Budget management operations...")
    
    # Get budget status
    updated_global = await cost_controller.get_budget(global_budget.id)
    print(f"  Global budget status:")
    print(f"    Limit: ${updated_global.limit}")
    print(f"    Current spending: ${updated_global.current_spending}")
    print(f"    Remaining: ${updated_global.limit - updated_global.current_spending}")
    print(f"    Period: {updated_global.period.value}")
    print(f"    Enforcement: {updated_global.enforcement_mode.value}")
    
    # Update spending
    await cost_controller.update_spending(global_budget.id, Decimal("10.00"))
    print(f"\n  Updated global budget spending to $10.00")
    
    # Get updated status
    updated_global = await cost_controller.get_budget(global_budget.id)
    print(f"    New remaining: ${updated_global.limit - updated_global.current_spending}")
    
    print()
    
    # ============================================================================
    # Step 8: Budget Reset
    # ============================================================================
    
    print("Step 8: Budget reset (time window)...")
    
    print("  Budgets automatically reset based on time window:")
    print(f"    Global budget: Resets daily at {updated_global.reset_at if hasattr(updated_global, 'reset_at') else 'midnight UTC'}")
    print(f"    Provider budget: Resets daily")
    print("  After reset, spending resets to $0.00")
    
    print()
    
    print("=" * 80)
    print("Example completed!")
    print("=" * 80)
    print()
    print("Key takeaways:")
    print("  - Hard enforcement rejects requests that would exceed budget")
    print("  - Soft enforcement allows requests but logs violations")
    print("  - Budgets can be scoped globally, per-provider, or per-key")
    print("  - Budgets automatically reset based on time window")
    print("  - Cost estimation happens before execution")
    print()


if __name__ == "__main__":
    asyncio.run(main())

