# Error Handling & Observability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add structured logging, request tracing, custom exceptions, retry logic, and consistent error handling across the entire AgentForge backend.

**Architecture:** BaseClient inheritance for shared HTTP logic (connection pooling, logging, error classification, retry). Structlog configured with JSON/console output and correlation IDs via contextvars. Request middleware for per-request tracing. Shared `safe_fetch` utility replacing 3 duplicates.

**Tech Stack:** structlog (already installed), httpx (already installed), contextvars (stdlib), uuid (stdlib)

---

### Task 1: Custom Exception Hierarchy

**Files:**
- Create: `src/ghostfolio_agent/clients/exceptions.py`
- Test: `tests/unit/test_client_exceptions.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_client_exceptions.py
import pytest
from ghostfolio_agent.clients.exceptions import (
    APIError, RateLimitError, AuthenticationError, TransientError,
)


class TestExceptionHierarchy:
    def test_api_error_is_exception(self):
        err = APIError(client_name="test", status_code=400, url="http://x", body="bad")
        assert isinstance(err, Exception)
        assert err.client_name == "test"
        assert err.status_code == 400
        assert err.url == "http://x"
        assert err.body == "bad"
        assert "test" in str(err)
        assert "400" in str(err)

    def test_rate_limit_error_is_api_error(self):
        err = RateLimitError(client_name="alpha_vantage", status_code=429, url="http://x", body="limit")
        assert isinstance(err, APIError)

    def test_authentication_error_is_api_error(self):
        err = AuthenticationError(client_name="ghostfolio", status_code=401, url="http://x", body="unauth")
        assert isinstance(err, APIError)

    def test_transient_error_is_api_error(self):
        err = TransientError(client_name="finnhub", status_code=503, url="http://x", body="down")
        assert isinstance(err, APIError)

    def test_api_error_str(self):
        err = APIError(client_name="fmp", status_code=500, url="http://api.fmp.com/test", body="Internal Server Error")
        s = str(err)
        assert "fmp" in s
        assert "500" in s
        assert "http://api.fmp.com/test" in s
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_client_exceptions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ghostfolio_agent.clients.exceptions'`

**Step 3: Write minimal implementation**

```python
# src/ghostfolio_agent/clients/exceptions.py
"""Custom exception hierarchy for API clients."""


class APIError(Exception):
    """Base exception for all API client errors."""

    def __init__(self, client_name: str, status_code: int, url: str, body: str) -> None:
        self.client_name = client_name
        self.status_code = status_code
        self.url = url
        self.body = body
        super().__init__(
            f"{client_name} API error: {status_code} for {url} — {body[:500]}"
        )


class RateLimitError(APIError):
    """Rate limit exceeded (HTTP 429 or soft rate limit in response body)."""
    pass


class AuthenticationError(APIError):
    """Authentication failed (HTTP 401/403)."""
    pass


class TransientError(APIError):
    """Transient server error (HTTP 5xx, timeouts). Safe to retry."""
    pass
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_client_exceptions.py -v`
Expected: PASS — all 5 tests green

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/clients/exceptions.py tests/unit/test_client_exceptions.py
git commit -m "feat: add custom exception hierarchy for API clients"
```

---

### Task 2: Structlog Configuration

**Files:**
- Create: `src/ghostfolio_agent/logging_config.py`
- Modify: `src/ghostfolio_agent/config.py` (add `log_format` field)
- Test: `tests/unit/test_logging_config.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_logging_config.py
import json
import logging
import structlog
import pytest
from ghostfolio_agent.logging_config import configure_logging, get_request_id, set_request_id


class TestConfigureLogging:
    def test_configure_json_format(self):
        configure_logging(log_level="info", log_format="json")
        logger = structlog.get_logger("test_json")
        # Should not raise
        logger.info("test_event", key="value")

    def test_configure_console_format(self):
        configure_logging(log_level="debug", log_format="console")
        logger = structlog.get_logger("test_console")
        logger.info("test_event", key="value")

    def test_log_level_applied(self):
        configure_logging(log_level="warning", log_format="json")
        root = logging.getLogger()
        assert root.level == logging.WARNING


class TestRequestId:
    def test_set_and_get_request_id(self):
        set_request_id("test-123")
        assert get_request_id() == "test-123"

    def test_default_request_id_is_none(self):
        # Reset by setting to empty
        set_request_id("")
        assert get_request_id() == ""
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_logging_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ghostfolio_agent.logging_config'`

