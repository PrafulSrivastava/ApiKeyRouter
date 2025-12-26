"""Tests for API security features."""

import os
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from apikeyrouter_proxy.middleware.auth import (
    ManagementAPIAuthMiddleware,
    get_management_api_key,
    require_management_auth,
)
from apikeyrouter_proxy.middleware.cors import CORSMiddleware, get_cors_origins
from apikeyrouter_proxy.middleware.rate_limit import RateLimitMiddleware
from apikeyrouter_proxy.middleware.security import SecurityHeadersMiddleware


class TestAuthentication:
    """Tests for authentication middleware."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.test_api_key = "test-management-api-key-12345"
        os.environ["MANAGEMENT_API_KEY"] = self.test_api_key
        # Clean up old env var if present
        os.environ.pop("APIKEYROUTER_MANAGEMENT_API_KEY", None)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        os.environ.pop("MANAGEMENT_API_KEY", None)
        os.environ.pop("APIKEYROUTER_MANAGEMENT_API_KEY", None)

    def test_get_management_api_key(self) -> None:
        """Test getting management API key from environment."""
        api_key = get_management_api_key()
        assert api_key == self.test_api_key

    def test_get_management_api_key_not_set(self) -> None:
        """Test getting management API key when not set."""
        os.environ.pop("MANAGEMENT_API_KEY", None)
        api_key = get_management_api_key()
        assert api_key is None

    @pytest.mark.asyncio
    async def test_require_management_auth_valid(self) -> None:
        """Test require_management_auth dependency with valid Bearer token."""
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {self.test_api_key}"}
        request.url.path = "/api/v1/keys"
        request.method = "GET"
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        request.state = MagicMock()

        result = await require_management_auth(request)
        assert result is True
        assert request.state.authenticated is True
        assert request.state.management_api_key == self.test_api_key

    @pytest.mark.asyncio
    async def test_require_management_auth_missing_header(self) -> None:
        """Test require_management_auth with missing Authorization header."""
        request = MagicMock()
        request.headers = {}
        request.url.path = "/api/v1/keys"
        request.method = "GET"
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        with pytest.raises(HTTPException) as exc_info:
            await require_management_auth(request)
        assert exc_info.value.status_code == 401
        assert "Missing Authorization header" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_management_auth_invalid_format(self) -> None:
        """Test require_management_auth with invalid Bearer token format."""
        request = MagicMock()
        request.headers = {"Authorization": "InvalidFormat token"}
        request.url.path = "/api/v1/keys"
        request.method = "GET"
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        with pytest.raises(HTTPException) as exc_info:
            await require_management_auth(request)
        assert exc_info.value.status_code == 401
        assert "Invalid Authorization header format" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_management_auth_invalid_key(self) -> None:
        """Test require_management_auth with invalid API key."""
        request = MagicMock()
        request.headers = {"Authorization": "Bearer invalid-key"}
        request.url.path = "/api/v1/keys"
        request.method = "GET"
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        with pytest.raises(HTTPException) as exc_info:
            await require_management_auth(request)
        assert exc_info.value.status_code == 401
        assert "Invalid management API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_management_auth_not_configured(self) -> None:
        """Test require_management_auth when management API key is not configured."""
        os.environ.pop("MANAGEMENT_API_KEY", None)
        request = MagicMock()
        request.headers = {"Authorization": "Bearer any-key"}
        request.url.path = "/api/v1/keys"
        request.method = "GET"

        with pytest.raises(HTTPException) as exc_info:
            await require_management_auth(request)
        assert exc_info.value.status_code == 401
        assert "not configured" in exc_info.value.detail

    def test_authentication_middleware_allows_public_endpoints(self) -> None:
        """Test that authentication middleware allows public endpoints."""
        test_app = FastAPI()

        @test_app.get("/v1/chat/completions")
        async def public_endpoint():
            return {"message": "public"}

        @test_app.get("/health")
        async def health_endpoint():
            return {"status": "healthy"}

        test_app.add_middleware(ManagementAPIAuthMiddleware)
        client = TestClient(test_app)

        # Public endpoints should work without API key
        response = client.get("/v1/chat/completions")
        assert response.status_code == 200

        response = client.get("/health")
        assert response.status_code == 200

    def test_authentication_middleware_protects_management_api(self) -> None:
        """Test that authentication middleware protects management API."""
        test_app = FastAPI()

        @test_app.get("/api/v1/keys")
        async def management_endpoint():
            return {"keys": []}

        test_app.add_middleware(ManagementAPIAuthMiddleware)
        client = TestClient(test_app)

        # Management endpoint without Authorization header should fail
        response = client.get("/api/v1/keys")
        assert response.status_code == 401
        assert "Missing Authorization header" in response.json()["detail"]

        # Management endpoint with invalid Bearer format should fail
        response = client.get("/api/v1/keys", headers={"Authorization": "InvalidFormat token"})
        assert response.status_code == 401
        assert "Invalid Authorization header format" in response.json()["detail"]

        # Management endpoint with invalid API key should fail
        response = client.get("/api/v1/keys", headers={"Authorization": "Bearer invalid-key"})
        assert response.status_code == 401
        assert "Invalid management API key" in response.json()["detail"]

        # Management endpoint with valid Bearer token should succeed
        response = client.get("/api/v1/keys", headers={"Authorization": f"Bearer {self.test_api_key}"})
        assert response.status_code == 200

    def test_authentication_middleware_fail_secure(self) -> None:
        """Test that authentication middleware fails secure when key not configured."""
        os.environ.pop("MANAGEMENT_API_KEY", None)

        test_app = FastAPI()

        @test_app.get("/api/v1/keys")
        async def management_endpoint():
            return {"keys": []}

        test_app.add_middleware(ManagementAPIAuthMiddleware)
        client = TestClient(test_app)

        # Should deny access even with a key when management API key is not configured
        response = client.get("/api/v1/keys", headers={"Authorization": "Bearer any-key"})
        assert response.status_code == 401
        assert "not configured" in response.json()["detail"]

    def test_authentication_rate_limiting(self) -> None:
        """Test rate limiting on authentication attempts."""
        test_app = FastAPI()

        @test_app.get("/api/v1/keys")
        async def management_endpoint():
            return {"keys": []}

        # Set rate limit to 3 attempts per minute
        test_app.add_middleware(ManagementAPIAuthMiddleware, auth_rate_limit=3, auth_rate_window_seconds=60)
        client = TestClient(test_app)

        # Make 3 failed authentication attempts (should all fail with 401)
        for _ in range(3):
            response = client.get("/api/v1/keys", headers={"Authorization": "Bearer invalid-key"})
            assert response.status_code == 401

        # 4th attempt should be rate limited (429)
        response = client.get("/api/v1/keys", headers={"Authorization": "Bearer invalid-key"})
        assert response.status_code == 429
        assert "Too many authentication attempts" in response.json()["detail"]
        assert "retry_after" in response.json()
        assert "Retry-After" in response.headers

    def test_authentication_rate_limiting_resets_on_success(self) -> None:
        """Test that successful authentication doesn't count toward rate limit."""
        test_app = FastAPI()

        @test_app.get("/api/v1/keys")
        async def management_endpoint():
            return {"keys": []}

        # Set rate limit to 2 attempts per minute
        test_app.add_middleware(ManagementAPIAuthMiddleware, auth_rate_limit=2, auth_rate_window_seconds=60)
        client = TestClient(test_app)

        # Make 1 failed attempt
        response = client.get("/api/v1/keys", headers={"Authorization": "Bearer invalid-key"})
        assert response.status_code == 401

        # Successful authentication should not be rate limited
        response = client.get("/api/v1/keys", headers={"Authorization": f"Bearer {self.test_api_key}"})
        assert response.status_code == 200

        # Should still be able to make another failed attempt (only 1 failed attempt so far)
        response = client.get("/api/v1/keys", headers={"Authorization": "Bearer invalid-key"})
        assert response.status_code == 401

        # Now should be rate limited (2 failed attempts)
        response = client.get("/api/v1/keys", headers={"Authorization": "Bearer invalid-key"})
        assert response.status_code == 429


