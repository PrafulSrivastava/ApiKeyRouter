"""Example: Key Rotation with Load Balancing

This example demonstrates how to use the routing engine with fairness objective
to distribute load across multiple API keys, preventing any single key from
being overstressed.

Scenario:
- 2 OpenAI API keys in the store
- Multiple requests need to be routed
- Goal: Distribute load evenly across both keys
"""

import asyncio
import os
from datetime import datetime

# Set encryption key for key material encryption (required)
# In production, use a secure key from environment or secrets manager
os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = os.getenv(
    "APIKEYROUTER_ENCRYPTION_KEY",
    "example-encryption-key-32-chars-long!!",  # 32+ chars for AES-256
)

from apikeyrouter.domain.components.key_manager import KeyManager
from apikeyrouter.domain.components.routing_engine import RoutingEngine
from apikeyrouter.domain.interfaces.observability_manager import (
    ObservabilityManager,
)
from apikeyrouter.domain.models.routing_decision import (
    ObjectiveType,
    RoutingObjective,
)
from apikeyrouter.infrastructure.state_store.memory_store import InMemoryStateStore


class SimpleObservabilityManager(ObservabilityManager):
    """Simple observability manager for examples."""

    async def emit_event(
        self,
        event_type: str,
        payload: dict,
        metadata: dict | None = None,
    ) -> None:
        """Emit an event (no-op for this example)."""
        pass

    async def log(
        self,
        level: str,
        message: str,
        context: dict | None = None,
    ) -> None:
        """Log a message (no-op for this example)."""
        pass