**Step 3: Write minimal implementation**

```python
# src/ghostfolio_agent/logging_config.py
"""Structlog configuration with correlation ID support."""

import logging
import sys
from contextvars import ContextVar

import structlog

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    return _request_id_var.get()


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def _add_request_id(logger, method_name, event_dict):
    """Structlog processor that injects request_id from context."""
    request_id = get_request_id()
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def configure_logging(log_level: str = "info", log_format: str = "json") -> None:
    """Configure structlog and stdlib logging.

    Args:
        log_level: Python log level name (debug, info, warning, error).
        log_format: "json" for production, "console" for development.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=numeric_level, force=True)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        _add_request_id,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_logger_name,
    ]

    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(numeric_level)
```

**Step 4: Add `log_format` to config**

In `src/ghostfolio_agent/config.py`, add this field to the `Settings` class after the `log_level` line:

```python
    log_format: str = "json"
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_logging_config.py -v`
Expected: PASS — all 5 tests green

**Step 6: Commit**

```bash
git add src/ghostfolio_agent/logging_config.py src/ghostfolio_agent/config.py tests/unit/test_logging_config.py
git commit -m "feat: add structlog configuration with correlation IDs"
```

---

### Task 3: Request Logging Middleware

**Files:**
- Create: `src/ghostfolio_agent/api/middleware.py`
- Modify: `src/ghostfolio_agent/main.py` (add middleware + call `configure_logging`)
- Test: `tests/unit/test_middleware.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_middleware.py
import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ghostfolio_agent.api.middleware import RequestLoggingMiddleware
from ghostfolio_agent.logging_config import get_request_id


@pytest.fixture
def app_with_middleware():
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/test")
    async def test_endpoint():
        return {"request_id": get_request_id()}

    return app


@pytest.fixture
def client(app_with_middleware):
    return TestClient(app_with_middleware)


class TestRequestLoggingMiddleware:
    def test_sets_request_id(self, client):
        response = client.get("/test")
        assert response.status_code == 200
        data = response.json()
        # request_id should be a non-empty UUID string
        assert data["request_id"]
        assert len(data["request_id"]) == 36  # UUID format

    def test_returns_request_id_header(self, client):
        response = client.get("/test")
        assert "x-request-id" in response.headers
        assert len(response.headers["x-request-id"]) == 36

    def test_logs_request_start_and_end(self, client):
        with patch("ghostfolio_agent.api.middleware.logger") as mock_logger:
            response = client.get("/test")
            assert response.status_code == 200
            # Should have at least 2 log calls (start + end)
            assert mock_logger.info.call_count >= 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_middleware.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ghostfolio_agent.api.middleware'`

**Step 3: Write minimal implementation**

```python
# src/ghostfolio_agent/api/middleware.py
"""Request logging middleware with correlation IDs."""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ghostfolio_agent.logging_config import set_request_id

logger = structlog.get_logger()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        set_request_id(request_id)

        start_time = time.monotonic()

        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            request_id=request_id,
        )

        response = await call_next(request)

        duration_ms = round((time.monotonic() - start_time) * 1000, 1)

        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
        )

        response.headers["x-request-id"] = request_id
        return response
```

**Step 4: Wire up middleware and logging in `main.py`**

Replace the full `src/ghostfolio_agent/main.py` with:

```python
import pathlib
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import structlog

from ghostfolio_agent.config import get_settings
from ghostfolio_agent.logging_config import configure_logging
from ghostfolio_agent.api.chat import router as chat_router
from ghostfolio_agent.api.middleware import RequestLoggingMiddleware

settings = get_settings()
configure_logging(log_level=settings.log_level, log_format=settings.log_format)
logger = structlog.get_logger()

STATIC_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting ghostfolio-agent", port=settings.agent_port)
    yield
    logger.info("shutting down ghostfolio-agent")


app = FastAPI(title="Ghostfolio Agent", version="0.1.0", lifespan=lifespan)

_allowed_origins = [settings.domain] if settings.domain else ["*"]

app.add_middleware(CORSMiddleware, allow_origins=_allowed_origins,
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(RequestLoggingMiddleware)

app.include_router(chat_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve frontend static files (built React app) — must come after API routes
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_middleware.py -v`
Expected: PASS — all 3 tests green

**Step 6: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All existing tests still pass (main.py changes are additive)

