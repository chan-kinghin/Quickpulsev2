"""Tests for X-API-Version header middleware."""

import httpx
import pytest
from fastapi import FastAPI
from starlette.requests import Request

from src.api.middleware.rate_limit import setup_rate_limiting
from src.api.routers.auth import router as auth_router


@pytest.fixture
def app_with_version_middleware():
    """Create test app with the same version middleware as main.py."""
    app = FastAPI()
    setup_rate_limiting(app)

    @app.middleware("http")
    async def add_api_version_header(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["X-API-Version"] = "1"
        return response

    app.include_router(auth_router)

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/")
    async def root():
        return {"message": "root"}

    return app


class TestAPIVersionHeader:
    """Tests for X-API-Version middleware."""

    @pytest.mark.asyncio
    async def test_api_path_has_version_header(self, app_with_version_middleware):
        """Test /api/* paths include X-API-Version: 1."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_version_middleware),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/auth/verify")
        # Will be 401 (no auth) but header should still be present
        assert response.headers.get("x-api-version") == "1"

    @pytest.mark.asyncio
    async def test_api_auth_token_has_version_header(self, app_with_version_middleware):
        """Test POST /api/auth/token includes X-API-Version."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_version_middleware),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/auth/token",
                data={"username": "test", "password": "quickpulse"},
            )
        assert response.status_code == 200
        assert response.headers.get("x-api-version") == "1"

    @pytest.mark.asyncio
    async def test_health_no_version_header(self, app_with_version_middleware):
        """Test /health does NOT have X-API-Version header."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_version_middleware),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")
        assert response.status_code == 200
        assert "x-api-version" not in response.headers

    @pytest.mark.asyncio
    async def test_root_no_version_header(self, app_with_version_middleware):
        """Test / does NOT have X-API-Version header."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_version_middleware),
            base_url="http://test",
        ) as client:
            response = await client.get("/")
        assert response.status_code == 200
        assert "x-api-version" not in response.headers