async def demonstrate_key_rotation() -> None:
    """Demonstrate key rotation with 2 OpenAI keys."""
    print("=" * 70)
    print("Key Rotation Example: Load Balancing Across 2 OpenAI Keys")
    print("=" * 70)

    # Initialize components
    store = InMemoryStateStore()
    observability = SimpleObservabilityManager()
    key_manager = KeyManager(
        state_store=store,
        observability_manager=observability,
    )
    routing_engine = RoutingEngine(
        key_manager=key_manager,
        state_store=store,
        observability_manager=observability,
    )

    # Step 1: Register 2 OpenAI keys
    print("\n[Step 1] Registering 2 OpenAI API keys...")
    key1 = await key_manager.register_key(
        key_material="sk-openai-key-1-encrypted-material",
        provider_id="openai",
        metadata={"tier": "standard", "account": "account-1"},
    )
    print(f"  [OK] Registered Key 1: {key1.id} (provider: {key1.provider_id}, state: {key1.state.value})")

    key2 = await key_manager.register_key(
        key_material="sk-openai-key-2-encrypted-material",
        provider_id="openai",
        metadata={"tier": "standard", "account": "account-2"},
    )
    print(f"  [OK] Registered Key 2: {key2.id} (provider: {key2.provider_id}, state: {key2.state.value})")

    # Verify keys are stored
    all_keys = await store.list_keys(provider_id="openai")
    print(f"  [OK] Verified: {len(all_keys)} keys found in store for 'openai' provider")

    # Step 2: Configure routing objective for fairness
    print("\n[Step 2] Configuring routing for fairness (load balancing)...")
    fairness_objective = RoutingObjective(
        primary=ObjectiveType.Fairness.value,
        explanation="Distribute load evenly across all keys",
    )
    print(f"  [OK] Routing objective: {fairness_objective.primary}")
    print("    This will select keys with lower usage counts first")

    # Step 3: Make multiple requests and observe key rotation
    print("\n[Step 3] Making 10 requests to observe load distribution...")
    print("-" * 70)

    request_count = 10
    key_usage: dict[str, int] = {key1.id: 0, key2.id: 0}

    for i in range(request_count):
        # Create request intent
        request_intent = {
            "provider_id": "openai",
            "request_id": f"req_{i+1}",
            "model": "gpt-4",
            "messages": [{"role": "user", "content": f"Request {i+1}"}],
        }

        # Route the request
        decision = await routing_engine.route_request(
            request_intent=request_intent,
            objective=fairness_objective,
        )

        # Track which key was selected
        selected_key_id = decision.selected_key_id
        key_usage[selected_key_id] = key_usage.get(selected_key_id, 0) + 1

        # Update key usage count (simulate actual usage)
        selected_key = await key_manager.get_key(selected_key_id)
        if selected_key:
            selected_key.usage_count += 1
            await store.save_key(selected_key)

        # Display decision
        print(
            f"Request {i+1:2d}: Selected {selected_key_id} "
            f"({decision.explanation[:50]}...)"
        )

    # Step 4: Analyze load distribution
    print("\n" + "-" * 70)
    print("[Step 4] Load Distribution Analysis")
    print("-" * 70)

    # Get updated key states
    updated_key1 = await key_manager.get_key(key1.id)
    updated_key2 = await key_manager.get_key(key2.id)

    print(f"\nKey 1 ({key1.id}):")
    print(f"  Usage count: {updated_key1.usage_count if updated_key1 else 0}")
    print(f"  Selected: {key_usage.get(key1.id, 0)} times")

    print(f"\nKey 2 ({key2.id}):")
    print(f"  Usage count: {updated_key2.usage_count if updated_key2 else 0}")
    print(f"  Selected: {key_usage.get(key2.id, 0)} times")

    # Calculate distribution
    total_requests = sum(key_usage.values())
    key1_percentage = (key_usage.get(key1.id, 0) / total_requests * 100) if total_requests > 0 else 0
    key2_percentage = (key_usage.get(key2.id, 0) / total_requests * 100) if total_requests > 0 else 0

    print(f"\nLoad Distribution:")
    print(f"  Key 1: {key_usage.get(key1.id, 0)}/{total_requests} requests ({key1_percentage:.1f}%)")
    print(f"  Key 2: {key_usage.get(key2.id, 0)}/{total_requests} requests ({key2_percentage:.1f}%)")

    # Step 5: Demonstrate how fairness prevents overstressing
    print("\n" + "-" * 70)
    print("[Step 5] How Fairness Prevents Overstressing")
    print("-" * 70)

    print("\nThe fairness objective works by:")
    print("  1. Scoring keys inversely to their usage count")
    print("  2. Keys with lower usage get higher scores")
    print("  3. The routing engine selects the key with the highest score")
    print("\nThis ensures:")
    print("  [OK] Keys with less usage are preferred")
    print("  [OK] Load is automatically balanced across all keys")
    print("  [OK] No single key gets overstressed")

    # Step 6: Show what happens with uneven initial usage
    print("\n" + "-" * 70)
    print("[Step 6] Demonstrating Self-Correction")
    print("-" * 70)

    # Manually set key1 to have more usage
    if updated_key1:
        updated_key1.usage_count = 10
        await store.save_key(updated_key1)

    if updated_key2:
        updated_key2.usage_count = 2
        await store.save_key(updated_key2)

    print("\nSimulating scenario where Key 1 has been used more:")
    print(f"  Key 1 usage: {updated_key1.usage_count if updated_key1 else 0}")
    print(f"  Key 2 usage: {updated_key2.usage_count if updated_key2 else 0}")

    print("\nMaking 5 more requests...")
    key1_selections = 0
    key2_selections = 0
    for i in range(5):
        request_intent = {
            "provider_id": "openai",
            "request_id": f"req_correct_{i+1}",
        }
        # Get current usage before routing to show fairness in action
        current_key1 = await key_manager.get_key(key1.id)
        current_key2 = await key_manager.get_key(key2.id)
        if i == 0:
            print(f"\n  Before routing - Key 1 usage: {current_key1.usage_count if current_key1 else 0}, Key 2 usage: {current_key2.usage_count if current_key2 else 0}")
        
        decision = await routing_engine.route_request(
            request_intent=request_intent,
            objective=fairness_objective,
        )
        selected_key = await key_manager.get_key(decision.selected_key_id)
        if selected_key:
            selected_key.usage_count += 1
            await store.save_key(selected_key)
            # Track which key was selected
            if selected_key.id == key1.id:
                key1_selections += 1
                key_name = "Key 1"
            elif selected_key.id == key2.id:
                key2_selections += 1
                key_name = "Key 2"
            else:
                key_name = selected_key.id
            print(f"  Request {i+1}: Selected {key_name} (usage now: {selected_key.usage_count})")

    # Check final distribution
    final_key1 = await key_manager.get_key(key1.id)
    final_key2 = await key_manager.get_key(key2.id)

    print("\nFinal usage counts:")
    print(f"  Key 1: {final_key1.usage_count if final_key1 else 0} requests")
    print(f"  Key 2: {final_key2.usage_count if final_key2 else 0} requests")
    
    print(f"\nSelection summary in this round:")
    print(f"  Key 1: {key1_selections} times")
    print(f"  Key 2: {key2_selections} times")
    
    if key2_selections > key1_selections:
        print("\n[OK] Key 2 (with lower initial usage) was preferred!")
        print("     This demonstrates fairness: keys with less usage get higher scores.")
    elif key1_selections > key2_selections:
        print("\n[WARNING] Key 1 was selected more - this shouldn't happen with fairness!")
        print("          Key 2 should be preferred since it has lower usage.")
    else:
        print("\n[OK] Both keys selected equally (usage counts were close).")

    # Step 7: Query routing decisions for audit
    print("\n" + "-" * 70)
    print("[Step 7] Querying Routing Decisions (Audit Trail)")
    print("-" * 70)

    from apikeyrouter.domain.interfaces.state_store import StateQuery

    # Query all routing decisions
    query = StateQuery(entity_type="RoutingDecision", provider_id="openai")
    decisions = await store.query_state(query)

    print(f"\nTotal routing decisions stored: {len(decisions)}")

    # Count decisions per key
    decision_counts: dict[str, int] = {}
    for decision in decisions:
        key_id = decision.selected_key_id
        decision_counts[key_id] = decision_counts.get(key_id, 0) + 1

    print("\nRouting decisions per key:")
    for key_id, count in decision_counts.items():
        print(f"  {key_id}: {count} decisions")

    print("\n" + "=" * 70)
    print("[SUCCESS] Key Rotation Example Complete!")
    print("=" * 70)
    print("\nKey Takeaways:")
    print("  1. Use RoutingObjective with 'fairness' primary objective")
    print("  2. The routing engine automatically balances load")
    print("  3. Keys with lower usage are preferred")
    print("  4. All routing decisions are stored for audit")
    print("  5. The system self-corrects when usage becomes uneven")


