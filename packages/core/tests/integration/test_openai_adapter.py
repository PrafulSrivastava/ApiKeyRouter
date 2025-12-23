"""Integration tests for OpenAIAdapter."""

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from apikeyrouter.domain.models.api_key import APIKey, KeyState
from apikeyrouter.domain.models.request_intent import Message, RequestIntent
from apikeyrouter.domain.models.system_error import ErrorCategory, SystemError
from apikeyrouter.infrastructure.adapters.openai_adapter import OpenAIAdapter
from apikeyrouter.infrastructure.utils.encryption import encrypt_key_material


@pytest.fixture
def encryption_key() -> str:
    """Set up encryption key for tests."""
    # Use a test encryption key
    key = "test-encryption-key-32-chars-long!!"
    os.environ["APIKEYROUTER_ENCRYPTION_KEY"] = key
    os.environ["APIKEYROUTER_ENCRYPTION_SALT"] = "test-salt"
    return key


@pytest.fixture
def api_key(encryption_key: str) -> APIKey:
    """Create a test API key."""
    plain_key = "sk-test123456789"
    encrypted_key = encrypt_key_material(plain_key)
    return APIKey(
        id="key-1",
        key_material=encrypted_key,
        provider_id="openai",
        state=KeyState.Available,
    )


@pytest.fixture
def request_intent() -> RequestIntent:
    """Create a test request intent."""
    return RequestIntent(
        model="gpt-4",
        messages=[Message(role="user", content="Hello!")],
        parameters={"temperature": 0.7, "max_tokens": 100},
    )


@pytest.fixture
def openai_adapter() -> OpenAIAdapter:
    """Create OpenAI adapter instance."""
    return OpenAIAdapter()


