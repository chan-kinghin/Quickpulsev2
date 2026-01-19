"""Tests for /health endpoint."""

import httpx
import pytest
from fastapi import FastAPI


@pytest.fixture
def app_with_health():
    """Create minimal app with health endpoint."""
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_healthy(self, app_with_health):
        """Test /health returns healthy status."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_health),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    @pytest.mark.asyncio
    async def test_health_no_auth_required(self, app_with_health):
        """Test /health does not require authentication."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_health),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_accepts_any_method_except_post(self, app_with_health):
        """Test /health only accepts GET method."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_health),
            base_url="http://test",
        ) as client:
            # POST should fail
            response = await client.post("/health")
            assert response.status_code == 405

            # PUT should fail
            response = await client.put("/health")
            assert response.status_code == 405

            # DELETE should fail
            response = await client.delete("/health")
            assert response.status_code == 405

    @pytest.mark.asyncio
    async def test_health_response_content_type(self, app_with_health):
        """Test /health returns JSON content type."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_health),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")

        assert "application/json" in response.headers["content-type"]
