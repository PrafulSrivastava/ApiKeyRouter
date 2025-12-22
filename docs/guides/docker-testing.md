# Docker Testing Guide

This guide covers how to test the ApiKeyRouter Proxy service running in Docker containers.

## Quick Test

### 1. Check Container Status

```bash
docker-compose ps
```

All services should show as "Up" and "healthy".

### 2. Test API Documentation

Open in browser:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

Or test with curl:
```bash
# Test docs endpoint
curl http://localhost:8000/docs

# Test OpenAPI schema
curl http://localhost:8000/openapi.json
```

### 3. Test Health Check

```bash
# Test health endpoint (if available)
curl http://localhost:8000/health

# Or check container health status
docker inspect apikeyrouter-proxy --format='{{.State.Health.Status}}'
```

## Viewing Logs

### View All Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f proxy
docker-compose logs -f mongodb
```

### View Recent Logs

```bash
# Last 50 lines
docker-compose logs --tail 50 proxy

# Last 100 lines with timestamps
docker-compose logs --tail 100 -t proxy
```

### View Logs from Container

```bash
docker logs apikeyrouter-proxy
docker logs apikeyrouter-proxy --tail 20 -f
```

## Testing API Endpoints

### Test Root Endpoint

```bash
curl http://localhost:8000/
```

### Test API Endpoints (if implemented)

```bash
# Example: Test chat completions endpoint
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Container Management

### Restart Services

```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart proxy
```

### Stop Services

```bash
# Stop all services
docker-compose stop

# Stop specific service
docker-compose stop proxy
```

### Start Services

```bash
# Start all services
docker-compose start

# Start specific service
docker-compose start proxy
```

### Rebuild and Restart

```bash
# Rebuild and restart
docker-compose up -d --build

# Rebuild specific service
docker-compose up -d --build proxy
```

## Executing Commands in Containers

### Access Proxy Container Shell

```bash
# Interactive shell
docker-compose exec proxy /bin/bash

# Or using docker directly
docker exec -it apikeyrouter-proxy /bin/bash
```

### Run Python Commands

```bash
# Test Python imports
docker-compose exec proxy python -c "import uvicorn; print('uvicorn OK')"
docker-compose exec proxy python -c "import fastapi; print('fastapi OK')"
docker-compose exec proxy python -c "import apikeyrouter; print('apikeyrouter OK')"
```

### Check Installed Packages

```bash
# List installed packages
docker-compose exec proxy pip list

# Check specific package
docker-compose exec proxy pip show uvicorn
```

## Testing MongoDB Connection

### Access MongoDB Container

```bash
# MongoDB shell
docker-compose exec mongodb mongosh

# Or using docker directly
docker exec -it apikeyrouter-mongodb mongosh
```

### Test MongoDB from Proxy Container

```bash
# Test MongoDB connection from proxy
docker-compose exec proxy python -c "
import os
print('MONGODB_URL:', os.getenv('MONGODB_URL', 'Not set'))
"
```

## Network Testing

### Test Container Networking

```bash
# Test proxy can reach MongoDB
docker-compose exec proxy ping -c 3 mongodb

# Test from host to proxy
curl -v http://localhost:8000/docs
```

### Check Network Configuration

```bash
# List networks
docker network ls

# Inspect network
docker network inspect apikeyrouter_apikeyrouter-network
```

## Performance Testing

### Check Resource Usage

```bash
# Container stats
docker stats apikeyrouter-proxy

# All containers
docker stats
```

### Load Testing (if Locust is available)

```bash
# Run load tests
docker-compose exec proxy locust -f tests/load/locustfile.py --host=http://localhost:8000
```

## Troubleshooting

### Container Not Starting

```bash
# Check logs for errors
docker-compose logs proxy

# Check container status
docker-compose ps

# Inspect container
docker inspect apikeyrouter-proxy
```

### Service Not Responding

```bash
# Check if port is accessible
curl -v http://localhost:8000/docs

# Check container health
docker inspect apikeyrouter-proxy --format='{{json .State.Health}}' | python -m json.tool

# Check if service is listening
docker-compose exec proxy netstat -tlnp
```

### Environment Variables

```bash
# Check environment variables in container
docker-compose exec proxy env

# Check specific variable
docker-compose exec proxy printenv PORT
docker-compose exec proxy printenv MONGODB_URL
```

### File Permissions

```bash
# Check file ownership
docker-compose exec proxy ls -la /app

# Check if user can write
docker-compose exec proxy touch /tmp/test && echo "Write OK" || echo "Write failed"
```

## Integration Testing

### Test Full Stack

1. **Start services:**
   ```bash
   docker-compose up -d
   ```

2. **Wait for health checks:**
   ```bash
   docker-compose ps
   # Wait until all show "healthy"
   ```

3. **Test API:**
   ```bash
   curl http://localhost:8000/docs
   ```

4. **Check logs:**
   ```bash
   docker-compose logs proxy
   ```

## Browser Testing

1. Open browser: http://localhost:8000/docs
2. You should see the FastAPI Swagger UI
3. Test endpoints interactively through the UI

## Automated Testing Script

Create a test script:

```bash
#!/bin/bash
# test-docker.sh

echo "Testing Docker containers..."

# Check containers are running
if ! docker-compose ps | grep -q "Up.*healthy"; then
    echo "❌ Containers not healthy"
    exit 1
fi

# Test docs endpoint
if curl -f http://localhost:8000/docs > /dev/null 2>&1; then
    echo "✅ Docs endpoint working"
else
    echo "❌ Docs endpoint failed"
    exit 1
fi

# Test OpenAPI
if curl -f http://localhost:8000/openapi.json > /dev/null 2>&1; then
    echo "✅ OpenAPI endpoint working"
else
    echo "❌ OpenAPI endpoint failed"
    exit 1
fi

echo "✅ All tests passed!"
```

Run it:
```bash
chmod +x test-docker.sh
./test-docker.sh
```

## Next Steps

- Test API endpoints (when implemented)
- Configure environment variables in `.env`
- Test with actual API keys
- Monitor logs for errors
- Check performance metrics

