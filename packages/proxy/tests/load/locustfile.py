"""Locust load testing for ApiKeyRouter Proxy service.

This file defines load test scenarios for the proxy service:
- Normal load (baseline)
- High load (stress test)
- Failure scenarios (degraded performance)
- Concurrent key switching

Usage:
    # Run with web UI
    locust -f locustfile.py --host=http://localhost:8000

    # Run headless
    locust -f locustfile.py --host=http://localhost:8000 --headless \
        --users 100 --spawn-rate 10 --run-time 5m

    # Run specific scenario
    locust -f locustfile.py --host=http://localhost:8000 \
        -u 100 -r 10 -t 5m --tags normal_load
"""

import random

from locust import HttpUser, TaskSet, between, tag, task


class ChatCompletionsTasks(TaskSet):
    """Task set for chat completions endpoint."""

    @task(10)
    @tag("normal_load", "high_load")
    def chat_completion_basic(self):
        """Basic chat completion request."""
        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "Hello, how are you?"}
            ],
            "temperature": 0.7,
            "max_tokens": 100,
        }
        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            catch_response=True,
            name="chat_completion_basic",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                response.failure("Rate limit exceeded")
            elif response.status_code >= 500:
                response.failure(f"Server error: {response.status_code}")
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(5)
    @tag("normal_load", "high_load")
    def chat_completion_multiple_messages(self):
        """Chat completion with multiple messages."""
        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is the capital of France?"},
                {"role": "assistant", "content": "The capital of France is Paris."},
                {"role": "user", "content": "Tell me more about it."},
            ],
            "temperature": 0.8,
            "max_tokens": 200,
        }
        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            catch_response=True,
            name="chat_completion_multiple_messages",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")

    @task(2)
    @tag("normal_load", "high_load")
    def chat_completion_streaming(self):
        """Chat completion with streaming (if supported)."""
        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "Write a short story."}
            ],
            "stream": True,
            "temperature": 0.9,
            "max_tokens": 500,
        }
        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            catch_response=True,
            name="chat_completion_streaming",
            stream=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")

    @task(1)
    @tag("normal_load")
    def chat_completion_different_models(self):
        """Chat completion with different models."""
        models = ["gpt-4", "gpt-3.5-turbo", "gpt-4-turbo"]
        payload = {
            "model": random.choice(models),
            "messages": [
                {"role": "user", "content": f"Test message for {random.choice(models)}"}
            ],
            "temperature": 0.7,
            "max_tokens": 50,
        }
        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            catch_response=True,
            name="chat_completion_different_models",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")


class ManagementTasks(TaskSet):
    """Task set for management API endpoints."""

    @task(3)
    @tag("normal_load")
    def health_check(self):
        """Health check endpoint."""
        with self.client.get(
            "/health",
            catch_response=True,
            name="health_check",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")

    @task(1)
    @tag("normal_load")
    def list_models(self):
        """List available models."""
        with self.client.get(
            "/v1/models",
            catch_response=True,
            name="list_models",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")


class NormalLoadUser(HttpUser):
    """Normal load scenario - baseline performance testing.

    Simulates typical usage patterns with moderate concurrency.
    """

    tasks = [ChatCompletionsTasks, ManagementTasks]
    wait_time = between(1, 3)  # Wait 1-3 seconds between requests
    weight = 1  # Default weight

    def on_start(self):
        """Called when a user starts."""
        # Optional: Set up user session
        pass


class HighLoadUser(HttpUser):
    """High load scenario - stress testing.

    Simulates high concurrency and rapid request rate.
    """

    tasks = [ChatCompletionsTasks]
    wait_time = between(0.1, 0.5)  # Wait 0.1-0.5 seconds between requests
    weight = 2  # Higher weight for stress testing

    @task
    @tag("high_load", "stress")
    def rapid_requests(self):
        """Rapid fire requests for stress testing."""
        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": "Quick test"}
            ],
            "max_tokens": 50,
        }
        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            catch_response=True,
            name="rapid_requests",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 429:
                # Rate limiting is expected under high load
                response.success()
            else:
                response.failure(f"Status: {response.status_code}")


class FailureScenarioUser(HttpUser):
    """Failure scenario - test graceful degradation.

    Simulates scenarios that may cause failures to test error handling.
    """

    tasks = [ChatCompletionsTasks]
    wait_time = between(0.5, 2)
    weight = 1

    @task
    @tag("failure_scenario")
    def invalid_request(self):
        """Send invalid requests to test error handling."""
        # Invalid payload (missing required fields)
        payload = {
            "model": "gpt-4",
            # Missing "messages" field
        }
        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            catch_response=True,
            name="invalid_request",
        ) as response:
            # 400 is expected for invalid requests
            if response.status_code == 400:
                response.success()
            else:
                response.failure(f"Expected 400, got {response.status_code}")

    @task
    @tag("failure_scenario")
    def invalid_model(self):
        """Request with invalid model name."""
        payload = {
            "model": "invalid-model-name-12345",
            "messages": [
                {"role": "user", "content": "Test"}
            ],
        }
        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            catch_response=True,
            name="invalid_model",
        ) as response:
            # Should handle gracefully (400 or 404)
            if response.status_code in [400, 404]:
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task
    @tag("failure_scenario")
    def very_large_request(self):
        """Send very large request to test limits."""
        # Create a large message
        large_content = "A" * 10000  # 10KB of text
        payload = {
            "model": "gpt-4",
            "messages": [
                {"role": "user", "content": large_content}
            ],
            "max_tokens": 100,
        }
        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            catch_response=True,
            name="very_large_request",
        ) as response:
            # May succeed or fail depending on limits
            if response.status_code in [200, 400, 413]:
                response.success()
            else:
                response.failure(f"Unexpected status: {response.status_code}")


class ConcurrentKeySwitchingUser(HttpUser):
    """Concurrent key switching scenario.

    Tests system behavior when requests switch between different keys rapidly.
    """

    tasks = [ChatCompletionsTasks]
    wait_time = between(0.2, 1)
    weight = 1

    @task
    @tag("concurrent_key_switching")
    def rapid_key_switching(self):
        """Rapid requests that should trigger key switching."""
        # Vary model/provider to encourage key switching
        models = ["gpt-4", "gpt-3.5-turbo"]
        payload = {
            "model": random.choice(models),
            "messages": [
                {"role": "user", "content": f"Request {random.randint(1, 1000)}"}
            ],
            "temperature": random.uniform(0.1, 1.0),
            "max_tokens": random.randint(50, 200),
        }
        with self.client.post(
            "/v1/chat/completions",
            json=payload,
            catch_response=True,
            name="rapid_key_switching",
        ) as response:
            if response.status_code == 200:
                # Verify key switching by checking response headers
                key_used = response.headers.get("X-Key-Used")
                if key_used:
                    response.success()
                else:
                    response.failure("Missing X-Key-Used header")
            else:
                response.failure(f"Status: {response.status_code}")


# Custom event handlers for monitoring
def on_request_success(request_type, name, response_time, response_length):
    """Called when a request succeeds."""
    # Can be used for custom logging or metrics
    pass


def on_request_failure(request_type, name, response_time, exception):
    """Called when a request fails."""
    # Can be used for custom logging or metrics
    pass

