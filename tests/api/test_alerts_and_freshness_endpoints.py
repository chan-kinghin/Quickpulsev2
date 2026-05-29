"""Tests for /api/sync/freshness and /api/alerts/* endpoints."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.routers.alerts import router as alerts_router
from src.api.routers.auth import create_access_token, router as auth_router
from src.api.routers.sync import router as sync_router


@pytest.fixture
def mock_cache_reader():
    reader = MagicMock()
    reader.table_freshness = AsyncMock(return_value=[])
    reader.get_over_pick_alerts = AsyncMock(
        return_value={"alerts": [], "skipped_incomplete": 0}
    )
    reader.get_over_ship_alerts = AsyncMock(
        return_value={"alerts": [], "skipped_incomplete": 0}
    )
    return reader


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.sync = MagicMock()
    config.sync.auto_sync = MagicMock()
    # 07/12/18 → max gap 13h (18:00→07:00) → ~19.5h staleness threshold
    config.sync.auto_sync.schedule = ["07:00", "12:00", "18:00"]
    return config


@pytest.fixture
def app_with_alerts(mock_cache_reader, mock_config):
    app = FastAPI()
    app.state.cache_reader = mock_cache_reader
    app.state.config = mock_config
    app.include_router(auth_router)
    app.include_router(sync_router)
    app.include_router(alerts_router)
    return app


@pytest.fixture
def auth_headers():
    token = create_access_token(data={"sub": "testuser"})
    return {"Authorization": f"Bearer {token}"}


async def _get(app, path, headers=None):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(path, headers=headers or {})


class TestFreshnessEndpoint:
    @pytest.mark.asyncio
    async def test_classifies_fresh_stale_empty(
        self, app_with_alerts, auth_headers, mock_cache_reader
    ):
        fresh = datetime.utcnow() - timedelta(hours=1)
        stale = datetime.utcnow() - timedelta(days=3)
        mock_cache_reader.table_freshness.return_value = [
            {"table": "cached_sales_orders", "last_synced_at": fresh, "row_count": 100},
            {"table": "cached_sales_delivery", "last_synced_at": stale, "row_count": 50},
            {"table": "cached_production_bom", "last_synced_at": None, "row_count": 0},
        ]

        resp = await _get(app_with_alerts, "/api/sync/freshness", auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        verdicts = {t["table"]: t["verdict"] for t in data["tables"]}
        assert verdicts["cached_sales_orders"] == "fresh"
        assert verdicts["cached_sales_delivery"] == "stale"
        assert verdicts["cached_production_bom"] == "empty"
        assert data["stale_count"] == 2
        assert data["threshold_hours"] == 19.5
        # oldest = worst rated table (empty has no age and is excluded from oldest)
        assert data["oldest"]["table"] == "cached_sales_delivery"
        # Chinese label surfaced
        assert verdicts and any(t["label"] == "销售出库单" for t in data["tables"])

    @pytest.mark.asyncio
    async def test_requires_auth(self, app_with_alerts):
        resp = await _get(app_with_alerts, "/api/sync/freshness")
        assert resp.status_code == 401


class TestOverPickEndpoint:
    @pytest.mark.asyncio
    async def test_passthrough(self, app_with_alerts, auth_headers, mock_cache_reader):
        mock_cache_reader.get_over_pick_alerts.return_value = {
            "alerts": [
                {
                    "mto_number": "AK1",
                    "material_code": "05.01.001",
                    "app_qty": 0,
                    "actual_qty": 50,
                    "over_amount": 50,
                    "customer_name": "刀刀",
                    "delivery_date": "2026-03-05T00:00:00",
                    "material_name": "静电膜",
                    "severe": True,
                }
            ],
            "skipped_incomplete": 2,
        }
        resp = await _get(app_with_alerts, "/api/alerts/over-pick", auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped_incomplete"] == 2
        assert data["alerts"][0]["severe"] is True

    @pytest.mark.asyncio
    async def test_query_failure_returns_500(
        self, app_with_alerts, auth_headers, mock_cache_reader
    ):
        mock_cache_reader.get_over_pick_alerts.side_effect = RuntimeError("db down")
        resp = await _get(app_with_alerts, "/api/alerts/over-pick", auth_headers)
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_requires_auth(self, app_with_alerts):
        resp = await _get(app_with_alerts, "/api/alerts/over-pick")
        assert resp.status_code == 401


class TestOverShipEndpoint:
    @pytest.mark.asyncio
    async def test_passthrough(self, app_with_alerts, auth_headers, mock_cache_reader):
        mock_cache_reader.get_over_ship_alerts.return_value = {
            "alerts": [
                {
                    "mto_number": "AK2",
                    "material_code": "07.01.001",
                    "order_qty": 100,
                    "shipped_qty": 120,
                    "over_amount": 20,
                    "customer_name": "MARES",
                    "delivery_date": "2026-03-05T00:00:00",
                    "material_name": "蛙鞋",
                }
            ],
            "skipped_incomplete": 0,
        }
        resp = await _get(app_with_alerts, "/api/alerts/over-ship", auth_headers)
        assert resp.status_code == 200
        assert resp.json()["alerts"][0]["over_amount"] == 20

    @pytest.mark.asyncio
    async def test_requires_auth(self, app_with_alerts):
        resp = await _get(app_with_alerts, "/api/alerts/over-ship")
        assert resp.status_code == 401