**Step 7: Commit**

```bash
git add src/ghostfolio_agent/api/middleware.py src/ghostfolio_agent/main.py tests/unit/test_middleware.py
git commit -m "feat: add request logging middleware with correlation IDs"
```

---

### Task 4: BaseClient with Connection Pooling, Logging, and Error Classification

**Files:**
- Create: `src/ghostfolio_agent/clients/base.py`
- Test: `tests/unit/test_base_client.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_base_client.py
import httpx
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from ghostfolio_agent.clients.base import BaseClient
from ghostfolio_agent.clients.exceptions import (
    APIError, RateLimitError, AuthenticationError, TransientError,
)


class ConcreteClient(BaseClient):
    """Test subclass."""
    client_name = "test_client"

    def __init__(self):
        super().__init__(base_url="http://test.com", default_headers={})


class SoftErrorClient(BaseClient):
    """Client with soft error detection."""
    client_name = "soft_client"

    def __init__(self):
        super().__init__(base_url="http://test.com", default_headers={})

    def _check_soft_errors(self, response_json):
        if isinstance(response_json, dict) and "Note" in response_json:
            raise RateLimitError(
                client_name=self.client_name,
                status_code=200,
                url="http://test.com",
                body=response_json["Note"],
            )


class RetryableClient(BaseClient):
    """Client that retries on transient errors."""
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
            # Should be base APIError, not a subclass
            assert type(exc_info.value) is APIError


class TestSoftErrorDetection:
    @pytest.mark.asyncio
    async def test_soft_rate_limit_detected(self):
        client = SoftErrorClient()
        mock_response = httpx.Response(
            200,
            json={"Note": "API call frequency exceeded"},
            request=httpx.Request("GET", "http://test.com/path"),
        )
        with patch.object(client._http, "get", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(RateLimitError):
                await client._get("/path")

    @pytest.mark.asyncio
    async def test_no_soft_error_passes_through(self):
        client = SoftErrorClient()
        mock_response = httpx.Response(
            200,
            json={"data": [1, 2, 3]},
            request=httpx.Request("GET", "http://test.com/path"),
        )
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
        # 1 initial + 2 retries = 3 total
        assert mock_get.call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_client_no_retry(self):
        client = ConcreteClient()  # retryable = False (default)
        fail_response = httpx.Response(500, text="Error", request=httpx.Request("GET", "http://test.com/path"))

        mock_get = AsyncMock(return_value=fail_response)
        with patch.object(client._http, "get", mock_get):
            with pytest.raises(TransientError):
                await client._get("/path")
        assert mock_get.call_count == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_base_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ghostfolio_agent.clients.base'`

**Step 3: Write minimal implementation**

```python
# src/ghostfolio_agent/clients/base.py
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
            timeout=timeout or httpx.Timeout(connect=5.0, read=15.0),
            headers=self._default_headers,
        )

    def _check_soft_errors(self, response_json: Any) -> None:
        """Override in subclasses to detect soft errors (e.g., rate limits in 200 responses).

        Should raise RateLimitError or APIError if a soft error is detected.
        """
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
                # Only retry transient errors
                if isinstance(error, TransientError) and self.retryable and attempt < self.max_retries:
                    last_error = error
                    continue
                raise error

            result = response.json()
            self._check_soft_errors(result)
            return result

        # Should not reach here, but just in case
        raise last_error or APIError(self.client_name, 0, url, "Unknown error after retries")

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Make a GET request."""
        url = f"{self._base_url}{path}"
        return await self._request("GET", url, params=params)

    async def _post(self, path: str, json_data: dict | None = None) -> Any:
        """Make a POST request."""
        url = f"{self._base_url}{path}"
        return await self._request("POST", url, json_data=json_data)
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_base_client.py -v`
Expected: PASS — all 12 tests green

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/clients/base.py tests/unit/test_base_client.py
git commit -m "feat: add BaseClient with connection pooling, error classification, and retry"
```

---

### Task 5: Migrate Ghostfolio Client to BaseClient

**Files:**
- Modify: `src/ghostfolio_agent/clients/ghostfolio.py`
- Test: `tests/unit/test_clients_init.py` (existing — verify no regressions)

**Step 1: Rewrite `ghostfolio.py` to inherit from BaseClient**

```python
# src/ghostfolio_agent/clients/ghostfolio.py
from typing import Any