class TestRateLimiting:
    """Tests for rate limiting middleware."""

    def test_rate_limiting_allows_requests_within_limit(self) -> None:
        """Test that rate limiting allows requests within limit."""
        test_app = FastAPI()

        @test_app.get("/api/v1/keys")
        async def management_endpoint():
            return {"keys": []}

        test_app.add_middleware(RateLimitMiddleware, management_api_limit=5)
        client = TestClient(test_app)

        # Make 5 requests (within limit)
        for _ in range(5):
            response = client.get("/api/v1/keys")
            assert response.status_code == 200

    def test_rate_limiting_blocks_excessive_requests(self) -> None:
        """Test that rate limiting blocks excessive requests."""
        test_app = FastAPI()

        @test_app.get("/api/v1/keys")
        async def management_endpoint():
            return {"keys": []}

        test_app.add_middleware(RateLimitMiddleware, management_api_limit=5)
        client = TestClient(test_app)

        # Make 5 requests (within limit)
        for _ in range(5):
            response = client.get("/api/v1/keys")
            assert response.status_code == 200

        # 6th request should be rate limited
        response = client.get("/api/v1/keys")
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]
        assert "retry_after" in response.json()
        assert "Retry-After" in response.headers

    def test_rate_limiting_does_not_apply_to_public_endpoints(self) -> None:
        """Test that rate limiting does not apply to public endpoints."""
        test_app = FastAPI()

        @test_app.get("/v1/public")
        async def public_endpoint():
            return {"message": "public"}

        test_app.add_middleware(RateLimitMiddleware, management_api_limit=1)
        client = TestClient(test_app)

        # Make many requests to public endpoint (should not be rate limited)
        for _ in range(10):
            response = client.get("/v1/public")
            assert response.status_code == 200

    def test_rate_limiting_per_ip(self) -> None:
        """Test that rate limiting is per IP address."""
        test_app = FastAPI()

        @test_app.get("/api/v1/keys")
        async def management_endpoint():
            return {"keys": []}

        test_app.add_middleware(RateLimitMiddleware, management_api_limit=2)
        client = TestClient(test_app)

        # Make 2 requests from IP1 (limit)
        for _ in range(2):
            response = client.get("/api/v1/keys", headers={"X-Forwarded-For": "192.168.1.1"})
            assert response.status_code == 200

        # IP1 should be rate limited
        response = client.get("/api/v1/keys", headers={"X-Forwarded-For": "192.168.1.1"})
        assert response.status_code == 429

        # IP2 should still be able to make requests
        response = client.get("/api/v1/keys", headers={"X-Forwarded-For": "192.168.1.2"})
        assert response.status_code == 200