async def demonstrate_round_robin_alternative() -> None:
    """Demonstrate round-robin as an alternative to fairness."""
    print("\n" + "=" * 70)
    print("Alternative: Round-Robin Routing (No Objective)")
    print("=" * 70)

    store = InMemoryStateStore()
    observability = SimpleObservabilityManager()
    key_manager = KeyManager(
        state_store=store,
        observability_manager=observability,
    )
    routing_engine = RoutingEngine(
        key_manager=key_manager,
        state_store=store,
        observability_manager=observability,
    )

    # Register 2 keys
    key1 = await key_manager.register_key(
        key_material="sk-openai-key-1",
        provider_id="openai",
    )
    key2 = await key_manager.register_key(
        key_material="sk-openai-key-2",
        provider_id="openai",
    )

    print(f"\nRegistered 2 keys: {key1.id}, {key2.id}")
    print("\nMaking 6 requests with NO objective (defaults to fairness/round-robin)...")

    selections = []
    for i in range(6):
        request_intent = {
            "provider_id": "openai",
            "request_id": f"rr_req_{i+1}",
        }
        # No objective = defaults to fairness
        decision = await routing_engine.route_request(request_intent=request_intent)
        selections.append(decision.selected_key_id)
        print(f"  Request {i+1}: {decision.selected_key_id}")

    print(f"\nSelection pattern: {selections}")
    print("[OK] Round-robin alternates between keys automatically!")


async def main() -> None:
    """Run the key rotation examples."""
    await demonstrate_key_rotation()
    await demonstrate_round_robin_alternative()


if __name__ == "__main__":
    asyncio.run(main())

