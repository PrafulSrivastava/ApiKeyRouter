# Testing Guide for Stories 3.7.1, 3.7.2, and 3.7.3

This guide provides instructions for testing the last three implemented stories.

## Story 3.7.1: Implement Redis State Store
**Location:** `packages/core/`

### Prerequisites
- Redis server running (or Docker)
- Redis URL configured (default: `redis://localhost:6379/0`)

### Option 1: Run Tests with Docker Redis

```bash
# Start Redis in Docker
docker run -d -p 6379:6379 --name redis-test redis:latest

# Run Redis state store tests
cd packages/core
poetry run pytest tests/integration/test_state_store_redis.py -v

# Cleanup
docker stop redis-test && docker rm redis-test
```

### Option 2: Run Tests with Local Redis

```bash
# Ensure Redis is running locally
redis-cli ping  # Should return PONG

# Set Redis URL if different from default
export REDIS_URL="redis://localhost:6379/0"

# Run tests
cd packages/core
poetry run pytest tests/integration/test_state_store_redis.py -v
```

### Option 3: Run All Core Tests (Including Redis)

```bash
cd packages/core
poetry run pytest tests/integration/ -v -k redis
```

### Manual Testing

```python
# Test Redis connection
import os
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

from apikeyrouter.infrastructure.state_store.redis_store import RedisStateStore
from apikeyrouter.domain.models.api_key import APIKey

# Create store
store = RedisStateStore()

# Test save and retrieve
key = APIKey(id="test-key", key_material="encrypted", provider_id="openai")
await store.save_key(key)
retrieved = await store.get_key("test-key")
assert retrieved.id == "test-key"

# Cleanup
await store.close()
```

---

## Story 3.7.2: Secure Management API with Authentication
**Location:** `packages/proxy/`

### Run Unit Tests

```bash
cd packages/proxy
poetry run pytest tests/test_api_security.py::TestAuthentication -v
```

### Run All Security Tests

```bash
cd packages/proxy
poetry run pytest tests/test_api_security.py -v
```

**Note:** The `PendingDeprecationWarning` from the `multipart` package is automatically filtered in `pyproject.toml`, so you don't need the `-W` flag.

### Manual Testing with Test Client

```bash
cd packages/proxy

# Start the server
poetry run uvicorn apikeyrouter_proxy.main:app --reload
```

In another terminal:

```bash
# Test 1: Public endpoint (should work without auth)
curl http://localhost:8000/health

# Test 2: Management endpoint without auth (should fail with 401)
curl http://localhost:8000/api/v1/keys

# Test 3: Management endpoint with invalid Bearer token (should fail with 401)
curl -H "Authorization: Bearer invalid-key" http://localhost:8000/api/v1/keys

# Test 4: Management endpoint with valid Bearer token (should succeed)
export MANAGEMENT_API_KEY="test-key-12345"
curl -H "Authorization: Bearer test-key-12345" http://localhost:8000/api/v1/keys

# Test 5: Rate limiting (make 6 failed attempts, 6th should return 429)
for i in {1..6}; do
  curl -H "Authorization: Bearer wrong-key" http://localhost:8000/api/v1/keys
done
```

### Test Rate Limiting

```bash
# Set management API key
export MANAGEMENT_API_KEY="test-key-12345"

# Start server
poetry run uvicorn apikeyrouter_proxy.main:app

# In another terminal, make multiple failed auth attempts
for i in {1..6}; do
  echo "Attempt $i:"
  curl -s -H "Authorization: Bearer wrong-key" http://localhost:8000/api/v1/keys | jq
  sleep 1
done
# 6th attempt should return 429 Too Many Requests
```

### Test Authentication Logging

Check server logs for structured logging:
- `authentication_success` events
- `authentication_failed` events with reasons
- `authentication_rate_limit_exceeded` events

---

## Story 3.7.3: Implement Graceful Shutdown
**Location:** `packages/proxy/`

### Run Unit Tests

```bash
cd packages/proxy
poetry run pytest tests/test_graceful_shutdown.py -v
```

### Manual Testing - Basic Shutdown

```bash
cd packages/proxy

# Start server with the run script
poetry run python -m apikeyrouter_proxy.run

# In another terminal, send SIGTERM
# On Linux/Mac:
kill -TERM <pid>

# On Windows PowerShell:
# Find the process ID first
Get-Process python | Where-Object {$_.Path -like "*python*"}
# Then kill it (or use Ctrl+C in the terminal)
```