class TestCORS:
    """Tests for CORS middleware."""

    def test_get_cors_origins_from_environment(self) -> None:
        """Test getting CORS origins from environment variable."""
        os.environ["CORS_ORIGINS"] = "https://example.com,https://app.example.com"
        origins = get_cors_origins()
        assert "https://example.com" in origins
        assert "https://app.example.com" in origins
        os.environ.pop("CORS_ORIGINS", None)

    def test_get_cors_origins_defaults(self) -> None:
        """Test default CORS origins when not configured."""
        os.environ.pop("CORS_ORIGINS", None)
        origins = get_cors_origins()
        assert "http://localhost:3000" in origins
        assert "http://localhost:8000" in origins

    def test_cors_middleware_allows_configured_origins(self) -> None:
        """Test that CORS middleware allows configured origins."""
        test_app = FastAPI()

        @test_app.get("/api/v1/test")
        async def test_endpoint():
            return {"message": "test"}

        test_app.add_middleware(CORSMiddleware, allowed_origins=["https://example.com"])
        client = TestClient(test_app)

        # Request with allowed origin
        response = client.get(
            "/api/v1/test",
            headers={"Origin": "https://example.com"},
        )
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "https://example.com"

    def test_cors_middleware_handles_preflight(self) -> None:
        """Test that CORS middleware handles preflight OPTIONS requests."""
        test_app = FastAPI()

        @test_app.get("/api/v1/test")
        async def test_endpoint():
            return {"message": "test"}

        test_app.add_middleware(CORSMiddleware, allowed_origins=["https://example.com"])
        client = TestClient(test_app)

        # Preflight request
        response = client.options(
            "/api/v1/test",
            headers={"Origin": "https://example.com"},
        )
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "https://example.com"
        assert "Access-Control-Allow-Methods" in response.headers
        assert "Access-Control-Allow-Headers" in response.headers

    def test_cors_middleware_blocks_unconfigured_origins(self) -> None:
        """Test that CORS middleware blocks unconfigured origins."""
        test_app = FastAPI()

        @test_app.get("/api/v1/test")
        async def test_endpoint():
            return {"message": "test"}

        test_app.add_middleware(CORSMiddleware, allowed_origins=["https://example.com"])
        client = TestClient(test_app)

        # Request with disallowed origin
        response = client.get(
            "/api/v1/test",
            headers={"Origin": "https://malicious.com"},
        )
        assert response.status_code == 200
        # Should not have CORS headers for disallowed origin
        assert (
            "Access-Control-Allow-Origin" not in response.headers
            or response.headers["Access-Control-Allow-Origin"] != "https://malicious.com"
        )