from ghostfolio_agent.clients.base import BaseClient


class GhostfolioClient(BaseClient):
    """Async HTTP client for Ghostfolio REST API. Retries on transient errors."""

    client_name = "ghostfolio"
    retryable = True
    max_retries = 2

    def __init__(self, base_url: str, access_token: str) -> None:
        super().__init__(
            base_url=base_url,
            default_headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )

    async def get_portfolio_holdings(self) -> dict[str, Any]:
        """Get portfolio holdings with values and allocations."""
        return await self._get("/api/v1/portfolio/holdings")

    async def get_portfolio_details(self) -> dict[str, Any]:
        """Get detailed portfolio breakdown."""
        return await self._get("/api/v1/portfolio/details")

    async def get_orders(self) -> list[dict[str, Any]]:
        """Get all transactions/orders."""
        result = await self._get("/api/v1/order")
        return result.get("activities", [])

    async def lookup_symbol(self, query: str) -> dict[str, Any]:
        """Search for symbols by name or ticker."""
        return await self._get("/api/v1/symbol/lookup", params={"query": query})

    async def get_symbol(self, data_source: str, symbol: str) -> dict[str, Any]:
        """Get details for a specific symbol."""
        return await self._get(f"/api/v1/symbol/{data_source}/{symbol}")

    async def get_portfolio_performance(self, date_range: str = "max") -> dict[str, Any]:
        """Get portfolio performance for a date range."""
        return await self._get("/api/v2/portfolio/performance", params={"range": date_range})

    async def get_holding(self, data_source: str, symbol: str) -> dict[str, Any]:
        """Get detailed info for a specific portfolio holding."""
        return await self._get(f"/api/v1/portfolio/holding/{data_source}/{symbol}")

    async def get_accounts(self) -> list[dict[str, Any]]:
        """Get all accounts."""
        result = await self._get("/api/v1/account")
        return result.get("accounts", result) if isinstance(result, dict) else result

    async def create_order(self, order_data: dict) -> dict[str, Any]:
        """Create a new order/activity."""
        return await self._post("/api/v1/order", json_data=order_data)
```

**Step 2: Run existing client tests**

Run: `uv run pytest tests/unit/test_clients_init.py -v`
Expected: PASS — existing tests still work

**Step 3: Run full test suite to check for regressions**

Run: `uv run pytest tests/unit/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add src/ghostfolio_agent/clients/ghostfolio.py
git commit -m "refactor: migrate GhostfolioClient to BaseClient with retry"
```

---

### Task 6: Migrate Finnhub Client to BaseClient

**Files:**
- Modify: `src/ghostfolio_agent/clients/finnhub.py`
- Test: `tests/unit/test_finnhub_client.py` (existing — verify no regressions)

**Step 1: Rewrite `finnhub.py` to inherit from BaseClient**

```python
# src/ghostfolio_agent/clients/finnhub.py
from typing import Any, cast

from ghostfolio_agent.clients.base import BaseClient


