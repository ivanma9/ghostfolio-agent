import httpx
import pytest
from unittest.mock import AsyncMock, patch

from ghostfolio_agent.clients.base import BaseClient
from ghostfolio_agent.clients.exceptions import (
    APIError, RateLimitError, AuthenticationError, TransientError,
)


class ConcreteClient(BaseClient):
    client_name = "test_client"
    def __init__(self):
        super().__init__(base_url="http://test.com", default_headers={})


class SoftErrorClient(BaseClient):
    client_name = "soft_client"
    def __init__(self):
        super().__init__(base_url="http://test.com", default_headers={})
    def _check_soft_errors(self, response_json):
        if isinstance(response_json, dict) and "Note" in response_json:
            raise RateLimitError(client_name=self.client_name, status_code=200, url="http://test.com", body=response_json["Note"])


class RetryableClient(BaseClient):
    client_name = "retry_client"
    retryable = True
    max_retries = 2
    def __init__(self):
        super().__init__(base_url="http://test.com", default_headers={})


class TestBaseClient:
    @pytest.mark.asyncio
    async def test_successful_get(self):
        client = ConcreteClient()
        mock_response = httpx.Response(200, json={"data": "ok"}, request=httpx.Request("GET", "http://test.com/path"))
        with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_response):
            result = await client._get("/path")
        assert result == {"data": "ok"}

    @pytest.mark.asyncio
    async def test_successful_post(self):
        client = ConcreteClient()
        mock_response = httpx.Response(200, json={"id": 1}, request=httpx.Request("POST", "http://test.com/path"))
        with patch.object(client._http, "post", new_callable=AsyncMock, return_value=mock_response):
            result = await client._post("/path", json_data={"key": "val"})
        assert result == {"id": 1}

    @pytest.mark.asyncio
    async def test_401_raises_authentication_error(self):
        client = ConcreteClient()
        mock_response = httpx.Response(401, text="Unauthorized", request=httpx.Request("GET", "http://test.com/path"))
        with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(AuthenticationError) as exc_info:
                await client._get("/path")
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_403_raises_authentication_error(self):
        client = ConcreteClient()
        mock_response = httpx.Response(403, text="Forbidden", request=httpx.Request("GET", "http://test.com/path"))
        with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(AuthenticationError):
                await client._get("/path")

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit_error(self):
        client = ConcreteClient()
        mock_response = httpx.Response(429, text="Too Many Requests", request=httpx.Request("GET", "http://test.com/path"))
        with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(RateLimitError):
                await client._get("/path")

    @pytest.mark.asyncio
    async def test_500_raises_transient_error(self):
        client = ConcreteClient()
        mock_response = httpx.Response(500, text="Server Error", request=httpx.Request("GET", "http://test.com/path"))
        with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(TransientError):
                await client._get("/path")

    @pytest.mark.asyncio
    async def test_400_raises_api_error(self):
        client = ConcreteClient()
        mock_response = httpx.Response(400, text="Bad Request", request=httpx.Request("GET", "http://test.com/path"))
        with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(APIError) as exc_info:
                await client._get("/path")
            assert type(exc_info.value) is APIError


class TestSoftErrorDetection:
    @pytest.mark.asyncio
    async def test_soft_rate_limit_detected(self):
        client = SoftErrorClient()
        mock_response = httpx.Response(200, json={"Note": "API call frequency exceeded"}, request=httpx.Request("GET", "http://test.com/path"))
        with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(RateLimitError):
                await client._get("/path")

    @pytest.mark.asyncio
    async def test_no_soft_error_passes_through(self):
        client = SoftErrorClient()
        mock_response = httpx.Response(200, json={"data": [1, 2, 3]}, request=httpx.Request("GET", "http://test.com/path"))
        with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_response):
            result = await client._get("/path")
        assert result == {"data": [1, 2, 3]}


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self):
        client = RetryableClient()
        fail_response = httpx.Response(503, text="Unavailable", request=httpx.Request("GET", "http://test.com/path"))
        ok_response = httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", "http://test.com/path"))
        mock_get = AsyncMock(side_effect=[fail_response, ok_response])
        with patch.object(client._http, "get", mock_get), \
             patch("ghostfolio_agent.clients.base.asyncio.sleep", new_callable=AsyncMock):
            result = await client._get("/path")
        assert result == {"ok": True}
        assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_error(self):
        client = RetryableClient()
        fail_response = httpx.Response(401, text="Unauthorized", request=httpx.Request("GET", "http://test.com/path"))
        mock_get = AsyncMock(return_value=fail_response)
        with patch.object(client._http, "get", mock_get):
            with pytest.raises(AuthenticationError):
                await client._get("/path")
        assert mock_get.call_count == 1

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises(self):
        client = RetryableClient()
        fail_response = httpx.Response(500, text="Error", request=httpx.Request("GET", "http://test.com/path"))
        mock_get = AsyncMock(return_value=fail_response)
        with patch.object(client._http, "get", mock_get), \
             patch("ghostfolio_agent.clients.base.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(TransientError):
                await client._get("/path")
        assert mock_get.call_count == 3  # 1 initial + 2 retries

    @pytest.mark.asyncio
    async def test_non_retryable_client_no_retry(self):
        client = ConcreteClient()
        fail_response = httpx.Response(500, text="Error", request=httpx.Request("GET", "http://test.com/path"))
        mock_get = AsyncMock(return_value=fail_response)
        with patch.object(client._http, "get", mock_get):
            with pytest.raises(TransientError):
                await client._get("/path")
        assert mock_get.call_count == 1