class TestOpenAIAdapterExecuteRequest:
    """Tests for execute_request method."""

    @pytest.mark.asyncio
    async def test_execute_request_success(
        self,
        openai_adapter: OpenAIAdapter,
        api_key: APIKey,
        request_intent: RequestIntent,
    ) -> None:
        """Test successful request execution."""
        # Mock OpenAI API response
        mock_response = {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1677652288,
            "model": "gpt-4",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello! How can I help?"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        # Mock httpx.AsyncClient
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response_obj)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            # Execute request
            response = await openai_adapter.execute_request(request_intent, api_key)

            # Verify response
            assert response.content == "Hello! How can I help?"
            assert response.metadata.model_used == "gpt-4"
            assert response.metadata.tokens_used.input_tokens == 10
            assert response.metadata.tokens_used.output_tokens == 5
            assert response.metadata.tokens_used.total_tokens == 15
            assert response.key_used == api_key.id

            # Verify HTTP request was made correctly
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "https://api.openai.com/v1/chat/completions"
            assert "Authorization" in call_args[1]["headers"]
            assert call_args[1]["headers"]["Authorization"].startswith("Bearer ")
            assert call_args[1]["headers"]["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_execute_request_converts_intent_correctly(
        self,
        openai_adapter: OpenAIAdapter,
        api_key: APIKey,
        request_intent: RequestIntent,
    ) -> None:
        """Test that RequestIntent is converted to OpenAI format correctly."""
        mock_response = {
            "id": "chatcmpl-123",
            "choices": [{"message": {"content": "test"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()
            mock_client.post = AsyncMock(return_value=mock_response_obj)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            await openai_adapter.execute_request(request_intent, api_key)

            # Verify request format
            call_args = mock_client.post.call_args
            request_data = call_args[1]["json"]
            assert request_data["model"] == "gpt-4"
            assert len(request_data["messages"]) == 1
            assert request_data["messages"][0]["role"] == "user"
            assert request_data["messages"][0]["content"] == "Hello!"
            assert request_data["temperature"] == 0.7
            assert request_data["max_tokens"] == 100

    @pytest.mark.asyncio
    async def test_execute_request_handles_authentication_error(
        self,
        openai_adapter: OpenAIAdapter,
        api_key: APIKey,
        request_intent: RequestIntent,
    ) -> None:
        """Test handling of 401 authentication error."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 401
            mock_response_obj.text = "Invalid API key"
            mock_response_obj.headers = {}
            mock_response_obj.json.return_value = {}
            mock_response_obj.raise_for_status.side_effect = httpx.HTTPStatusError(
                "401", request=MagicMock(), response=mock_response_obj
            )
            mock_client.post = AsyncMock(side_effect=mock_response_obj.raise_for_status)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(SystemError) as exc_info:
                await openai_adapter.execute_request(request_intent, api_key)

            assert exc_info.value.category == ErrorCategory.AuthenticationError
            # Message can be from response body or default
            assert "invalid" in exc_info.value.message.lower() or "authentication" in exc_info.value.message.lower()
            assert exc_info.value.retryable is False

    @pytest.mark.asyncio
    async def test_execute_request_handles_rate_limit_error(
        self,
        openai_adapter: OpenAIAdapter,
        api_key: APIKey,
        request_intent: RequestIntent,
    ) -> None:
        """Test handling of 429 rate limit error."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 429
            mock_response_obj.text = "Rate limit exceeded"
            mock_response_obj.raise_for_status.side_effect = httpx.HTTPStatusError(
                "429", request=MagicMock(), response=mock_response_obj
            )
            mock_client.post = AsyncMock(side_effect=mock_response_obj.raise_for_status)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(SystemError) as exc_info:
                await openai_adapter.execute_request(request_intent, api_key)

            assert exc_info.value.category == ErrorCategory.RateLimitError
            assert "rate limit" in exc_info.value.message.lower()
            assert exc_info.value.retryable is True

    @pytest.mark.asyncio
    async def test_execute_request_handles_timeout(
        self,
        openai_adapter: OpenAIAdapter,
        api_key: APIKey,
        request_intent: RequestIntent,
    ) -> None:
        """Test handling of timeout error."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(SystemError) as exc_info:
                await openai_adapter.execute_request(request_intent, api_key)

            assert exc_info.value.category == ErrorCategory.TimeoutError
            assert "timed out" in exc_info.value.message.lower() or "timeout" in exc_info.value.message.lower()
            assert exc_info.value.retryable is True

    @pytest.mark.asyncio
    async def test_execute_request_handles_network_error(
        self,
        openai_adapter: OpenAIAdapter,
        api_key: APIKey,
        request_intent: RequestIntent,
    ) -> None:
        """Test handling of network error."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.NetworkError("Network error"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(SystemError) as exc_info:
                await openai_adapter.execute_request(request_intent, api_key)

            assert exc_info.value.category == ErrorCategory.NetworkError
            assert "network" in exc_info.value.message.lower()
            assert exc_info.value.retryable is True

    @pytest.mark.asyncio
    async def test_execute_request_handles_server_error(
        self,
        openai_adapter: OpenAIAdapter,
        api_key: APIKey,
        request_intent: RequestIntent,
    ) -> None:
        """Test handling of 500 server error."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 500
            mock_response_obj.text = "Internal server error"
            mock_response_obj.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500", request=MagicMock(), response=mock_response_obj
            )
            mock_client.post = AsyncMock(side_effect=mock_response_obj.raise_for_status)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_class.return_value = mock_client

            with pytest.raises(SystemError) as exc_info:
                await openai_adapter.execute_request(request_intent, api_key)

            assert exc_info.value.category == ErrorCategory.ProviderError
            assert "server error" in exc_info.value.message.lower()
            assert exc_info.value.retryable is True


class TestOpenAIAdapterNormalizeResponse:
    """Tests for normalize_response method."""

    def test_normalize_response_converts_openai_format(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that OpenAI response is normalized correctly."""
        openai_response = {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1677652288,
            "model": "gpt-4",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            "_key_id": "key-1",
            "_request_id": "req-1",
        }

        response = openai_adapter.normalize_response(openai_response)

        assert response.content == "Hello!"
        assert response.metadata.model_used == "gpt-4"
        assert response.metadata.tokens_used.input_tokens == 100
        assert response.metadata.tokens_used.output_tokens == 50
        assert response.metadata.tokens_used.total_tokens == 150
        assert response.metadata.finish_reason == "stop"
        assert response.key_used == "key-1"
        assert response.request_id == "req-1"

    def test_normalize_response_handles_no_choices(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that normalize_response raises error when no choices."""
        openai_response = {"choices": []}

        with pytest.raises(SystemError) as exc_info:
            openai_adapter.normalize_response(openai_response)

        assert exc_info.value.category == ErrorCategory.ProviderError
        assert "no choices" in exc_info.value.message.lower()

    def test_normalize_response_handles_multiple_choices(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that normalize_response uses first choice when multiple choices present."""
        openai_response = {
            "model": "gpt-4",
            "choices": [
                {
                    "message": {"content": "First response"},
                    "finish_reason": "stop",
                },
                {
                    "message": {"content": "Second response"},
                    "finish_reason": "stop",
                },
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "_key_id": "key-1",
            "_request_id": "req-1",
        }

        response = openai_adapter.normalize_response(openai_response)

        assert response.content == "First response"
        assert response.metadata.model_used == "gpt-4"

    def test_normalize_response_handles_empty_content(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that normalize_response handles empty content gracefully."""
        openai_response = {
            "model": "gpt-4",
            "choices": [
                {
                    "message": {"content": ""},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 0},
            "_key_id": "key-1",
            "_request_id": "req-1",
        }

        response = openai_adapter.normalize_response(openai_response)

        assert response.content == ""
        assert response.metadata.tokens_used.output_tokens == 0

    def test_normalize_response_handles_missing_usage(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that normalize_response handles missing usage field gracefully."""
        openai_response = {
            "model": "gpt-4",
            "choices": [
                {
                    "message": {"content": "Hello"},
                    "finish_reason": "stop",
                }
            ],
            "_key_id": "key-1",
            "_request_id": "req-1",
        }

        response = openai_adapter.normalize_response(openai_response)

        assert response.content == "Hello"
        assert response.metadata.tokens_used.input_tokens == 0
        assert response.metadata.tokens_used.output_tokens == 0
        assert response.metadata.tokens_used.total_tokens == 0

    def test_normalize_response_handles_missing_model(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that normalize_response handles missing model field gracefully."""
        openai_response = {
            "choices": [
                {
                    "message": {"content": "Hello"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "_key_id": "key-1",
            "_request_id": "req-1",
        }

        response = openai_adapter.normalize_response(openai_response)

        assert response.content == "Hello"
        assert response.metadata.model_used == "unknown"

    def test_normalize_response_handles_missing_message(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that normalize_response handles missing message field gracefully."""
        openai_response = {
            "model": "gpt-4",
            "choices": [
                {
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "_key_id": "key-1",
            "_request_id": "req-1",
        }

        response = openai_adapter.normalize_response(openai_response)

        assert response.content == ""  # Empty content when message missing
        assert response.metadata.model_used == "gpt-4"

    def test_normalize_response_preserves_additional_metadata(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that normalize_response preserves additional metadata."""
        openai_response = {
            "id": "chatcmpl-abc123",
            "object": "chat.completion",
            "created": 1677652288,
            "model": "gpt-4",
            "choices": [
                {
                    "message": {"content": "Hello"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "_key_id": "key-1",
            "_request_id": "req-1",
        }

        response = openai_adapter.normalize_response(openai_response)

        assert response.metadata.additional_metadata["id"] == "chatcmpl-abc123"
        assert response.metadata.additional_metadata["object"] == "chat.completion"
        assert response.metadata.additional_metadata["created"] == 1677652288

    def test_normalize_response_handles_partial_usage_data(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that normalize_response handles partial usage data."""
        openai_response = {
            "model": "gpt-4",
            "choices": [
                {
                    "message": {"content": "Hello"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                # Missing completion_tokens
            },
            "_key_id": "key-1",
            "_request_id": "req-1",
        }

        response = openai_adapter.normalize_response(openai_response)

        assert response.metadata.tokens_used.input_tokens == 10
        assert response.metadata.tokens_used.output_tokens == 0  # Defaults to 0
        assert response.metadata.tokens_used.total_tokens == 10


class TestOpenAIAdapterMapError:
    """Tests for map_error method."""

    def test_map_error_401_authentication(self, openai_adapter: OpenAIAdapter) -> None:
        """Test mapping 401 to AuthenticationError."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        error = httpx.HTTPStatusError("401", request=MagicMock(), response=mock_response)

        system_error = openai_adapter.map_error(error)

        assert system_error.category == ErrorCategory.AuthenticationError
        assert system_error.retryable is False

    def test_map_error_429_rate_limit(self, openai_adapter: OpenAIAdapter) -> None:
        """Test mapping 429 to RateLimitError."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        error = httpx.HTTPStatusError("429", request=MagicMock(), response=mock_response)

        system_error = openai_adapter.map_error(error)

        assert system_error.category == ErrorCategory.RateLimitError
        assert system_error.retryable is True

    def test_map_error_500_server_error(self, openai_adapter: OpenAIAdapter) -> None:
        """Test mapping 500 to ProviderError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        error = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)

        system_error = openai_adapter.map_error(error)

        assert system_error.category == ErrorCategory.ProviderError
        assert system_error.retryable is True

    def test_map_error_timeout(self, openai_adapter: OpenAIAdapter) -> None:
        """Test mapping timeout to TimeoutError."""
        error = httpx.TimeoutException("Timeout")

        system_error = openai_adapter.map_error(error)

        assert system_error.category == ErrorCategory.TimeoutError
        assert system_error.retryable is True

    def test_map_error_network(self, openai_adapter: OpenAIAdapter) -> None:
        """Test mapping network error to NetworkError."""
        error = httpx.NetworkError("Network error")

        system_error = openai_adapter.map_error(error)

        assert system_error.category == ErrorCategory.NetworkError
        assert system_error.retryable is True

    def test_map_error_extracts_retry_after_header(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that map_error extracts retry-after header from 429 response."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_response.headers = {"retry-after": "60"}
        mock_response.json.return_value = {}
        error = httpx.HTTPStatusError("429", request=MagicMock(), response=mock_response)

        system_error = openai_adapter.map_error(error)

        assert system_error.category == ErrorCategory.RateLimitError
        assert system_error.retry_after == 60
        assert system_error.retryable is True

    def test_map_error_extracts_retry_after_datetime(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that map_error extracts retry-after as HTTP date."""
        from datetime import timedelta

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        # HTTP date format: Wed, 21 Oct 2015 07:28:00 GMT
        retry_date = datetime.now(UTC) + timedelta(seconds=120)
        mock_response.headers = {"retry-after": retry_date.strftime("%a, %d %b %Y %H:%M:%S GMT")}
        mock_response.json.return_value = {}
        error = httpx.HTTPStatusError("429", request=MagicMock(), response=mock_response)

        system_error = openai_adapter.map_error(error)

        assert system_error.category == ErrorCategory.RateLimitError
        # Should be approximately 120 seconds (allow some tolerance)
        assert system_error.retry_after is not None
        assert 100 <= system_error.retry_after <= 140

    def test_map_error_extracts_error_details_from_json(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that map_error extracts error details from JSON response body."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"error": {"message": "Invalid request", "type": "invalid_request_error", "code": "invalid_parameter"}}'
        mock_response.headers = {}
        mock_response.json.return_value = {
            "error": {
                "message": "Invalid request",
                "type": "invalid_request_error",
                "code": "invalid_parameter",
                "param": "model",
            }
        }
        error = httpx.HTTPStatusError("400", request=MagicMock(), response=mock_response)

        system_error = openai_adapter.map_error(error)

        assert system_error.category == ErrorCategory.ValidationError
        assert system_error.details["message"] == "Invalid request"
        assert system_error.details["type"] == "invalid_request_error"
        assert system_error.details["code"] == "invalid_parameter"
        assert system_error.details["param"] == "model"
        assert system_error.provider_code == "invalid_parameter"

    def test_map_error_handles_missing_error_object(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that map_error handles response without error object."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_response.headers = {}
        mock_response.json.return_value = {"message": "Something went wrong"}
        error = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)

        system_error = openai_adapter.map_error(error)

        assert system_error.category == ErrorCategory.ProviderError
        assert system_error.details.get("message") == "Something went wrong"

    def test_map_error_handles_non_json_response(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that map_error handles non-JSON response body."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error - plain text"
        mock_response.headers = {}
        mock_response.json.side_effect = ValueError("Not JSON")
        error = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_response)

        system_error = openai_adapter.map_error(error)

        assert system_error.category == ErrorCategory.ProviderError
        assert system_error.details.get("message") == "Internal server error - plain text"

    def test_map_error_handles_missing_retry_after(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that map_error handles missing retry-after header."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_response.headers = {}  # No retry-after header
        mock_response.json.return_value = {}
        error = httpx.HTTPStatusError("429", request=MagicMock(), response=mock_response)

        system_error = openai_adapter.map_error(error)

        assert system_error.category == ErrorCategory.RateLimitError
        assert system_error.retry_after is None

    def test_map_error_handles_invalid_retry_after(
        self, openai_adapter: OpenAIAdapter
    ) -> None:
        """Test that map_error handles invalid retry-after header."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_response.headers = {"retry-after": "invalid"}
        mock_response.json.return_value = {}
        error = httpx.HTTPStatusError("429", request=MagicMock(), response=mock_response)

        system_error = openai_adapter.map_error(error)

        assert system_error.category == ErrorCategory.RateLimitError
        assert system_error.retry_after is None  # Should be None if parsing fails

