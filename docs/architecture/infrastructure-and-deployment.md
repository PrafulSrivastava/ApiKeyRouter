# Infrastructure and Deployment

The system is designed for **stateless deployment** by default, with optional persistence for production. This enables deployment to modern platforms (Railway, Render, Vercel) without file system dependencies.

## Infrastructure as Code

**Tool:** Not required for MVP (manual deployment), Terraform/CloudFormation for future production deployments

**Location:** `infrastructure/` (future)

**Approach:** 
- **MVP:** Environment variable configuration, manual deployment
- **Production:** Infrastructure as Code for cloud resources (MongoDB, Redis, monitoring)

**Rationale:** MVP focuses on library + stateless proxy. Infrastructure automation added when production requirements emerge.

## Deployment Strategy

**Strategy:** Stateless container deployment with environment-based configuration

**CI/CD Platform:** GitHub Actions (recommended)

**Pipeline Configuration:** `.github/workflows/`

**Deployment Targets:**
- **Library:** PyPI package (pip install)
- **Proxy:** Container image (Docker) or direct deployment to platforms

**Deployment Flow:**
1. **Development:** Local development with Poetry
2. **CI:** Automated testing and benchmarking on pull requests
3. **Staging:** Deploy proxy to staging environment (Railway/Render)
4. **Production:** Deploy proxy to production (Railway/Render/Vercel)

## Environments

**Development:**
- **Purpose:** Local development and testing
- **Configuration:** `.env` file, in-memory state store
- **Database:** Optional (MongoDB local or Docker)
- **Access:** Localhost only

**Staging:**
- **Purpose:** Pre-production testing and validation
- **Configuration:** Environment variables, optional MongoDB
- **Database:** MongoDB (optional, for testing persistence)
- **Access:** Internal/staging URL
- **Deployment:** Automatic on merge to `develop` branch

**Production:**
- **Purpose:** Live service
- **Configuration:** Environment variables (secrets from platform)
- **Database:** MongoDB (required for audit logs and metrics)
- **Access:** Public production URL
- **Deployment:** Manual approval or automatic on release tags

## Environment Promotion Flow

```
Development (Local)
    ↓ (git push)
CI/CD Pipeline (GitHub Actions)
    ↓ (tests pass)
Staging (Railway/Render)
    ↓ (validation)
Production (Railway/Render/Vercel)
```

**Promotion Criteria:**
- All tests pass (unit, integration, benchmarks)
- No performance regressions
- Manual approval for production (optional)

## Deployment Platforms

**Railway:**
- **Pros:** Simple deployment, automatic HTTPS, environment variables
- **Cons:** Limited free tier
- **Use Case:** Staging and small production deployments

**Render:**
- **Pros:** Free tier, easy setup, automatic deployments
- **Cons:** Cold starts on free tier
- **Use Case:** Staging and development deployments

**Vercel:**
- **Pros:** Excellent for serverless, fast deployments
- **Cons:** Serverless model may not fit long-running proxy
- **Use Case:** Alternative deployment option

**Self-Hosted:**
- **Pros:** Full control, no vendor lock-in
- **Cons:** Requires infrastructure management
- **Use Case:** Enterprise deployments, on-premises

## Configuration Management

**Environment Variables (Required):**
```bash
# Provider API Keys (registered via API, not env vars)
# Keys are managed through library API, not environment

# MongoDB (Optional - for persistence)
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=apikeyrouter
MONGODB_ENABLED=true

# Redis (Optional - for distributed state)
REDIS_URL=redis://localhost:6379
REDIS_ENABLED=false

# Proxy Configuration
PROXY_HOST=0.0.0.0
PROXY_PORT=8000
PROXY_RELOAD=false  # Set to true for development

# Management API
MANAGEMENT_API_KEY=your-management-key-here
MANAGEMENT_API_ENABLED=true

# Observability
LOG_LEVEL=INFO
METRICS_ENABLED=true
```