class FinnhubClient(BaseClient):
    """Async HTTP client for Finnhub API (analyst recs, earnings)."""

    client_name = "finnhub"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        super().__init__(
            base_url="https://finnhub.io/api/v1",
            default_headers={},
        )

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Make authenticated GET request to Finnhub (injects API key)."""
        request_params = {"token": self._api_key}
        if params:
            request_params.update(params)
        return await self._request("GET", f"{self._base_url}{path}", params=request_params)

    async def get_analyst_recommendations(self, symbol: str) -> list[dict[str, Any]]:
        """Get analyst recommendation trends for a symbol."""
        return cast(list[dict[str, Any]], await self._get("/stock/recommendation", params={"symbol": symbol}))

    async def get_earnings_calendar(self, symbol: str) -> list[dict[str, Any]]:
        """Get upcoming earnings dates and estimates for a symbol."""
        result = await self._get("/calendar/earnings", params={"symbol": symbol})
        return cast(list[dict[str, Any]], result.get("earningsCalendar", []))

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """Get real-time quote for a symbol."""
        return cast(dict[str, Any], await self._get("/quote", params={"symbol": symbol}))
```

**Step 2: Run existing tests**

Run: `uv run pytest tests/unit/test_finnhub_client.py -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass

**Step 4: Commit**

```bash
git add src/ghostfolio_agent/clients/finnhub.py
git commit -m "refactor: migrate FinnhubClient to BaseClient"
```

---

### Task 7: Migrate Alpha Vantage Client to BaseClient

**Files:**
- Modify: `src/ghostfolio_agent/clients/alpha_vantage.py`
- Test: `tests/unit/test_alpha_vantage_client.py` (existing — verify no regressions)

**Step 1: Rewrite `alpha_vantage.py` to inherit from BaseClient with soft error detection**

```python
# src/ghostfolio_agent/clients/alpha_vantage.py
from typing import Any, cast

from ghostfolio_agent.clients.base import BaseClient
from ghostfolio_agent.clients.exceptions import RateLimitError


class AlphaVantageClient(BaseClient):
    """Async HTTP client for Alpha Vantage API (news sentiment, macro indicators)."""

    client_name = "alpha_vantage"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        super().__init__(
            base_url="https://www.alphavantage.co",
            default_headers={},
        )

    def _check_soft_errors(self, response_json: Any) -> None:
        """Alpha Vantage returns 200 with 'Note' or 'Information' key when rate-limited."""
        if isinstance(response_json, dict):
            for key in ("Note", "Information"):
                if key in response_json:
                    raise RateLimitError(
                        client_name=self.client_name,
                        status_code=200,
                        url="alphavantage.co",
                        body=response_json[key][:500],
                    )

    async def _query(self, params: dict[str, Any]) -> Any:
        """Make authenticated GET to the query endpoint."""
        request_params = {**params, "apikey": self._api_key}
        return await self._request("GET", f"{self._base_url}/query", params=request_params)

    async def get_news_sentiment(self, ticker: str) -> list[dict[str, Any]]:
        """Get news sentiment for a ticker symbol."""
        result = await self._query({"function": "NEWS_SENTIMENT", "tickers": ticker})
        return cast(list[dict[str, Any]], result.get("feed", []))

    async def get_fed_funds_rate(self) -> list[dict[str, Any]]:
        """Get Federal Funds effective rate (daily)."""
        result = await self._query({"function": "FEDERAL_FUNDS_RATE", "interval": "daily"})
        return cast(list[dict[str, Any]], result.get("data", []))

    async def get_cpi(self) -> list[dict[str, Any]]:
        """Get Consumer Price Index (monthly)."""
        result = await self._query({"function": "CPI", "interval": "monthly"})
        return cast(list[dict[str, Any]], result.get("data", []))

    async def get_treasury_yield(self, maturity: str = "10year") -> list[dict[str, Any]]:
        """Get Treasury Yield (daily)."""
        result = await self._query({
            "function": "TREASURY_YIELD",
            "interval": "daily",
            "maturity": maturity,
        })
        return cast(list[dict[str, Any]], result.get("data", []))
```

**Step 2: Run existing tests**

Run: `uv run pytest tests/unit/test_alpha_vantage_client.py -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass

**Step 4: Commit**

```bash
git add src/ghostfolio_agent/clients/alpha_vantage.py
git commit -m "refactor: migrate AlphaVantageClient to BaseClient with soft error detection"
```

---

### Task 8: Migrate FMP Client to BaseClient

**Files:**
- Modify: `src/ghostfolio_agent/clients/fmp.py`
- Test: `tests/unit/test_fmp_client.py` (existing — verify no regressions)

**Step 1: Rewrite `fmp.py` to inherit from BaseClient with soft error detection**

```python
# src/ghostfolio_agent/clients/fmp.py
from typing import Any, cast

from ghostfolio_agent.clients.base import BaseClient
from ghostfolio_agent.clients.exceptions import APIError


class FMPClient(BaseClient):
    """Async HTTP client for Financial Modeling Prep API (analyst estimates, price targets)."""

    client_name = "fmp"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        super().__init__(
            base_url="https://financialmodelingprep.com/stable",
            default_headers={},
        )

    def _check_soft_errors(self, response_json: Any) -> None:
        """FMP returns 200 with 'Error Message' key on invalid API key or bad request."""
        if isinstance(response_json, dict) and "Error Message" in response_json:
            raise APIError(
                client_name=self.client_name,
                status_code=200,
                url="fmp",
                body=response_json["Error Message"][:500],
            )

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Make authenticated GET request to FMP (injects API key)."""
        request_params: dict[str, Any] = {"apikey": self._api_key}
        if params:
            request_params.update(params)
        return await self._request("GET", f"{self._base_url}{path}", params=request_params)

    async def get_analyst_estimates(self, symbol: str) -> list[dict[str, Any]]:
        """Get analyst estimates (revenue, EPS forecasts) for a symbol. Annual period."""
        result = await self._get("/analyst-estimates", params={"symbol": symbol, "period": "annual"})
        return cast(list[dict[str, Any]], result if isinstance(result, list) else [])

    async def get_price_target_consensus(self, symbol: str) -> list[dict[str, Any]]:
        """Get analyst price target consensus."""
        result = await self._get("/price-target-consensus", params={"symbol": symbol})
        return cast(list[dict[str, Any]], result if isinstance(result, list) else [])

    async def get_price_target_summary(self, symbol: str) -> list[dict[str, Any]]:
        """Get price target summary with counts and averages by time period."""
        result = await self._get("/price-target-summary", params={"symbol": symbol})
        return cast(list[dict[str, Any]], result if isinstance(result, list) else [])
