"""Base HTTP client with connection pooling, structured logging, error classification, and retry."""

import asyncio
import time
from typing import Any

import httpx
import structlog

from ghostfolio_agent.clients.exceptions import (
    APIError,
    AuthenticationError,
    RateLimitError,
    TransientError,
)

logger = structlog.get_logger()


class BaseClient:
    """Base class for all API clients.

    Subclasses must set `client_name` (str).
    Optionally set `retryable = True` and `max_retries` for retry on transient errors.
    Override `_check_soft_errors(response_json)` to detect rate limits in 200 responses.
    """

    client_name: str = "unknown"
    retryable: bool = False
    max_retries: int = 2

    def __init__(
        self,
        base_url: str,
        default_headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_headers = default_headers or {}
        self._http = httpx.AsyncClient(
            timeout=timeout or httpx.Timeout(timeout=15.0, connect=5.0),
            headers=self._default_headers,
        )

    def _check_soft_errors(self, response_json: Any) -> None:
        """Override in subclasses to detect soft errors in 200 responses."""
        pass

    def _classify_error(self, response: httpx.Response) -> APIError:
        """Classify HTTP error response into the appropriate exception type."""
        status = response.status_code
        url = str(response.url)
        body = response.text[:500]

        if status in (401, 403):
            return AuthenticationError(self.client_name, status, url, body)
        if status == 429:
            return RateLimitError(self.client_name, status, url, body)
        if status >= 500:
            return TransientError(self.client_name, status, url, body)
        return APIError(self.client_name, status, url, body)

    async def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json_data: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Make an HTTP request with logging, error classification, and optional retry."""
        last_error: APIError | None = None
        attempts = (self.max_retries + 1) if self.retryable else 1

        for attempt in range(attempts):
            if attempt > 0:
                delay = 2 ** (attempt - 1)  # 1s, 2s
                logger.warning(
                    "client_retry",
                    client=self.client_name,
                    attempt=attempt + 1,
                    delay_s=delay,
                    url=url,
                )
                await asyncio.sleep(delay)

            start = time.monotonic()
            try:
                if method == "GET":
                    response = await self._http.get(url, params=params, headers=headers)
                else:
                    response = await self._http.post(url, params=params, json=json_data, headers=headers)
            except httpx.TimeoutException:
                last_error = TransientError(self.client_name, 0, url, "Request timed out")
                logger.warning("client_timeout", client=self.client_name, url=url)
                if self.retryable and attempt < self.max_retries:
                    continue
                raise last_error
            except httpx.RequestError as exc:
                last_error = TransientError(self.client_name, 0, url, str(exc))
                logger.warning("client_connection_error", client=self.client_name, url=url, error=str(exc))
                if self.retryable and attempt < self.max_retries:
                    continue
                raise last_error

            duration_ms = round((time.monotonic() - start) * 1000, 1)

            logger.debug(
                "client_request",
                client=self.client_name,
                method=method,
                url=url,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

            if not response.is_success:
                error = self._classify_error(response)
                logger.warning(
                    "client_error",
                    client=self.client_name,
                    status_code=response.status_code,
                    url=url,
                    duration_ms=duration_ms,
                )
                if isinstance(error, TransientError) and self.retryable and attempt < self.max_retries:
                    last_error = error
                    continue
                raise error

            result = response.json()
            self._check_soft_errors(result)
            return result

        raise last_error or APIError(self.client_name, 0, url, "Unknown error after retries")

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Make a GET request."""
        url = f"{self._base_url}{path}"
        return await self._request("GET", url, params=params)

    async def _post(self, path: str, json_data: dict | None = None) -> Any:
        """Make a POST request."""
        url = f"{self._base_url}{path}"
        return await self._request("POST", url, json_data=json_data)
