# Multi-stage build for ApiKeyRouter Proxy Service
# Stage 1: Builder stage - install dependencies
FROM python:3.11-slim AS builder

# Set working directory
WORKDIR /app

# Install system dependencies required for Poetry and building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.7.1 \
    POETRY_HOME=/opt/poetry \
    POETRY_VENV=/opt/poetry-venv \
    POETRY_CACHE_DIR=/opt/poetry-cache

RUN python3 -m venv $POETRY_VENV \
    && $POETRY_VENV/bin/pip install -U pip setuptools \
    && $POETRY_VENV/bin/pip install poetry==${POETRY_VERSION} \
    && ln -s ${POETRY_VENV}/bin/poetry /usr/local/bin/poetry \
    && chmod 755 /usr/local/bin/poetry

# Configure Poetry: Don't create virtual environment, install to system Python
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/opt/poetry-cache

# Copy dependency files and source code (needed for local path dependencies)
COPY pyproject.toml poetry.lock ./
COPY packages/core/pyproject.toml ./packages/core/
COPY packages/core/README.md ./packages/core/
COPY packages/core/apikeyrouter ./packages/core/apikeyrouter
COPY packages/proxy/pyproject.toml ./packages/proxy/
COPY packages/proxy/README.md ./packages/proxy/
COPY packages/proxy/apikeyrouter_proxy ./packages/proxy/apikeyrouter_proxy

# Install dependencies using pip directly (more reliable than Poetry install)
# First, install core package in editable mode
WORKDIR /app/packages/core
RUN pip install --no-cache-dir -e . && \
    echo "Core package installed"

# Then install proxy package in editable mode (this will install all its dependencies including uvicorn)
WORKDIR /app/packages/proxy
RUN pip install --no-cache-dir -e . && \
    echo "Proxy package installed"

# Verify installation and list what's actually installed
RUN echo "=== Verifying installation in BUILDER ===" && \
    python -c "import sys; print('Python executable:', sys.executable)" && \
    python -c "import site; print('Site packages:', site.getsitepackages())" && \
    echo "=== Package count in builder ===" && \
    ls -1 /usr/local/lib/python3.11/site-packages/ | wc -l && \
    echo "=== Checking for uvicorn in builder ===" && \
    (python -c "import uvicorn; print('✓ uvicorn found at:', uvicorn.__file__)" || echo "✗ uvicorn NOT found") && \
    echo "=== Sample packages in builder ===" && \
    ls -1 /usr/local/lib/python3.11/site-packages/ | grep -E "(uvicorn|fastapi|apikeyrouter)" | head -10 || echo "No matching packages found" && \
    echo "=== All packages in builder (first 30) ===" && \
    ls -1 /usr/local/lib/python3.11/site-packages/ | head -30

# Verify what's actually installed before cleaning
# Force this to run (add timestamp to avoid cache)
RUN echo "=== Final check in BUILDER $(date) ===" && \
    echo "Package count in site-packages:" && \
    ls -1 /usr/local/lib/python3.11/site-packages/ | wc -l && \
    echo "=== ALL packages in site-packages ===" && \
    ls -1 /usr/local/lib/python3.11/site-packages/ && \
    echo "=== Testing imports ===" && \
    (python -c "import uvicorn; print('✓ uvicorn found at:', uvicorn.__file__)" || echo "✗ uvicorn NOT found") && \
    (python -c "import fastapi; print('✓ fastapi found')" || echo "✗ fastapi NOT found") && \
    echo "=== Searching for uvicorn anywhere ===" && \
    find /usr/local -name "*uvicorn*" -type d 2>/dev/null | head -10

# Clean cache and return to root
WORKDIR /app
RUN rm -rf $POETRY_CACHE_DIR

# Stage 2: Runtime stage - minimal image with only runtime dependencies
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install only runtime system dependencies (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
# Remove the runtime's base site-packages first, then copy from builder
RUN rm -rf /usr/local/lib/python3.11/site-packages/* && \
    echo "=== Cleared runtime site-packages ==="

# Copy site-packages from builder (this should have all our packages)
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy scripts/binaries
COPY --from=builder /usr/local/bin /usr/local/bin

# Verify uvicorn is available after copy (run as root before switching user)
RUN echo "=== Verifying packages after copy in RUNTIME ===" && \
    python3 -c "import sys; print('Python paths:', sys.path)" && \
    echo "Site-packages count after copy:" && \
    ls -1 /usr/local/lib/python3.11/site-packages/ | wc -l && \
    echo "Looking for uvicorn:" && \
    (ls -la /usr/local/lib/python3.11/site-packages/ | grep -i uvicorn || echo "No uvicorn directory found") && \
    (python3 -c "import uvicorn; print('✓ uvicorn found at:', uvicorn.__file__)" || \
     (echo "✗ uvicorn NOT found! Debugging..." && \
      echo "First 50 packages:" && \
      ls -1 /usr/local/lib/python3.11/site-packages/ | head -50 && \
      echo "Searching for uvicorn files:" && \
      find /usr/local/lib/python3.11/site-packages -name "*uvicorn*" 2>/dev/null | head -10 && \
      exit 1))

# Ensure Python can find the installed packages
ENV PYTHONPATH=/usr/local/lib/python3.11/site-packages

# Copy application code
COPY packages/core/apikeyrouter ./packages/core/apikeyrouter
COPY packages/core/pyproject.toml ./packages/core/
COPY packages/core/README.md ./packages/core/
COPY packages/proxy/apikeyrouter_proxy ./packages/proxy/apikeyrouter_proxy
COPY packages/proxy/pyproject.toml ./packages/proxy/
COPY packages/proxy/README.md ./packages/proxy/

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Health check (uses FastAPI's default /docs endpoint)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

# Run the application (use python -m to ensure uvicorn is found)
CMD ["python", "-m", "uvicorn", "apikeyrouter_proxy.main:app", "--host", "0.0.0.0", "--port", "8000"]

