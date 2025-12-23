"""Tests for OpenAIAdapter health checks."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from apikeyrouter.domain.models.health_state import HealthState, HealthStatus
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter


class TestOpenAIAdapterHealth:
    """Tests for get_health method."""

    @pytest.mark.asyncio
    async def test_get_health_returns_healthy_for_200(self) -> None:
        """Test that get_health returns Healthy for 200 response."""
        adapter = OpenAIAdapter(base_url="https://api.openai.com/v1")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            health = await adapter.get_health()

            assert isinstance(health, HealthState)
            assert health.status == HealthStatus.Healthy
            assert health.latency_ms is not None
            assert health.latency_ms >= 0
            assert health.details["status_code"] == 200
            assert health.details["endpoint"] == "/models"

    @pytest.mark.asyncio
    async def test_get_health_returns_degraded_for_429(self) -> None:
        """Test that get_health returns Degraded for 429 response."""
        adapter = OpenAIAdapter(base_url="https://api.openai.com/v1")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            health = await adapter.get_health()

            assert health.status == HealthStatus.Degraded
            assert health.details["status_code"] == 429

    @pytest.mark.asyncio
    async def test_get_health_returns_down_for_500(self) -> None:
        """Test that get_health returns Down for 500+ response."""
        adapter = OpenAIAdapter(base_url="https://api.openai.com/v1")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            health = await adapter.get_health()

            assert health.status == HealthStatus.Down
            assert health.details["status_code"] == 500

    @pytest.mark.asyncio
    async def test_get_health_returns_down_for_timeout(self) -> None:
        """Test that get_health returns Down for timeout."""
        adapter = OpenAIAdapter(base_url="https://api.openai.com/v1")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            health = await adapter.get_health()

            assert health.status == HealthStatus.Down
            assert health.latency_ms is None
            assert "timeout" in health.details["error"].lower()

    @pytest.mark.asyncio
    async def test_get_health_returns_down_for_network_error(self) -> None:
        """Test that get_health returns Down for network error."""
        adapter = OpenAIAdapter(base_url="https://api.openai.com/v1")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.NetworkError("Network error"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            health = await adapter.get_health()

            assert health.status == HealthStatus.Down
            assert health.latency_ms is None
            assert "network" in health.details["error"].lower()

    @pytest.mark.asyncio
    async def test_get_health_caches_result(self) -> None:
        """Test that health status is cached."""
        adapter = OpenAIAdapter(base_url="https://api.openai.com/v1", health_check_ttl=60.0)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            # First call - should make request
            health1 = await adapter.get_health()
            assert mock_client.get.call_count == 1

            # Second call - should use cache
            health2 = await adapter.get_health()
            assert mock_client.get.call_count == 1  # Still 1, not 2

            # Health states should be the same
            assert health1.status == health2.status
            assert health1.latency_ms == health2.latency_ms

    @pytest.mark.asyncio
    async def test_get_health_cache_expires(self) -> None:
        """Test that health status cache expires after TTL."""
        adapter = OpenAIAdapter(
            base_url="https://api.openai.com/v1", health_check_ttl=0.1
        )  # Very short TTL

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            # First call - should make request
            await adapter.get_health()
            assert mock_client.get.call_count == 1

            # Wait for cache to expire
            time.sleep(0.15)

            # Second call - should make new request
            await adapter.get_health()
            assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_get_health_returns_degraded_for_4xx(self) -> None:
        """Test that get_health returns Degraded for other 4xx errors."""
        adapter = OpenAIAdapter(base_url="https://api.openai.com/v1")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            health = await adapter.get_health()

            assert health.status == HealthStatus.Degraded
            assert health.details["status_code"] == 400

    @pytest.mark.asyncio
    async def test_get_health_handles_unexpected_error(self) -> None:
        """Test that get_health handles unexpected errors gracefully."""
        adapter = OpenAIAdapter(base_url="https://api.openai.com/v1")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=ValueError("Unexpected error"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            health = await adapter.get_health()

            assert health.status == HealthStatus.Down
            assert "error" in health.details

    @pytest.mark.asyncio
    async def test_get_health_includes_latency(self) -> None:
        """Test that get_health includes latency measurement."""
        adapter = OpenAIAdapter(base_url="https://api.openai.com/v1")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200

            async def slow_get(*args, **kwargs):
                await asyncio.sleep(0.01)  # Simulate some latency
                return mock_response

            import asyncio

            mock_client.get = AsyncMock(side_effect=slow_get)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            health = await adapter.get_health()

            assert health.latency_ms is not None
            assert health.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_get_health_last_check_timestamp(self) -> None:
        """Test that get_health includes last_check timestamp."""
        adapter = OpenAIAdapter(base_url="https://api.openai.com/v1")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            health = await adapter.get_health()

            assert health.last_check is not None
            from datetime import datetime

            assert isinstance(health.last_check, datetime)