```

**Step 2: Run existing tests**

Run: `uv run pytest tests/unit/test_fmp_client.py -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass

**Step 4: Commit**

```bash
git add src/ghostfolio_agent/clients/fmp.py
git commit -m "refactor: migrate FMPClient to BaseClient with soft error detection"
```

---

### Task 9: Shared `safe_fetch` Utility

**Files:**
- Create: `src/ghostfolio_agent/utils.py`
- Test: `tests/unit/test_utils.py`

**Step 1: Write the failing test**

```python
# tests/unit/test_utils.py
import pytest
from unittest.mock import AsyncMock, patch

from ghostfolio_agent.utils import safe_fetch


class TestSafeFetch:
    @pytest.mark.asyncio
    async def test_returns_result_on_success(self):
        coro = AsyncMock(return_value={"data": "ok"})
        result = await safe_fetch(coro(), "test_label")
        assert result == {"data": "ok"}

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        async def failing():
            raise RuntimeError("boom")

        result = await safe_fetch(failing(), "test_label")
        assert result is None

    @pytest.mark.asyncio
    async def test_logs_warning_on_failure(self):
        async def failing():
            raise ValueError("bad value")

        with patch("ghostfolio_agent.utils.logger") as mock_logger:
            result = await safe_fetch(failing(), "my_label")
            assert result is None
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert call_args[0][0] == "enrichment_fetch_failed"
            assert call_args[1]["label"] == "my_label"
            assert "bad value" in call_args[1]["error"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_utils.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ghostfolio_agent.utils'`

**Step 3: Write minimal implementation**

```python
# src/ghostfolio_agent/utils.py
"""Shared utilities for the Ghostfolio agent."""

from typing import Any, Coroutine

import structlog

logger = structlog.get_logger()


async def safe_fetch(coro: Coroutine[Any, Any, Any], label: str) -> Any | None:
    """Await a coroutine, returning None on any exception.

    Logs a warning with the label and error on failure.
    Used for optional enrichment data that shouldn't block the main response.
    """
    try:
        return await coro
    except Exception as exc:
        logger.warning("enrichment_fetch_failed", label=label, error=str(exc))
        return None
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_utils.py -v`
Expected: PASS — all 3 tests green

**Step 5: Commit**

```bash
git add src/ghostfolio_agent/utils.py tests/unit/test_utils.py
git commit -m "feat: add shared safe_fetch utility"
```

---

### Task 10: Tool-Layer Bug Fixes

This task fixes the concrete bugs in `stock_quote.py`, `paper_trade.py`, `risk_analysis.py`, and `morning_briefing.py`. Also replaces duplicated `_safe_fetch` in `holding_detail.py`, `conviction_score.py`, and `morning_briefing.py` with the shared `safe_fetch`.

**Files:**
- Modify: `src/ghostfolio_agent/tools/stock_quote.py`
- Modify: `src/ghostfolio_agent/tools/paper_trade.py`
- Modify: `src/ghostfolio_agent/tools/risk_analysis.py`
- Modify: `src/ghostfolio_agent/tools/morning_briefing.py`
- Modify: `src/ghostfolio_agent/tools/holding_detail.py`
- Modify: `src/ghostfolio_agent/tools/conviction_score.py`
- Test: existing tests in `tests/unit/`

**Step 1: Fix `stock_quote.py`**

Add structlog logger and replace silent catches with logged warnings:

```python
# At the top of stock_quote.py, add:
import structlog

logger = structlog.get_logger()
```

