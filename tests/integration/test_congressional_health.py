"""Integration test — live Congressional Trading API health check.

Skipped when CONGRESSIONAL_API_URL env var is not set.
Run manually: CONGRESSIONAL_API_URL=http://... uv run pytest tests/integration/ -v
"""

import os

import httpx
import pytest

CONGRESSIONAL_API_URL = os.environ.get("CONGRESSIONAL_API_URL", "")

pytestmark = pytest.mark.skipif(
    not CONGRESSIONAL_API_URL,
    reason="CONGRESSIONAL_API_URL not set — skipping live integration tests",
)


@pytest.mark.asyncio
async def test_health_endpoint_returns_healthy():
    """Real HTTP call to /api/v1/health — verifies the service is up."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{CONGRESSIONAL_API_URL}/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
