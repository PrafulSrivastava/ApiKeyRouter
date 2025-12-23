"""
Basic ApiKeyRouter Usage Example

This example demonstrates the fundamental usage of ApiKeyRouter:
- Initializing the router
- Registering providers and API keys
- Making requests with routing
- Basic error handling

Prerequisites:
    Install dependencies:
    pip install apikeyrouter-core

    Or from source:
    cd packages/core
    poetry install

Run with: python basic-usage.py
"""

import asyncio
import os

from apikeyrouter import ApiKeyRouter
from apikeyrouter.domain.components.routing_engine import NoEligibleKeysError
from apikeyrouter.domain.models.request_intent import Message, RequestIntent
from apikeyrouter.domain.models.system_error import SystemError
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter


async def main():
    """Main example function demonstrating basic ApiKeyRouter usage."""

    print("=" * 80)
    print("ApiKeyRouter Basic Usage Example")
    print("=" * 80)
    print()

    # ============================================================================
    # Step 1: Initialize ApiKeyRouter
    # ============================================================================

    print("Step 1: Initializing ApiKeyRouter...")
    router = ApiKeyRouter()
    print("✓ Router initialized")
    print()

    # ============================================================================
    # Step 2: Register Provider
    # ============================================================================

    print("Step 2: Registering provider...")
    openai_adapter = OpenAIAdapter()
    await router.register_provider("openai", openai_adapter)
    print("✓ Provider 'openai' registered")
    print()

    # ============================================================================
    # Step 3: Register API Keys
    # ============================================================================

    print("Step 3: Registering API keys...")

    # Get API keys from environment variables or use placeholders
    # In production, use environment variables or secure key management
    api_key_1 = os.getenv("OPENAI_API_KEY_1", "sk-example-key-1-not-a-real-key")
    api_key_2 = os.getenv("OPENAI_API_KEY_2", "sk-example-key-2-not-a-real-key")

    if "placeholder" in api_key_1:
        print("⚠️  Using placeholder keys. Set OPENAI_API_KEY_1 and OPENAI_API_KEY_2 environment variables for real keys.")
        print()

    # Register multiple keys for the same provider
    key1 = await router.register_key(
        key_material=api_key_1,
        provider_id="openai",
        metadata={"tier": "premium", "region": "us-east"}
    )
    print(f"✓ Registered key: {key1.id} (state: {key1.state.value})")

    key2 = await router.register_key(
        key_material=api_key_2,
        provider_id="openai",
        metadata={"tier": "paygo", "region": "us-west"}
    )
    print(f"✓ Registered key: {key2.id} (state: {key2.state.value})")
    print()

    # ============================================================================
    # Step 4: Make a Request
    # ============================================================================

    print("Step 4: Making a request...")

    # Create a request intent
    intent = RequestIntent(
        model="gpt-4",
        messages=[
            Message(role="user", content="Hello! Say 'Hello from ApiKeyRouter' if you can read this.")
        ],
        provider_id="openai"
    )

    try:
        # Route the request (router automatically selects best key)
        response = await router.route(intent)

        print("✓ Request completed successfully")
        print(f"  Response: {response.content[:100]}...")  # Show first 100 chars
        print(f"  Key used: {response.metadata.key_used}")
        print(f"  Model: {response.metadata.model}")

        if response.metadata.tokens_used:
            print(f"  Tokens used: {response.metadata.tokens_used.total_tokens}")

        if response.cost:
            print(f"  Cost: ${response.cost.amount}")

        # Show routing explanation if available
        if hasattr(response.metadata, 'routing_explanation'):
            print(f"  Routing explanation: {response.metadata.routing_explanation}")

    except NoEligibleKeysError as e:
        print(f"✗ No eligible keys available: {e}")
        print("  This can happen if:")
        print("  - All keys are exhausted or rate limited")
        print("  - All keys are in unavailable state")
        print("  - No keys are registered")

    except SystemError as e:
        print(f"✗ System error: {e.category.value} - {e.message}")
        if e.retryable:
            print(f"  This error is retryable. Retry after: {e.retry_after} seconds" if e.retry_after else "  This error is retryable.")
        else:
            print("  This error is not retryable.")

    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        print(f"  Error type: {type(e).__name__}")

    print()

    # ============================================================================
    # Step 5: Using Different Routing Objectives
    # ============================================================================

    print("Step 5: Using different routing objectives...")

    # Fairness (default) - distributes load evenly
    print("\n  Fairness objective (default):")
    try:
        response = await router.route(intent, objective="fairness")
        print(f"    ✓ Key used: {response.metadata.key_used}")
    except Exception as e:
        print(f"    ✗ Error: {e}")

    # Cost optimization - selects cheapest key
    print("\n  Cost objective:")
    try:
        response = await router.route(intent, objective="cost")
        print(f"    ✓ Key used: {response.metadata.key_used}")
    except Exception as e:
        print(f"    ✗ Error: {e}")

    # Reliability optimization - selects most reliable key
    print("\n  Reliability objective:")
    try:
        response = await router.route(intent, objective="reliability")
        print(f"    ✓ Key used: {response.metadata.key_used}")
    except Exception as e:
        print(f"    ✗ Error: {e}")

    print()

    # ============================================================================
    # Step 6: Check System State
    # ============================================================================

    print("Step 6: Checking system state...")

    # Get all registered keys
    all_keys = await router.state_store.list_keys(provider_id="openai")
    print(f"  Total keys registered: {len(all_keys)}")

    for key in all_keys:
        print(f"    - Key {key.id}: state={key.state.value}, usage={key.usage_count}, failures={key.failure_count}")

    print()

    print("=" * 80)
    print("Example completed!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("  1. Read the User Guide: docs/guides/user-guide.md")
    print("  2. Check API Reference: docs/api/API_REFERENCE.md")
    print("  3. See more examples: docs/examples/")
    print()


if __name__ == "__main__":
    # Run the example
    asyncio.run(main())

