"""
Proxy Service Setup Example

This example demonstrates how to set up and use the ApiKeyRouter proxy service:
- Starting the proxy service
- Configuring environment variables
- Using OpenAI-compatible endpoints
- Managing keys via API

Prerequisites:
    Install dependencies:
    pip install apikeyrouter-proxy

    Or from source:
    cd packages/proxy
    poetry install

Run the proxy with: python proxy-setup.py
Or use uvicorn directly: uvicorn apikeyrouter_proxy.main:app --reload
"""

import os
import sys
import subprocess
from pathlib import Path

# This script demonstrates proxy setup
# The actual proxy runs via uvicorn

def print_setup_instructions():
    """Print setup instructions for the proxy service."""
    
    print("=" * 80)
    print("ApiKeyRouter Proxy Service Setup")
    print("=" * 80)
    print()
    
    # ============================================================================
    # Step 1: Environment Variables
    # ============================================================================
    
    print("Step 1: Configure Environment Variables")
    print("-" * 80)
    print()
    print("Create a .env file or set environment variables:")
    print()
    print("# Encryption key (required for production)")
    print("APIKEYROUTER_ENCRYPTION_KEY=your-32-byte-base64-encoded-key")
    print()
    print("# Proxy settings")
    print("PROXY_HOST=0.0.0.0")
    print("PROXY_PORT=8000")
    print("PROXY_RELOAD=false  # Set to 'true' for development")
    print()
    print("# Management API")
    print("MANAGEMENT_API_KEY=your-secret-management-key")
    print("MANAGEMENT_API_ENABLED=true")
    print()
    print("# State store (optional - uses in-memory by default)")
    print("# MONGODB_URL=mongodb://localhost:27017")
    print("# MONGODB_DATABASE=apikeyrouter")
    print("# REDIS_URL=redis://localhost:6379")
    print()
    print("# Observability")
    print("LOG_LEVEL=INFO")
    print("METRICS_ENABLED=true")
    print()
    
    # ============================================================================
    # Step 2: Starting the Proxy
    # ============================================================================
    
    print("Step 2: Starting the Proxy Service")
    print("-" * 80)
    print()
    print("Option 1: Using uvicorn directly")
    print("  cd packages/proxy")
    print("  poetry run uvicorn apikeyrouter_proxy.main:app --reload")
    print()
    print("Option 2: Using this script")
    print("  python proxy-setup.py")
    print()
    print("Option 3: Using Docker (if docker-compose.yml exists)")
    print("  docker-compose up")
    print()
    print("The proxy will be available at: http://localhost:8000")
    print("API documentation: http://localhost:8000/docs")
    print()
    
    # ============================================================================
    # Step 3: Register Keys via Management API
    # ============================================================================
    
    print("Step 3: Register Keys via Management API")
    print("-" * 80)
    print()
    print("Once the proxy is running, register keys via the management API:")
    print()
    print("```bash")
    print("curl -X POST http://localhost:8000/api/v1/keys \\")
    print("  -H 'X-API-Key: your-management-key' \\")
    print("  -H 'Content-Type: application/json' \\")
    print("  -d '{")
    print('    "key_material": "sk-your-openai-key",')
    print('    "provider_id": "openai",')
    print('    "metadata": {"tier": "premium"}')
    print("  }'")
    print("```")
    print()
    print("Or using Python:")
    print()
    print("```python")
    print("import httpx")
    print()
    print("response = httpx.post(")
    print("    'http://localhost:8000/api/v1/keys',")
    print("    headers={")
    print("        'X-API-Key': 'your-management-key',")
    print("        'Content-Type': 'application/json'")
    print("    },")
    print("    json={")
    print("        'key_material': 'sk-your-openai-key',")
    print("        'provider_id': 'openai',")
    print("        'metadata': {'tier': 'premium'}")
    print("    }")
    print(")")
    print("print(response.json())")
    print("```")
    print()
    
    # ============================================================================
    # Step 4: Using OpenAI-Compatible Endpoints
    # ============================================================================
    
    print("Step 4: Using OpenAI-Compatible Endpoints")
    print("-" * 80)
    print()
    print("The proxy provides OpenAI-compatible endpoints:")
    print()
    print("```python")
    print("import httpx")
    print()
    print("# Chat completions")
    print("response = httpx.post(")
    print("    'http://localhost:8000/v1/chat/completions',")
    print("    json={")
    print("        'model': 'gpt-4',")
    print("        'messages': [")
    print("            {'role': 'user', 'content': 'Hello!'}")
    print("        ]")
    print("    }")
    print(")")
    print("print(response.json())")
    print("```")
    print()
    print("Or using the OpenAI Python SDK:")
    print()
    print("```python")
    print("from openai import OpenAI")
    print()
    print("client = OpenAI(")
    print("    api_key='dummy-key',  # Not used, proxy handles routing")
    print("    base_url='http://localhost:8000/v1'")
    print(")")
    print()
    print("response = client.chat.completions.create(")
    print("    model='gpt-4',")
    print("    messages=[{'role': 'user', 'content': 'Hello!'}]")
    print(")")
    print("print(response.choices[0].message.content)")
    print("```")
    print()
    
    # ============================================================================
    # Step 5: Docker Setup (Optional)
    # ============================================================================
    
    print("Step 5: Docker Setup (Optional)")
    print("-" * 80)
    print()
    print("Create a Dockerfile for the proxy:")
    print()
    print("```dockerfile")
    print("FROM python:3.11-slim")
    print()
    print("WORKDIR /app")
    print()
    print("# Install Poetry")
    print("RUN pip install poetry")
    print()
    print("# Copy project files")
    print("COPY pyproject.toml poetry.lock .")
    print("COPY packages/proxy ./packages/proxy")
    print()
    print("# Install dependencies")
    print("RUN poetry config virtualenvs.create false \\")
    print("    && poetry install --no-dev")
    print()
    print("# Expose port")
    print("EXPOSE 8000")
    print()
    print("# Run proxy")
    print("CMD [\"uvicorn\", \"apikeyrouter_proxy.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]")
    print("```")
    print()
    print("Build and run:")
    print("  docker build -t apikeyrouter-proxy .")
    print("  docker run -p 8000:8000 -e APIKEYROUTER_ENCRYPTION_KEY=your-key apikeyrouter-proxy")
    print()
    
    # ============================================================================
    # Step 6: Health Checks
    # ============================================================================
    
    print("Step 6: Health Checks")
    print("-" * 80)
    print()
    print("Check proxy health:")
    print()
    print("```bash")
    print("curl http://localhost:8000/health")
    print("```")
    print()
    print("Response:")
    print("```json")
    print("{")
    print('  "status": "healthy",')
    print('  "version": "0.1.0",')
    print('  "keys_registered": 5,')
    print('  "providers_registered": 2')
    print("}")
    print("```")
    print()
    
    print("=" * 80)
    print("Setup complete!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("  1. Start the proxy: cd packages/proxy && poetry run uvicorn apikeyrouter_proxy.main:app --reload")
    print("  2. Register keys via management API")
    print("  3. Use OpenAI-compatible endpoints")
    print("  4. Read the User Guide: docs/guides/user-guide.md")
    print()


def start_proxy():
    """Start the proxy service (if running as main script)."""
    proxy_dir = Path(__file__).parent.parent.parent / "packages" / "proxy"
    
    if not proxy_dir.exists():
        print("Error: Proxy package not found. Please run from project root.")
        sys.exit(1)
    
    print("Starting ApiKeyRouter proxy service...")
    print(f"Working directory: {proxy_dir}")
    print()
    
    # Change to proxy directory and run uvicorn
    os.chdir(proxy_dir)
    
    try:
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "apikeyrouter_proxy.main:app",
            "--reload",
            "--host", "0.0.0.0",
            "--port", "8000"
        ])
    except KeyboardInterrupt:
        print("\nProxy stopped.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "start":
        start_proxy()
    else:
        print_setup_instructions()