### Manual Testing - Shutdown with Active Requests

```bash
# Terminal 1: Start server
cd packages/proxy
export SHUTDOWN_TIMEOUT_SECONDS=10
poetry run python -m apikeyrouter_proxy.run

# Terminal 2: Make a long-running request
curl http://localhost:8000/health &
sleep 2

# Terminal 3: Send shutdown signal
kill -TERM <pid>

# Observe:
# 1. Server stops accepting new connections
# 2. Waits for active requests to complete
# 3. Logs shutdown events
# 4. Closes connections gracefully
```

### Test Shutdown Timeout

```bash
# Start server with short timeout
export SHUTDOWN_TIMEOUT_SECONDS=2
poetry run python -m apikeyrouter_proxy.run

# Make a request that takes longer than timeout
# Send SIGTERM
# Should see timeout warning in logs and force cleanup
```

### Test Shutdown Logging

Watch for these log events during shutdown:
- `application_startup` - On startup
- `shutdown_timeout_configured` - Shows configured timeout
- `shutdown_signal_received` - When SIGTERM received
- `shutdown_started` - Beginning cleanup
- `shutdown_resource_closed` - Each resource closed
- `shutdown_completed` - Successful completion
- `shutdown_timeout_exceeded` - If timeout exceeded

### Test with Different Timeouts

```bash
# Test with 10 second timeout
export SHUTDOWN_TIMEOUT_SECONDS=10
poetry run python -m apikeyrouter_proxy.run

# Test with 60 second timeout
export SHUTDOWN_TIMEOUT_SECONDS=60
poetry run python -m apikeyrouter_proxy.run

# Test with default (30 seconds)
unset SHUTDOWN_TIMEOUT_SECONDS
poetry run python -m apikeyrouter_proxy.run
```

---

## Running All Tests Together

### Run All Proxy Tests

```bash
cd packages/proxy
poetry run pytest tests/ -v
```

### Run All Core Tests (Including Redis)

```bash
cd packages/core
poetry run pytest tests/integration/ -v
```

### Run Tests with Coverage

```bash
# Proxy tests
cd packages/proxy
poetry run pytest tests/ --cov=apikeyrouter_proxy --cov-report=html

# Core tests
cd packages/core
poetry run pytest tests/integration/test_state_store_redis.py --cov=apikeyrouter.infrastructure.state_store.redis_store --cov-report=html
```

---

## Integration Testing

### Test Complete Flow: Authentication + Shutdown

```bash
# Terminal 1: Start server
cd packages/proxy
export MANAGEMENT_API_KEY="test-key-12345"
export SHUTDOWN_TIMEOUT_SECONDS=30
poetry run python -m apikeyrouter_proxy.run

# Terminal 2: Make authenticated requests
for i in {1..5}; do
  curl -H "Authorization: Bearer test-key-12345" http://localhost:8000/api/v1/keys
  sleep 1
done

# Terminal 3: Send shutdown signal
kill -TERM <pid>

# Verify:
# - Requests complete successfully
# - Shutdown logs appear
# - Server exits cleanly
```

---

## Troubleshooting

### Redis Tests Failing
- Ensure Redis is running: `redis-cli ping`
- Check REDIS_URL environment variable
- Verify Redis is accessible: `redis-cli -u $REDIS_URL ping`

### Authentication Tests Failing
- Ensure MANAGEMENT_API_KEY is set for manual testing
- Check that Bearer token format is correct: `Authorization: Bearer <key>`
- Verify middleware is applied to `/api/v1/*` routes

### Shutdown Tests Failing
- Check that SIGTERM signal is being sent correctly
- Verify SHUTDOWN_TIMEOUT_SECONDS is set
- Check logs for shutdown events
- Ensure no blocking operations prevent shutdown

---

## Expected Test Results

### Story 3.7.1 (Redis State Store)
- All integration tests should pass
- Redis connection should be established
- Fallback to in-memory store if Redis unavailable

### Story 3.7.2 (Authentication)
- 12 authentication tests should pass
- Public endpoints accessible without auth
- Management endpoints require Bearer token
- Rate limiting works (5 attempts per minute)

### Story 3.7.3 (Graceful Shutdown)
- 14 shutdown tests should pass
- Server stops accepting new connections on SIGTERM
- Active requests complete before shutdown
- Resources closed gracefully
- Shutdown events logged

