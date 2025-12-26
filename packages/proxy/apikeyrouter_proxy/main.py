"""FastAPI application entry point for ApiKeyRouter Proxy."""

import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apikeyrouter_proxy.api import management, v1
from apikeyrouter_proxy.middleware.auth import AuthenticationMiddleware
from apikeyrouter_proxy.middleware.cors import CORSMiddleware
from apikeyrouter_proxy.middleware.rate_limit import RateLimitMiddleware
from apikeyrouter_proxy.middleware.security import SecurityHeadersMiddleware

app = FastAPI(
    title="ApiKeyRouter Proxy",
    version="0.1.0",
    description="FastAPI proxy service for intelligent API key routing",
)

# Add middleware in order (last added is first executed)
# Security headers should be added first (outermost)
app.add_middleware(
    SecurityHeadersMiddleware, enable_hsts=os.getenv("ENABLE_HSTS", "false").lower() == "true"
)

# CORS middleware
app.add_middleware(CORSMiddleware)

# Rate limiting middleware
app.add_middleware(RateLimitMiddleware)

# Authentication middleware (innermost, executes last)
app.add_middleware(AuthenticationMiddleware)

app.mount("/ui", StaticFiles(directory="tests/UI"), name="ui")

@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("tests/UI/index.html")

app.include_router(v1.router, prefix="/v1")
app.include_router(management.router, prefix="/api/v1")
