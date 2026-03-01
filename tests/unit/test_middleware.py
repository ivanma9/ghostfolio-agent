import pytest
from unittest.mock import patch
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
        assert data["request_id"]
        assert len(data["request_id"]) == 36  # UUID format

    def test_returns_request_id_header(self, client):
        response = client.get("/test")
        assert "x-request-id" in response.headers
        assert len(response.headers["x-request-id"]) == 36

    def test_logs_request(self, client):
        with patch("ghostfolio_agent.api.middleware.logger") as mock_logger:
            response = client.get("/test")
            assert response.status_code == 200
            assert mock_logger.info.call_count == 1
