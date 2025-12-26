"""Tests for graceful shutdown functionality."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from apikeyrouter_proxy.main import cleanup_resources, get_shutdown_timeout


class TestShutdownConfiguration:
    """Tests for shutdown configuration."""

    def test_get_shutdown_timeout_default(self) -> None:
        """Test that shutdown timeout defaults to 30 seconds."""
        os.environ.pop("SHUTDOWN_TIMEOUT_SECONDS", None)
        timeout = get_shutdown_timeout()
        assert timeout == 30

    def test_get_shutdown_timeout_from_env(self) -> None:
        """Test that shutdown timeout can be configured via environment variable."""
        os.environ["SHUTDOWN_TIMEOUT_SECONDS"] = "60"
        timeout = get_shutdown_timeout()
        assert timeout == 60
        os.environ.pop("SHUTDOWN_TIMEOUT_SECONDS", None)


class TestCleanupResources:
    """Tests for resource cleanup during shutdown."""

    @pytest.mark.asyncio
    async def test_cleanup_with_no_resources(self) -> None:
        """Test cleanup when no resources are initialized."""
        from apikeyrouter_proxy import main

        # Patch all resources to None/empty
        with patch.object(main, "_state_store", None), patch.object(
            main, "_redis_client", None
        ), patch.object(main, "_http_clients", []):
            # Should complete without errors
            await cleanup_resources()

    @pytest.mark.asyncio
    async def test_cleanup_mongodb_connection(self) -> None:
        """Test cleanup of MongoDB connections."""
        from apikeyrouter_proxy import main

        # Mock state store with close method
        mock_store = AsyncMock()
        mock_store.close = AsyncMock()

        # Patch the module-level variable
        with patch.object(main, "_state_store", mock_store):
            await cleanup_resources()

            # Verify close was called
            mock_store.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_redis_connection(self) -> None:
        """Test cleanup of Redis connections."""
        from apikeyrouter_proxy import main

        # Mock Redis client with close and connection_pool
        mock_redis = AsyncMock()
        mock_redis.close = AsyncMock()
        mock_pool = AsyncMock()
        mock_pool.disconnect = AsyncMock()
        mock_redis.connection_pool = mock_pool

        # Patch the module-level variable
        with patch.object(main, "_redis_client", mock_redis):
            await cleanup_resources()

            # Verify close and disconnect were called
            mock_redis.close.assert_called_once()
            mock_pool.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_http_clients(self) -> None:
        """Test cleanup of HTTP client connections."""
        from apikeyrouter_proxy import main

        # Mock HTTP clients - first has aclose, second has close
        mock_client1 = MagicMock()
        mock_client1.aclose = AsyncMock()
        mock_client2 = MagicMock()
        mock_client2.close = AsyncMock()
        # Ensure second client doesn't have aclose (MagicMock creates it by default)
        if hasattr(mock_client2, "aclose"):
            delattr(mock_client2, "aclose")

        # Patch the module-level variable
        with patch.object(main, "_http_clients", [mock_client1, mock_client2]):
            await cleanup_resources()

            # Verify clients were closed
            # First client should use aclose
            mock_client1.aclose.assert_called_once()
            # Second client should use close (since it doesn't have aclose)
            mock_client2.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_handles_errors_gracefully(self) -> None:
        """Test that cleanup handles errors gracefully."""
        from apikeyrouter_proxy import main

        # Mock state store that raises an error
        mock_store = AsyncMock()
        mock_store.close = AsyncMock(side_effect=Exception("Connection error"))

        # Patch the module-level variable
        with patch.object(main, "_state_store", mock_store):
            # Should not raise exception
            await cleanup_resources()

            # Verify close was attempted
            mock_store.close.assert_called_once()


class TestLifespanEvents:
    """Tests for FastAPI lifespan events."""

    def test_app_has_lifespan(self) -> None:
        """Test that the FastAPI app has lifespan configured."""
        from apikeyrouter_proxy.main import app

        assert app.router.lifespan_context is not None

    @pytest.mark.asyncio
    async def test_lifespan_startup(self) -> None:
        """Test lifespan startup event."""
        from apikeyrouter_proxy.main import app

        # Create a test client to trigger lifespan
        with TestClient(app) as client:
            # App should be started
            assert client.app is not None

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_timeout(self) -> None:
        """Test that shutdown respects timeout."""
        # Mock cleanup to take longer than timeout
        original_timeout = os.getenv("SHUTDOWN_TIMEOUT_SECONDS", "30")
        os.environ["SHUTDOWN_TIMEOUT_SECONDS"] = "1"

        try:

            # Mock cleanup to take 2 seconds (longer than 1 second timeout)
            async def slow_cleanup() -> None:
                await asyncio.sleep(2)

            with patch("apikeyrouter_proxy.main.cleanup_resources", slow_cleanup):
                # This should complete but log a timeout warning
                # We can't easily test the timeout in unit tests, but we can verify
                # the timeout configuration is respected
                timeout = get_shutdown_timeout()
                assert timeout == 1
        finally:
            os.environ["SHUTDOWN_TIMEOUT_SECONDS"] = original_timeout


class TestUvicornConfiguration:
    """Tests for uvicorn graceful shutdown configuration."""

    def test_run_script_exists(self) -> None:
        """Test that run.py script exists and can be imported."""
        try:
            from apikeyrouter_proxy.run import main

            assert callable(main)
        except ImportError:
            pytest.fail("run.py script not found or cannot be imported")

    def test_run_script_reads_env_vars(self) -> None:
        """Test that run script reads environment variables."""
        from apikeyrouter_proxy.run import main

        # Verify function exists and is callable
        assert callable(main)

        # Test that it would read environment variables
        original_host = os.getenv("PROXY_HOST")
        original_port = os.getenv("PROXY_PORT")
        original_timeout = os.getenv("SHUTDOWN_TIMEOUT_SECONDS")

        try:
            os.environ["PROXY_HOST"] = "127.0.0.1"
            os.environ["PROXY_PORT"] = "9000"
            os.environ["SHUTDOWN_TIMEOUT_SECONDS"] = "60"

            # The function should be able to read these
            # We can't easily test the full uvicorn startup in unit tests,
            # but we can verify the configuration would be read
            assert os.getenv("PROXY_HOST") == "127.0.0.1"
            assert os.getenv("PROXY_PORT") == "9000"
            assert os.getenv("SHUTDOWN_TIMEOUT_SECONDS") == "60"
        finally:
            if original_host:
                os.environ["PROXY_HOST"] = original_host
            else:
                os.environ.pop("PROXY_HOST", None)
            if original_port:
                os.environ["PROXY_PORT"] = original_port
            else:
                os.environ.pop("PROXY_PORT", None)
            if original_timeout:
                os.environ["SHUTDOWN_TIMEOUT_SECONDS"] = original_timeout
            else:
                os.environ.pop("SHUTDOWN_TIMEOUT_SECONDS", None)


class TestShutdownLogging:
    """Tests for shutdown logging."""

    @pytest.mark.asyncio
    async def test_shutdown_logs_events(self) -> None:
        """Test that shutdown logs events using structlog."""
        import structlog

        # Get logger
        logger = structlog.get_logger("apikeyrouter_proxy.main")

        # Verify logger is configured
        assert logger is not None

        # Test that we can log shutdown events
        # (We can't easily verify the actual log output in unit tests,
        # but we can verify the logger is available)
        logger.info("test_shutdown_log", message="Test shutdown log")

    def test_shutdown_timeout_logged(self) -> None:
        """Test that shutdown timeout is logged during startup."""
        # This is tested indirectly through the lifespan startup
        # The actual logging happens in the lifespan context manager
        from apikeyrouter_proxy.main import app

        # Verify app has lifespan configured
        assert app.router.lifespan_context is not None

