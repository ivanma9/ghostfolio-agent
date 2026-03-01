"""Tests for custom API client exception hierarchy."""
import pytest
from ghostfolio_agent.clients.exceptions import (
    APIError,
    AuthenticationError,
    RateLimitError,
    TransientError,
)


def test_api_error_is_exception():
    err = APIError(
        client_name="TestClient",
        status_code=500,
        url="https://example.com/api",
        body="Internal Server Error",
    )
    assert isinstance(err, Exception)
    assert err.client_name == "TestClient"
    assert err.status_code == 500
    assert err.url == "https://example.com/api"
    assert err.body == "Internal Server Error"


def test_rate_limit_error_is_api_error():
    err = RateLimitError(
        client_name="Finnhub",
        status_code=429,
        url="https://finnhub.io/api/v1/quote",
        body="Too Many Requests",
    )
    assert isinstance(err, APIError)
    assert isinstance(err, Exception)
    assert err.status_code == 429


def test_authentication_error_is_api_error():
    err = AuthenticationError(
        client_name="FMP",
        status_code=401,
        url="https://financialmodelingprep.com/stable/analyst-estimates",
        body="Unauthorized",
    )
    assert isinstance(err, APIError)
    assert isinstance(err, Exception)
    assert err.status_code == 401


def test_transient_error_is_api_error():
    err = TransientError(
        client_name="AlphaVantage",
        status_code=503,
        url="https://www.alphavantage.co/query",
        body="Service Unavailable",
    )
    assert isinstance(err, APIError)
    assert isinstance(err, Exception)
    assert err.status_code == 503


def test_api_error_str():
    err = APIError(
        client_name="Ghostfolio",
        status_code=404,
        url="https://ghostfolio.example.com/api/v1/portfolio",
        body="Not Found",
    )
    msg = str(err)
    assert "Ghostfolio" in msg
    assert "404" in msg
    assert "https://ghostfolio.example.com/api/v1/portfolio" in msg


def test_api_error_body_truncated_to_500():
    long_body = "x" * 1000
    err = APIError(
        client_name="TestClient",
        status_code=500,
        url="https://example.com",
        body=long_body,
    )
    # body attribute stores full body
    assert err.body == long_body
    # str representation should only include first 500 chars of body
    msg = str(err)
    assert "x" * 500 in msg
    assert "x" * 501 not in msg