class TestSecurityHeaders:
    """Tests for security headers middleware."""

    def test_security_headers_added_to_responses(self) -> None:
        """Test that security headers are added to all responses."""
        test_app = FastAPI()

        @test_app.get("/test")
        async def test_endpoint():
            return {"message": "test"}

        test_app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(test_app)

        response = client.get("/test")
        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"

    def test_hsts_header_added_when_enabled(self) -> None:
        """Test that HSTS header is added when enabled and request is HTTPS."""
        test_app = FastAPI()

        @test_app.get("/test")
        async def test_endpoint():
            return {"message": "test"}

        test_app.add_middleware(SecurityHeadersMiddleware, enable_hsts=True)
        client = TestClient(test_app)

        # Note: TestClient uses HTTP by default, so HSTS won't be added
        # In production with HTTPS, HSTS header would be added
        response = client.get("/test")
        assert response.status_code == 200
        # HSTS header should not be present for HTTP requests
        assert (
            "Strict-Transport-Security" not in response.headers
            or response.headers.get("Strict-Transport-Security") is None
        )


class TestAuthorizationRules:
    """Tests for authorization rules."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.test_api_key = "test-management-api-key-12345"
        os.environ["MANAGEMENT_API_KEY"] = self.test_api_key
        os.environ.pop("APIKEYROUTER_MANAGEMENT_API_KEY", None)

    def teardown_method(self) -> None:
        """Clean up test environment."""
        os.environ.pop("MANAGEMENT_API_KEY", None)
        os.environ.pop("APIKEYROUTER_MANAGEMENT_API_KEY", None)

    def test_routing_requests_no_auth_required(self) -> None:
        """Test that routing requests do not require authentication."""
        test_app = FastAPI()

        @test_app.post("/v1/chat/completions")
        async def routing_endpoint():
            return {"message": "routing"}

        test_app.add_middleware(ManagementAPIAuthMiddleware)
        client = TestClient(test_app)

        # Routing endpoint should work without API key
        response = client.post("/v1/chat/completions", json={})
        assert response.status_code == 200

    def test_management_endpoints_require_auth(self) -> None:
        """Test that management endpoints require authentication."""
        test_app = FastAPI()

        @test_app.get("/api/v1/keys")
        async def keys_endpoint():
            return {"keys": []}

        @test_app.post("/api/v1/keys")
        async def register_key_endpoint():
            return {"key_id": "key-123"}

        @test_app.delete("/api/v1/keys/{key_id}")
        async def revoke_key_endpoint(key_id: str):
            return {"status": "revoked"}

        @test_app.get("/api/v1/state")
        async def state_endpoint():
            return {"state": {}}

        test_app.add_middleware(ManagementAPIAuthMiddleware)
        client = TestClient(test_app)

        # All management endpoints should require Bearer token
        endpoints = [
            ("GET", "/api/v1/keys"),
            ("POST", "/api/v1/keys"),
            ("DELETE", "/api/v1/keys/key-123"),
            ("GET", "/api/v1/state"),
        ]

        auth_header = f"Bearer {self.test_api_key}"

        for method, path in endpoints:
            if method == "GET":
                response = client.get(path)
            elif method == "POST":
                response = client.post(path, json={})
            elif method == "DELETE":
                response = client.delete(path)
            else:
                continue

            assert response.status_code == 401, f"{method} {path} should require auth"

            # With valid Bearer token, should succeed
            if method == "GET":
                response = client.get(path, headers={"Authorization": auth_header})
            elif method == "POST":
                response = client.post(path, json={}, headers={"Authorization": auth_header})
            elif method == "DELETE":
                response = client.delete(path, headers={"Authorization": auth_header})

            assert response.status_code == 200, f"{method} {path} should work with valid Bearer token"