Replace the two `except Exception: pass` blocks:

First one (Ghostfolio symbol lookup fallback, around line 40):
```python
        except Exception as e:
            logger.warning("stock_quote_ghostfolio_price_failed", symbol=resolved_symbol, error=str(e))
```

Second one (Finnhub quote, around line 65):
```python
        except Exception as e:
            logger.warning("stock_quote_finnhub_failed", symbol=resolved_symbol, error=str(e))
```

**Step 2: Fix `paper_trade.py`**

Add structlog logger:
```python
# At top, add:
import structlog

logger = structlog.get_logger()
```

Fix bare `except:` in `_save_portfolio` (line ~38):
```python
    except Exception:
        os.unlink(tmp)
        raise
```

In the `show` command, replace the silent `except Exception: pass` for price fetch (around line ~123) with:
```python
                    except Exception as e:
                        logger.warning("paper_trade_price_fetch_failed", symbol=sym, error=str(e))
```

**Step 3: Fix `risk_analysis.py`**

Replace the single `asyncio.gather` with independent failure handling:

```python
        try:
            holdings_data = await client.get_portfolio_holdings()
        except Exception as e:
            logger.error("risk_analysis_failed", error=str(e))
            return "Sorry, I couldn't analyze your portfolio risk right now. Please try again later."

        details_data = None
        try:
            details_data = await client.get_portfolio_details()
        except Exception as e:
            logger.warning("risk_analysis_details_failed", error=str(e))
```

Then later where `details_data` is used, guard with `if details_data:`:
```python
        details = details_data if isinstance(details_data, dict) else {}
```
This line already handles `None` correctly since `isinstance(None, dict)` is `False`, so `details` becomes `{}` and the existing fallback to asset class grouping kicks in.

**Step 4: Fix `morning_briefing.py` macro cache**

In `_fetch_macro`, after all three safe_fetch calls, add a check before caching:

```python
    # After fetching fed, cpi, treasury via safe_fetch:
    data = {}
    if fed:
        data["fed_rate"] = fed[0].get("value", "N/A") if fed else "N/A"
    if cpi:
        data["cpi"] = cpi[0].get("value", "N/A") if cpi else "N/A"
    if treasury:
        data["treasury_10y"] = treasury[0].get("value", "N/A") if treasury else "N/A"

    # Only cache if we got at least some data
    if data:
        _macro_cache["data"] = data
        _macro_cache["fetched_at"] = datetime.now(timezone.utc)
    else:
        logger.warning("macro_fetch_all_failed", message="All macro data sources returned None")

    return data
```

**Step 5: Replace duplicated `_safe_fetch` in three tools**

In `holding_detail.py`, `conviction_score.py`, and `morning_briefing.py`:
- Remove the local `_safe_fetch` function definition
- Add import: `from ghostfolio_agent.utils import safe_fetch`
- Replace all calls from `_safe_fetch(...)` to `safe_fetch(...)`

**Step 6: Run existing tests for all modified tools**

Run: `uv run pytest tests/unit/test_stock_quote.py tests/unit/test_morning_briefing.py tests/unit/test_holding_detail.py tests/unit/test_conviction_score.py -v`
Expected: PASS (may need to update mocked imports if tests mock `_safe_fetch` directly)

**Step 7: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass

**Step 8: Commit**

```bash
git add src/ghostfolio_agent/tools/stock_quote.py src/ghostfolio_agent/tools/paper_trade.py src/ghostfolio_agent/tools/risk_analysis.py src/ghostfolio_agent/tools/morning_briefing.py src/ghostfolio_agent/tools/holding_detail.py src/ghostfolio_agent/tools/conviction_score.py
git commit -m "fix: add logging to tools, fix bare except, fix macro cache, deduplicate safe_fetch"
```

---

### Task 11: Verification Pipeline Hardening

**Files:**
- Modify: `src/ghostfolio_agent/verification/pipeline.py`
- Modify: `src/ghostfolio_agent/verification/numerical.py`
- Modify: `src/ghostfolio_agent/verification/hallucination.py`
- Modify: `src/ghostfolio_agent/verification/output_validation.py`
- Modify: `src/ghostfolio_agent/verification/domain_constraints.py`
- Test: `tests/unit/test_pipeline.py` (existing — verify no regressions)

**Step 1: Add structlog to all 5 verification files**

In each file, add at the top:
```python
import structlog

logger = structlog.get_logger()
```