**Configuration Priority:**
1. Environment variables (highest priority)
2. `.env` file (development only)
3. Default values (safe defaults)

## Container Deployment (Docker)

**Dockerfile Structure:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install Poetry
RUN pip install poetry

# Copy dependency files
COPY pyproject.toml poetry.lock ./
COPY packages/proxy/pyproject.toml ./packages/proxy/

# Install dependencies
RUN poetry install --no-dev

# Copy application code
COPY packages/proxy/apikeyrouter_proxy ./packages/proxy/apikeyrouter_proxy/
COPY packages/core/apikeyrouter ./packages/core/apikeyrouter/

# Expose port
EXPOSE 8000

# Run application
CMD ["poetry", "run", "uvicorn", "apikeyrouter_proxy.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Docker Compose (Development):**
```yaml
version: '3.8'

services:
  proxy:
    build: .
    ports:
      - "8000:8000"
    environment:
      - MONGODB_URL=mongodb://mongo:27017
      - MONGODB_ENABLED=true
    depends_on:
      - mongo

  mongo:
    image: mongo:7.0
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db

volumes:
  mongo_data:
```

## Rollback Strategy

**Primary Method:** Platform-native rollback (Railway/Render support instant rollbacks)

**Trigger Conditions:**
- Health check failures
- Error rate threshold exceeded
- Performance degradation detected
- Manual rollback request

**Recovery Time Objective (RTO):** < 5 minutes

**Rollback Process:**
1. Detect issue (health checks, metrics, alerts)
2. Trigger rollback (automatic or manual)
3. Revert to previous deployment
4. Verify system health
5. Investigate root cause

**Data Safety:**
- MongoDB data persists across deployments (no data loss)
- State store (Redis/MongoDB) maintains state during rollback
- In-memory state lost on rollback (acceptable for stateless design)

## Monitoring and Health Checks

**Health Check Endpoint:** `GET /health`

**Health Check Criteria:**
- Application is running
- Can connect to optional dependencies (MongoDB, Redis)
- No critical errors in recent requests

**Monitoring:**
- **Application Metrics:** Prometheus metrics endpoint (`/metrics`)
- **Logs:** Structured JSON logs (stdout/stderr)
- **Alerts:** Platform-native alerting (Railway/Render) or external (PagerDuty, etc.)

**Key Metrics:**
- Request rate (requests/second)
- Error rate (4xx, 5xx responses)
- Response time (p50, p95, p99)
- Key usage distribution
- Quota exhaustion events
- Cost per request

## Scaling Strategy

**Library Mode:**
- Scales with application (embedded in each process)
- No separate scaling needed
- State is per-process (in-memory) or shared (Redis/MongoDB)

**Proxy Mode:**
- **Horizontal Scaling:** Deploy multiple proxy instances
- **State Sharing:** Use Redis or MongoDB for shared state
- **Load Balancing:** Platform load balancer (Railway/Render) or external (nginx, etc.)
- **Stateless Design:** Enables easy horizontal scaling

**Scaling Triggers:**
- CPU usage > 70%
- Memory usage > 80%
- Request queue length > threshold
- Response time degradation

## Security Considerations

**Secrets Management:**
- **Development:** `.env` file (git-ignored)
- **Staging/Production:** Platform secrets management (Railway/Render secrets)
- **Future:** Integration with Vault, AWS Secrets Manager

**Network Security:**
- HTTPS enforced (platform handles TLS termination)
- Internal services (MongoDB, Redis) not exposed publicly
- Management API requires authentication

**Access Control:**
- Management API protected by API key
- Provider API keys encrypted at rest
- No secrets in logs or error messages

---

**Select 1-9 or just type your question/feedback:**

1. Proceed to next section (Error Handling Strategy)
2. Challenge assumptions
3. Explore alternatives
4. Deep dive analysis
5. Risk assessment
6. Stakeholder perspective
7. Scenario planning
8. Constraint analysis
9. Expert consultation

Or type your feedback/questions about the Infrastructure and Deployment section.
