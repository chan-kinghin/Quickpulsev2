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
        return_value={"alerts": [], "skipped_incomplete": 0, "total_count": 0}
    )
    reader.get_over_ship_alerts = AsyncMock(
        return_value={"alerts": [], "skipped_incomplete": 0, "total_count": 0}
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


def _over_pick_alert(mto, material="05.01.001", severe=True):
    return {
        "mto_number": mto,
        "material_code": material,
        "app_qty": 0,
        "actual_qty": 50,
        "over_amount": 50,
        "customer_name": "刀刀",
        "delivery_date": "2026-03-05T00:00:00",
        "material_name": "静电膜",
        "severe": severe,
    }


def _over_ship_alert(mto, material="07.01.001"):
    return {
        "mto_number": mto,
        "material_code": material,
        "order_qty": 100,
        "shipped_qty": 120,
        "over_amount": 20,
        "customer_name": "MARES",
        "delivery_date": "2026-03-05T00:00:00",
        "material_name": "蛙鞋",
    }


class TestOverPickEndpoint:
    @pytest.mark.asyncio
    async def test_passthrough(self, app_with_alerts, auth_headers, mock_cache_reader):
        mock_cache_reader.get_over_pick_alerts.return_value = {
            "alerts": [_over_pick_alert("AK1")],
            "skipped_incomplete": 2,
            "total_count": 5,
        }
        resp = await _get(app_with_alerts, "/api/alerts/over-pick", auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped_incomplete"] == 2
        assert data["alerts"][0]["severe"] is True
        # No samples present → nothing excluded, but the count is always reported.
        assert data["excluded_sample_count"] == 0
        # total_count passes through the sample filter unchanged.
        assert data["total_count"] == 5

    @pytest.mark.asyncio
    async def test_samples_excluded_by_default(
        self, app_with_alerts, auth_headers, mock_cache_reader
    ):
        """AY/DY (order_type=Y) sample rows are noise — dropped by default."""
        mock_cache_reader.get_over_pick_alerts.return_value = {
            "alerts": [
                _over_pick_alert("AK2510034"),  # 完整订单 — keep
                _over_pick_alert("AY2510001"),  # 样品单 (export) — drop
                _over_pick_alert("DY251002S"),  # 样品单 (domestic) — drop
                _over_pick_alert("AK2510034-1"),  # sub-order, not a sample — keep
            ],
            "skipped_incomplete": 0,
        }
        resp = await _get(app_with_alerts, "/api/alerts/over-pick", auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        kept = {a["mto_number"] for a in data["alerts"]}
        assert kept == {"AK2510034", "AK2510034-1"}
        assert data["excluded_sample_count"] == 2

    @pytest.mark.asyncio
    async def test_include_samples_retains_and_still_reports_count(
        self, app_with_alerts, auth_headers, mock_cache_reader
    ):
        mock_cache_reader.get_over_pick_alerts.return_value = {
            "alerts": [
                _over_pick_alert("AK2510034"),
                _over_pick_alert("AY2510001"),
                _over_pick_alert("DY251002S"),
            ],
            "skipped_incomplete": 0,
        }
        resp = await _get(
            app_with_alerts, "/api/alerts/over-pick?include_samples=true", auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["alerts"]) == 3  # nothing dropped
        # Count is still reported so the filter never becomes a silent no-op.
        assert data["excluded_sample_count"] == 2

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
            "alerts": [_over_ship_alert("AK2")],
            "skipped_incomplete": 0,
            "total_count": 3,
        }
        resp = await _get(app_with_alerts, "/api/alerts/over-ship", auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["alerts"][0]["over_amount"] == 20
        assert data["excluded_sample_count"] == 0
        # total_count passes through the sample filter unchanged.
        assert data["total_count"] == 3

    @pytest.mark.asyncio
    async def test_samples_excluded_by_default(
        self, app_with_alerts, auth_headers, mock_cache_reader
    ):
        mock_cache_reader.get_over_ship_alerts.return_value = {
            "alerts": [
                _over_ship_alert("AK2510034"),  # keep
                _over_ship_alert("AY2510001"),  # 样品单 — drop
                _over_ship_alert("DY251002S"),  # 样品单 — drop
            ],
            "skipped_incomplete": 0,
        }
        resp = await _get(app_with_alerts, "/api/alerts/over-ship", auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        kept = {a["mto_number"] for a in data["alerts"]}
        assert kept == {"AK2510034"}
        assert data["excluded_sample_count"] == 2

    @pytest.mark.asyncio
    async def test_include_samples_retains_and_still_reports_count(
        self, app_with_alerts, auth_headers, mock_cache_reader
    ):
        mock_cache_reader.get_over_ship_alerts.return_value = {
            "alerts": [
                _over_ship_alert("AK2510034"),
                _over_ship_alert("AY2510001"),
            ],
            "skipped_incomplete": 0,
        }
        resp = await _get(
            app_with_alerts, "/api/alerts/over-ship?include_samples=true", auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["alerts"]) == 2
        assert data["excluded_sample_count"] == 1

    @pytest.mark.asyncio
    async def test_requires_auth(self, app_with_alerts):
        resp = await _get(app_with_alerts, "/api/alerts/over-ship")
        assert resp.status_code == 401
