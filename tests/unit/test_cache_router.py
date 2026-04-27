"""Tests for src/api/routers/cache.py"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.routers.cache import router
from src.api.routers.auth import create_access_token


def _build_app():
    app = FastAPI()
    app.include_router(router)
    return app


def _auth_header():
    token = create_access_token(data={"sub": "testadmin"})
    return {"Authorization": f"Bearer {token}"}


def _mock_mto_handler():
    handler = MagicMock()
    handler.get_cache_stats.return_value = {"memory_size": 10, "hit_rate": 0.85}
    handler.get_query_stats.return_value = {
        "total_queries": 200,
        "total_unique_mtos": 50,
    }
    handler.reset_stats = MagicMock()
    handler.clear_memory_cache = AsyncMock(return_value=5)
    handler.invalidate_mto = AsyncMock(return_value=True)
    handler.get_hot_mtos.return_value = ["AK2510034", "AK2510035"]
    handler.warm_cache = AsyncMock(
        return_value={"status": "done", "warmed": 2, "failed": 0}
    )
    return handler


@pytest.fixture()
def app_with_state():
    app = _build_app()
    mock_handler = _mock_mto_handler()
    mock_db = MagicMock()
    mock_db.execute_read = AsyncMock(return_value=[])
    app.state.mto_handler = mock_handler
    app.state.db = mock_db
    return app, mock_handler, mock_db


# ---------------------------------------------------------------------------
# GET /api/cache/stats
# ---------------------------------------------------------------------------

class TestCacheStats:
    @pytest.mark.asyncio
    async def test_returns_stats_with_query_stats(self, app_with_state):
        app, handler, _ = app_with_state
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/cache/stats", headers=_auth_header())

        assert resp.status_code == 200
        body = resp.json()
        assert body["memory_size"] == 10
        assert body["hit_rate"] == 0.85
        assert body["query_stats"]["total_queries"] == 200

    @pytest.mark.asyncio
    async def test_requires_auth(self, app_with_state):
        app, _, _ = app_with_state
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/cache/stats")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /api/cache/clear
# ---------------------------------------------------------------------------

class TestCacheClear:
    @pytest.mark.asyncio
    async def test_clear_returns_entries_cleared(self, app_with_state):
        app, handler, _ = app_with_state
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/cache/clear", headers=_auth_header())

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "cleared"
        assert body["entries_cleared"] == 5
        handler.clear_memory_cache.assert_called_once()


# ---------------------------------------------------------------------------
# POST /api/cache/reset-stats
# ---------------------------------------------------------------------------

class TestResetStats:
    @pytest.mark.asyncio
    async def test_reset_returns_status(self, app_with_state):
        app, handler, _ = app_with_state
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/cache/reset-stats", headers=_auth_header())

        assert resp.status_code == 200
        assert resp.json()["status"] == "stats_reset"
        handler.reset_stats.assert_called_once()


# ---------------------------------------------------------------------------
# DELETE /api/cache/{mto_number}
# ---------------------------------------------------------------------------

class TestInvalidateMTO:
    @pytest.mark.asyncio
    async def test_invalidate_existing(self, app_with_state):
        app, handler, _ = app_with_state
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.delete("/api/cache/AK2510034", headers=_auth_header())

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "invalidated"
        assert body["mto_number"] == "AK2510034"

    @pytest.mark.asyncio
    async def test_invalidate_not_found(self, app_with_state):
        app, handler, _ = app_with_state
        handler.invalidate_mto = AsyncMock(return_value=False)

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.delete("/api/cache/NONEXIST", headers=_auth_header())

        assert resp.status_code == 200
        assert resp.json()["status"] == "not_found"


# ---------------------------------------------------------------------------
# POST /api/cache/warm — "recent_synced" strategy
# ---------------------------------------------------------------------------

class TestWarmCacheRecentSynced:
    @pytest.mark.asyncio
    async def test_warm_recent_synced(self, app_with_state):
        app, handler, mock_db = app_with_state
        mock_db.execute_read = AsyncMock(
            return_value=[("AK2510034",), ("AK2510035",)]
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/cache/warm?count=2&use_hot=false", headers=_auth_header()
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] == "recent_synced"
        assert body["warmed"] == 2

    @pytest.mark.asyncio
    async def test_warm_no_mtos_found(self, app_with_state):
        app, handler, mock_db = app_with_state
        mock_db.execute_read = AsyncMock(return_value=[])
        handler.warm_cache = AsyncMock()  # should not be called

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/cache/warm?use_hot=false", headers=_auth_header()
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "no_mtos_found"
        handler.warm_cache.assert_not_called()


# ---------------------------------------------------------------------------
# POST /api/cache/warm — "hot" strategy
# ---------------------------------------------------------------------------

class TestWarmCacheHot:
    @pytest.mark.asyncio
    async def test_warm_hot_mtos(self, app_with_state):
        app, handler, _ = app_with_state
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/cache/warm?use_hot=true&count=2", headers=_auth_header()
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] == "query_history"
        handler.get_hot_mtos.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_warm_hot_empty(self, app_with_state):
        app, handler, _ = app_with_state
        handler.get_hot_mtos.return_value = []

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/cache/warm?use_hot=true", headers=_auth_header()
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "no_mtos_found"


# ---------------------------------------------------------------------------
# GET /api/cache/hot-mtos
# ---------------------------------------------------------------------------

class TestHotMTOs:
    @pytest.mark.asyncio
    async def test_returns_hot_list(self, app_with_state):
        app, handler, _ = app_with_state
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/cache/hot-mtos?top_n=10", headers=_auth_header()
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["hot_mtos"] == ["AK2510034", "AK2510035"]
        assert body["total_queries"] == 200
