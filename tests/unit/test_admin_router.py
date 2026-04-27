"""Tests for src/api/routers/admin.py"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from src.api.routers.admin import router
from src.api.routers.auth import create_access_token


def _build_app():
    """Create a minimal FastAPI app with the admin router mounted."""
    app = FastAPI()
    app.include_router(router)
    return app


def _auth_header():
    """Return a valid Authorization header dict."""
    token = create_access_token(data={"sub": "testadmin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def app_with_db():
    app = _build_app()
    mock_db = MagicMock()
    mock_db.execute_read = AsyncMock(return_value=[])
    app.state.db = mock_db
    return app, mock_db


# ---------------------------------------------------------------------------
# /api/admin/usage/summary
# ---------------------------------------------------------------------------

class TestUsageSummary:
    """Tests for the usage summary endpoint."""

    @pytest.mark.asyncio
    async def test_returns_correct_structure(self, app_with_db):
        app, mock_db = app_with_db
        mock_db.execute_read = AsyncMock(
            return_value=[(42, 5, 123.456, "/api/mto/X", "10.0.0.1")]
        )

        with patch("src.api.routers.admin.lookup_ip_display", return_value="深圳 电信"):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/admin/usage/summary", headers=_auth_header())

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_requests"] == 42
        assert body["unique_ips"] == 5
        assert body["avg_response_time_ms"] == 123.46
        assert body["top_endpoint"] == "/api/mto/X"
        assert body["top_location"] == "深圳 电信"
        assert body["period_hours"] == 24

    @pytest.mark.asyncio
    async def test_empty_db_returns_zeros(self, app_with_db):
        app, mock_db = app_with_db
        mock_db.execute_read = AsyncMock(return_value=[(0, 0, None, None, None)])

        with patch("src.api.routers.admin.lookup_ip_display", return_value="未知"):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/admin/usage/summary", headers=_auth_header())

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_requests"] == 0
        assert body["avg_response_time_ms"] == 0.0

    @pytest.mark.asyncio
    async def test_custom_hours_param(self, app_with_db):
        app, mock_db = app_with_db
        mock_db.execute_read = AsyncMock(
            return_value=[(1, 1, 10.0, "/", "127.0.0.1")]
        )

        with patch("src.api.routers.admin.lookup_ip_display", return_value="本地"):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/admin/usage/summary?hours=48", headers=_auth_header()
                )

        assert resp.status_code == 200
        assert resp.json()["period_hours"] == 48

    @pytest.mark.asyncio
    async def test_requires_auth(self, app_with_db):
        app, _ = app_with_db
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/admin/usage/summary")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# /api/admin/usage/recent  (pagination)
# ---------------------------------------------------------------------------

class TestUsageRecent:
    """Tests for the paginated recent logs endpoint."""

    @pytest.mark.asyncio
    async def test_returns_items_and_total(self, app_with_db):
        app, mock_db = app_with_db
        mock_db.execute_read = AsyncMock(
            side_effect=[
                [(100,)],  # count query
                [
                    ("2026-04-06 12:00", "1.2.3.4", "GET", "/api/mto/X", 200, 15.0),
                ],
            ]
        )

        with patch("src.api.routers.admin.lookup_ip_display", return_value="深圳"):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/admin/usage/recent?limit=10&offset=0", headers=_auth_header()
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 100
        assert len(body["items"]) == 1
        assert body["items"][0]["ip_address"] == "1.2.3.4"
        assert body["items"][0]["location"] == "深圳"

    @pytest.mark.asyncio
    async def test_empty_logs(self, app_with_db):
        app, mock_db = app_with_db
        mock_db.execute_read = AsyncMock(side_effect=[[(0,)], []])

        with patch("src.api.routers.admin.lookup_ip_display", return_value="未知"):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/admin/usage/recent", headers=_auth_header())

        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# /api/admin/usage/by-ip
# ---------------------------------------------------------------------------

class TestUsageByIP:
    """Tests for the by-ip endpoint with GeoIP lookup mocking."""

    @pytest.mark.asyncio
    async def test_returns_list_with_locations(self, app_with_db):
        app, mock_db = app_with_db
        mock_db.execute_read = AsyncMock(
            return_value=[
                ("10.0.0.1", 50, "2026-04-06 10:00", "/api/mto/X"),
                ("10.0.0.2", 30, "2026-04-06 09:00", "/api/sync/status"),
            ]
        )

        with patch(
            "src.api.routers.admin.batch_lookup_ip_displays",
            return_value={"10.0.0.1": "深圳 电信", "10.0.0.2": "广州 联通"},
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/admin/usage/by-ip", headers=_auth_header())

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["ip_address"] == "10.0.0.1"
        assert body[0]["location"] == "深圳 电信"
        assert body[1]["location"] == "广州 联通"


# ---------------------------------------------------------------------------
# /api/admin/usage/timeline
# ---------------------------------------------------------------------------

class TestUsageTimeline:
    """Tests for the timeline endpoint."""

    @pytest.mark.asyncio
    async def test_returns_buckets(self, app_with_db):
        app, mock_db = app_with_db
        mock_db.execute_read = AsyncMock(
            return_value=[
                ("2026-04-06 10:00", 15),
                ("2026-04-06 11:00", 20),
            ]
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/admin/usage/timeline", headers=_auth_header())

        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2
        assert body[0]["bucket_start"] == "2026-04-06 10:00"
        assert body[0]["request_count"] == 15
