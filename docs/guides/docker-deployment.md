# Docker Deployment Guide

This guide covers building, running, and deploying the ApiKeyRouter Proxy service using Docker.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Building the Docker Image](#building-the-docker-image)
- [Running with Docker](#running-with-docker)
- [Docker Compose for Local Development](#docker-compose-for-local-development)
- [Environment Variables](#environment-variables)
- [Image Optimization](#image-optimization)
- [Production Deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)

## Prerequisites

- Docker Engine 20.10+ installed
- Docker Compose 2.0+ (for local development)
- Basic knowledge of Docker commands

## Building the Docker Image

### Basic Build

Build the Docker image from the project root:

```bash
docker build -t apikeyrouter-proxy:latest .
```

### Build with Specific Tag

```bash
docker build -t apikeyrouter-proxy:v0.1.0 .
```

### Build Arguments

The Dockerfile uses multi-stage builds for optimization. No build arguments are currently required, but you can customize the build if needed.

## Running with Docker

### Basic Run

Run the container with default settings:

```bash
docker run -d \
  --name apikeyrouter-proxy \
  -p 8000:8000 \
  apikeyrouter-proxy:latest
```

### Run with Environment Variables

```bash
docker run -d \
  --name apikeyrouter-proxy \
  -p 8000:8000 \
  -e PORT=8000 \
  -e API_KEY=your-api-key-here \
  -e MONGODB_URL=mongodb://host.docker.internal:27017/apikeyrouter \
  apikeyrouter-proxy:latest
```

### Run with Environment File

Create a `.env` file:

```env
PORT=8000
API_KEY=your-api-key-here
MONGODB_URL=mongodb://localhost:27017/apikeyrouter
REDIS_URL=redis://localhost:6379/0
ENABLE_HSTS=false
```

Run with the environment file:

```bash
docker run -d \
  --name apikeyrouter-proxy \
  -p 8000:8000 \
  --env-file .env \
  apikeyrouter-proxy:latest
```

### Run with Volume Mounts (Development)

For development with live code reloading:

```bash
docker run -d \
  --name apikeyrouter-proxy \
  -p 8000:8000 \
  -v $(pwd)/packages/proxy/apikeyrouter_proxy:/app/packages/proxy/apikeyrouter_proxy:ro \
  -v $(pwd)/packages/core/apikeyrouter:/app/packages/core/apikeyrouter:ro \
  apikeyrouter-proxy:latest
```

## Docker Compose for Local Development

The project includes a `docker-compose.yml` file for local development with all required services.

### Setup Environment Variables

**Important:** Docker Compose uses a `.env` file for all environment variables. This ensures you only need to manage environment variables in one place.

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and configure your values:
   ```bash
   # Required: Set your encryption key
   APIKEYROUTER_ENCRYPTION_KEY=your-encryption-key-here
   
   # Optional: Set management API key
   APIKEYROUTER_MANAGEMENT_API_KEY=your-management-key-here
   
   # Optional: Configure database connections
   MONGODB_URL=mongodb://mongodb:27017/apikeyrouter
   REDIS_URL=redis://redis:6379/0
   ```

3. All environment variables are automatically loaded from `.env` by Docker Compose.

### Start All Services

```bash
docker-compose up -d
```

This will start:
- **Proxy service** on port 8000 (configurable via `PORT` in `.env`)
- **MongoDB** on port 27017 (optional)
- **Redis** on port 6379 (optional, commented out by default)

All services automatically use environment variables from the `.env` file.

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f proxy
```

### Stop Services

```bash
docker-compose down
```

### Stop and Remove Volumes

```bash
docker-compose down -v
```

### Rebuild After Code Changes

```bash
docker-compose up -d --build
```

### Enable Redis in Docker Compose

1. Edit `docker-compose.yml` and uncomment the Redis service section
2. Update the proxy service dependencies to include Redis:
   ```yaml
   depends_on:
     mongodb:
       condition: service_healthy
     redis:
       condition: service_healthy
   ```
3. Ensure `REDIS_URL` is set in your `.env` file:
   ```env
   REDIS_URL=redis://redis:6379/0
   ```

## Environment Variables

### Using .env File (Recommended)

**All environment variables are managed through a `.env` file.** This is the recommended approach as it:
- Centralizes all configuration in one place
- Works seamlessly with Docker Compose
- Keeps sensitive values out of version control (`.env` is gitignored)
- Makes it easy to switch between environments

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your configuration values

3. Docker Compose automatically loads all variables from `.env`

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `APIKEYROUTER_ENCRYPTION_KEY` | Encryption key for API key material (required in production) | Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

### Optional Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `PORT` | Server port | `8000` | `8000` |
| `APIKEYROUTER_MANAGEMENT_API_KEY` | Management API key for authentication | None | `your-management-key-here` |
| `MONGODB_URL` | MongoDB connection string | None | `mongodb://mongodb:27017/apikeyrouter` |
| `REDIS_URL` | Redis connection string | None | `redis://redis:6379/0` |
| `ENABLE_HSTS` | Enable HTTP Strict Transport Security | `false` | `true` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `localhost` | `https://example.com,https://app.example.com` |
| `PYTHONUNBUFFERED` | Python output buffering | `1` | `1` |
| `PYTHONDONTWRITEBYTECODE` | Disable .pyc files | `1` | `1` |
| `APIKEYROUTER_MAX_DECISIONS` | Max routing decisions to store | `1000` | `2000` |
| `APIKEYROUTER_LOG_LEVEL` | Logging level | `INFO` | `DEBUG` |

See `.env.example` for a complete list of all available environment variables with descriptions.

### Setting Environment Variables

**In Docker Compose (Recommended):**

All variables are automatically loaded from `.env` file. Just edit `.env` and restart:

```bash
# Edit .env file
nano .env

# Restart services to pick up changes
docker-compose restart
```

**In Docker Run:**

```bash
# Using .env file
docker run --env-file .env apikeyrouter-proxy:latest

# Or inline
docker run -e APIKEYROUTER_ENCRYPTION_KEY=your-key apikeyrouter-proxy:latest
```

## Image Optimization

The Dockerfile uses multi-stage builds to optimize image size:

### Optimization Features

1. **Multi-stage build**: Separates build dependencies from runtime
2. **Python slim image**: Uses `python:3.11-slim` (smaller base image)
3. **No dev dependencies**: Only installs production dependencies
4. **Layer caching**: Optimized layer order for better caching
5. **Non-root user**: Runs as `appuser` for security

### Image Size

Expected image size: ~200-300 MB (depending on dependencies)

### Build Optimization Tips

1. **Use .dockerignore**: Excludes unnecessary files from build context
2. **Layer caching**: Copy dependency files before source code
3. **Multi-stage builds**: Removes build tools from final image
4. **Specific versions**: Use specific image tags, not `latest`

## Production Deployment

### Security Best Practices

1. **Use non-root user**: Already configured in Dockerfile
2. **Scan for vulnerabilities**: Regularly scan images
   ```bash
   docker scan apikeyrouter-proxy:latest
   ```
3. **Use secrets management**: Don't hardcode secrets in Dockerfile
4. **Limit resources**: Set memory and CPU limits
   ```bash
   docker run --memory="512m" --cpus="1.0" apikeyrouter-proxy:latest
   ```

### Health Checks

The container includes a health check that verifies the service is responding:

```bash
# Check health status
docker inspect --format='{{.State.Health.Status}}' apikeyrouter-proxy
```

### Resource Limits

Set resource limits in Docker Compose:

```yaml
services:
  proxy:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
```

### Logging

Configure logging driver:

```bash
docker run --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  apikeyrouter-proxy:latest
```

## Troubleshooting

### Container Won't Start

1. **Check logs:**
   ```bash
   docker logs apikeyrouter-proxy
   ```

2. **Check port conflicts:**
   ```bash
   # Verify port 8000 is available
   netstat -an | grep 8000
   ```

3. **Verify environment variables:**
   ```bash
   docker exec apikeyrouter-proxy env
   ```

### Connection Issues

1. **MongoDB connection:**
   - Verify MongoDB is running and accessible
   - Check connection string format
   - Ensure network connectivity in Docker Compose

2. **Redis connection:**
   - Verify Redis is running
   - Check connection string format
   - Ensure network connectivity

### Build Issues

1. **Poetry installation fails:**
   - Check internet connectivity
   - Verify Poetry version compatibility

2. **Dependencies not found:**
   - Ensure `poetry.lock` is up to date
   - Run `poetry lock` before building

### Performance Issues

1. **Slow startup:**
   - Check health check intervals
   - Verify resource limits

2. **High memory usage:**
   - Review dependency sizes
   - Consider using Alpine-based images (if compatible)

## Docker Hub Publishing

The project includes automated Docker image building and publishing via GitHub Actions.

### Automated Publishing

Images are automatically built and published to Docker Hub when:
- Code is pushed to `main` or `develop` branches
- Version tags are created (e.g., `v0.1.0`)
- Workflow is manually triggered

### Image Tags

Images are tagged with:
- `latest` - Latest build from main branch
- `develop` - Latest build from develop branch
- `v0.1.0` - Specific version tag
- `0.1` - Major.minor version
- `0` - Major version only
- `main-<sha>` - Branch name with commit SHA

### Setting Up Docker Hub Credentials

To enable automated publishing, configure GitHub secrets:

1. **Create Docker Hub Access Token:**
   - Log in to [Docker Hub](https://hub.docker.com/)
   - Go to Account Settings → Security → New Access Token
   - Create a token with read/write permissions

2. **Configure GitHub Secrets:**
   - Go to repository Settings → Secrets and variables → Actions
   - Add the following secrets:
     - `DOCKER_HUB_USERNAME`: Your Docker Hub username
     - `DOCKER_HUB_TOKEN`: Your Docker Hub access token

### Manual Publishing

To manually trigger a build and publish:

1. Go to the Actions tab in GitHub
2. Select "Docker Build and Publish" workflow
3. Click "Run workflow"
4. Select branch and click "Run workflow"

### Pulling Published Images

Once published, pull the image:

```bash
# Latest version
docker pull <username>/apikeyrouter-proxy:latest

# Specific version
docker pull <username>/apikeyrouter-proxy:v0.1.0

# Run the pulled image
docker run -d -p 8000:8000 <username>/apikeyrouter-proxy:latest
```

### Security Scanning

All published images are automatically scanned for vulnerabilities using Trivy. Results are available in the GitHub Security tab.

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [Project README](../README.md)

## Support

For issues or questions:
- Check the [Troubleshooting](#troubleshooting) section
- Review project documentation
- Open an issue on GitHub

