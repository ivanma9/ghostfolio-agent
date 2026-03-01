"""Custom exception hierarchy for API clients."""


class APIError(Exception):
    """Base exception for all API client errors."""

    def __init__(self, client_name: str, status_code: int, url: str, body: str) -> None:
        self.client_name = client_name
        self.status_code = status_code
        self.url = url
        self.body = body
        super().__init__(f"{client_name} API error: {status_code} for {url} \u2014 {body[:500]}")


class RateLimitError(APIError):
    """Rate limit exceeded (HTTP 429 or soft rate limit in response body)."""

    pass


class AuthenticationError(APIError):
    """Authentication failed (HTTP 401/403)."""

    pass


class TransientError(APIError):
    """Transient server error (HTTP 5xx, timeouts). Safe to retry."""

    pass