**Step 2: Wrap verifier calls in `pipeline.py`**

Replace the direct calls with try/except blocks. For each verifier in `run_verification_pipeline`:

```python
    # Numerical (async)
    numerical_result = None
    if client:
        try:
            numerical_result = await verify_numerical_accuracy(response_text, client, tolerance=0.02)
            logger.info("verification_numerical_complete", confidence=numerical_result.confidence)
        except Exception as e:
            logger.error("verification_numerical_failed", error=str(e))

    # Hallucination (sync)
    hallucination_result = None
    try:
        hallucination_result = detect_hallucinations(response_text, tool_outputs)
        logger.info("verification_hallucination_complete", confidence=hallucination_result.confidence)
    except Exception as e:
        logger.error("verification_hallucination_failed", error=str(e))

    # Output validation (sync)
    output_result = None
    try:
        output_result = validate_output(response_text, tool_outputs)
        logger.info("verification_output_complete", confidence=output_result.confidence)
    except Exception as e:
        logger.error("verification_output_failed", error=str(e))

    # Domain constraints (sync)
    domain_result = None
    try:
        domain_result = check_domain_constraints(response_text, tool_outputs, portfolio_value)
        logger.info("verification_domain_complete", confidence=domain_result.confidence)
    except Exception as e:
        logger.error("verification_domain_failed", error=str(e))
```

Then adjust the confidence/issue aggregation to handle `None` results — skip any that are `None`.

**Step 3: Log the overall pipeline result**

At the end of the pipeline, before returning:
```python
    logger.info(
        "verification_pipeline_complete",
        overall_confidence=overall_confidence,
        total_issues=len(all_issues),
    )
```

**Step 4: Run existing pipeline tests**

Run: `uv run pytest tests/unit/test_pipeline.py tests/unit/test_hallucination.py tests/unit/test_output_validation.py tests/unit/test_domain_constraints.py -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass

**Step 6: Commit**

```bash
git add src/ghostfolio_agent/verification/
git commit -m "feat: add structured logging to verification pipeline, wrap verifiers in try/except"
```

---

### Task 12: FastAPI Error Handling

**Files:**
- Modify: `src/ghostfolio_agent/api/chat.py`
- Modify: `src/ghostfolio_agent/main.py`
- Test: existing tests + manual verification

**Step 1: Fix `/api/chat` to return proper HTTP errors**

In `chat.py`, the outer `except Exception` block currently returns HTTP 200 with error in body. Change to:

```python
    except Exception as e:
        logger.error("chat_endpoint_failed", error=str(e), session_id=request.session_id)
        raise HTTPException(status_code=500, detail="An internal error occurred. Please try again.")
```

Add import at top: `from fastapi import HTTPException`

**Step 2: Add structlog logger to `chat.py` if not present**

Verify `import structlog` and `logger = structlog.get_logger()` exist at module level (they already do based on audit).

**Step 3: Log request start in `/api/chat`**

At the beginning of the chat endpoint, add:
```python
    logger.info("chat_request", session_id=request.session_id, model=request.model)
```

**Step 4: Fix `/api/paper-portfolio` error handling**

Wrap the endpoint body:
```python
    try:
        portfolio = load_portfolio()
        # ... rest of existing code ...
    except Exception as e:
        logger.error("paper_portfolio_endpoint_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to load paper portfolio.")
```

**Step 5: Add global exception handler in `main.py`**

```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
```

**Step 6: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass (some tests may need updating if they check for 200 responses on error paths)

**Step 7: Commit**

```bash
git add src/ghostfolio_agent/api/chat.py src/ghostfolio_agent/main.py
git commit -m "fix: return HTTP 500 on errors instead of 200, add global exception handler"
```

---

### Task 13: Final Integration Test

**Step 1: Run full test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: All tests pass

**Step 2: Verify structlog output**

Run the app briefly to check logs look right:
```bash
LOG_FORMAT=console uv run python -c "
from ghostfolio_agent.logging_config import configure_logging
import structlog
configure_logging('debug', 'console')
logger = structlog.get_logger()
logger.info('test_event', key='value')
logger.warning('test_warning', error='something')
"
```
Expected: Colored console output with timestamps

**Step 3: Commit any remaining fixes**

If any test needed updating, commit those changes.

```bash
git add -A
git commit -m "chore: final integration fixes for error handling and observability"
```
