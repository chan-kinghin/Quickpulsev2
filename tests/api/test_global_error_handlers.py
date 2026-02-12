"""Tests for global exception handlers defined in main.py."""

import httpx
import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.api.middleware.rate_limit import setup_rate_limiting
from src.exceptions import KingdeeConnectionError, QuickPulseError


@pytest.fixture
def app_with_error_handlers():
    """Create a minimal test app with the same exception handlers as main.py."""
    app = FastAPI()
    setup_rate_limiting(app)

    # Register the same handlers as main.py
    @app.exception_handler(KingdeeConnectionError)
    async def kingdee_connection_handler(request: Request, exc: KingdeeConnectionError):
        return JSONResponse(
            status_code=502,
            content={"detail": "ERP system unavailable", "error_code": "erp_unavailable"},
        )

    @app.exception_handler(QuickPulseError)
    async def quickpulse_error_handler(request: Request, exc: QuickPulseError):
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error_code": "internal_error"},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error_code": "internal_error"},
        )

    # Add test routes that raise specific exceptions
    @app.get("/test/kingdee-error")
    async def raise_kingdee_error():
        raise KingdeeConnectionError("Connection refused")

    @app.get("/test/quickpulse-error")
    async def raise_quickpulse_error():
        raise QuickPulseError("Something went wrong")

    @app.get("/test/generic-error")
    async def raise_generic_error():
        raise RuntimeError("Unexpected failure")

    @app.get("/test/ok")
    async def ok_route():
        return {"status": "ok"}

    return app


class TestGlobalExceptionHandlers:
    """Tests for global exception handlers."""

    @pytest.mark.asyncio
    async def test_kingdee_connection_error_returns_502(self, app_with_error_handlers):
        """Test KingdeeConnectionError returns 502 with proper body."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_error_handlers),
            base_url="http://test",
        ) as client:
            response = await client.get("/test/kingdee-error")
        assert response.status_code == 502
        data = response.json()
        assert data["detail"] == "ERP system unavailable"
        assert data["error_code"] == "erp_unavailable"

    @pytest.mark.asyncio
    async def test_quickpulse_error_returns_500(self, app_with_error_handlers):
        """Test QuickPulseError returns 500 with proper body."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_error_handlers),
            base_url="http://test",
        ) as client:
            response = await client.get("/test/quickpulse-error")
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Internal server error"
        assert data["error_code"] == "internal_error"

    @pytest.mark.asyncio
    async def test_kingdee_error_no_traceback(self, app_with_error_handlers):
        """Test that KingdeeConnectionError response does not contain traceback."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_error_handlers),
            base_url="http://test",
        ) as client:
            response = await client.get("/test/kingdee-error")
        body = response.text
        assert "Traceback" not in body
        assert "Connection refused" not in body

    @pytest.mark.asyncio
    async def test_quickpulse_error_no_traceback(self, app_with_error_handlers):
        """Test that QuickPulseError response does not contain traceback."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_error_handlers),
            base_url="http://test",
        ) as client:
            response = await client.get("/test/quickpulse-error")
        body = response.text
        assert "Traceback" not in body
        assert "Something went wrong" not in body

    @pytest.mark.asyncio
    async def test_normal_route_not_affected(self, app_with_error_handlers):
        """Test that normal routes still work with handlers registered."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_error_handlers),
            base_url="http://test",
        ) as client:
            response = await client.get("/test/ok")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_kingdee_error_is_json(self, app_with_error_handlers):
        """Test that error response is proper JSON."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_error_handlers),
            base_url="http://test",
        ) as client:
            response = await client.get("/test/kingdee-error")
        assert "application/json" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_generic_exception_returns_500(self, app_with_error_handlers):
        """Test unhandled RuntimeError returns 500 with no traceback leakage."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(
                app=app_with_error_handlers, raise_app_exceptions=False
            ),
            base_url="http://test",
        ) as client:
            response = await client.get("/test/generic-error")
        assert response.status_code == 500
        data = response.json()
        assert data["detail"] == "Internal server error"
        assert data["error_code"] == "internal_error"
        assert "Unexpected failure" not in response.text
        assert "Traceback" not in response.text
