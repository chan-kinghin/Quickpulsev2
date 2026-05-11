"""Tests for /health sync staleness reporting.

Background: the migration-008 incident (2026-03-20 → 2026-05-11 on legacy dev
DBs) was bad specifically because nobody noticed for 50+ days. /health now
surfaces last_success_age_seconds + a stale flag so probers can alert.
"""

from datetime import datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse


def _fake_db_factory(rows_by_query=None):
    """Build a stub db.execute_read that returns canned rows per query prefix."""
    rows_by_query = rows_by_query or {}

    class _DB:
        async def execute_read(self, query, *args, **kwargs):
            for prefix, rows in rows_by_query.items():
                if query.lstrip().startswith(prefix):
                    return rows
            return []

    return _DB()


def _make_app(db):
    """Minimal app exposing just the /health handler from src.main (copied logic)."""
    app = FastAPI()
    app.state.db = db

    @app.get("/health")
    async def health():
        components = {}
        try:
            await app.state.db.execute_read("SELECT 1")
            components["database"] = "ok"
        except Exception as e:
            components["database"] = f"error: {e}"

        sync_info = {"status": "ok"}
        try:
            rows = await app.state.db.execute_read(
                "SELECT started_at, status, error_message FROM sync_history "
                "WHERE status = 'success' ORDER BY started_at DESC LIMIT 1"
            )
            last_failed = await app.state.db.execute_read(
                "SELECT started_at, error_message FROM sync_history "
                "WHERE status = 'error' ORDER BY started_at DESC LIMIT 1"
            )
            if rows:
                ts = rows[0][0]
                try:
                    last_success_dt = datetime.fromisoformat(ts)
                    if last_success_dt.tzinfo is not None:
                        last_success_dt = last_success_dt.replace(tzinfo=None)
                    age = (datetime.now() - last_success_dt).total_seconds()
                except (ValueError, AttributeError):
                    age = None
                if age is not None:
                    sync_info["last_success_at"] = ts
                    sync_info["last_success_age_seconds"] = int(age)
                    if age > 86_400:
                        sync_info["status"] = f"stale: last success {int(age // 3600)}h ago"
            else:
                sync_info["status"] = "never_succeeded"
            if last_failed:
                sync_info["last_error_at"] = last_failed[0][0]
                err = last_failed[0][1] or ""
                sync_info["last_error_message"] = err[:200]
        except Exception as e:
            sync_info["status"] = f"probe_error: {e}"
        components["sync"] = sync_info["status"]

        overall = "healthy" if all(v == "ok" for v in components.values()) else "unhealthy"
        payload = {"status": overall, "components": components, "sync": sync_info}
        if overall != "healthy":
            return JSONResponse(status_code=503, content=payload)
        return payload

    return app


async def _get_health(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get("/health")


@pytest.mark.asyncio
async def test_health_reports_fresh_sync_as_ok():
    """Sync within the last hour → healthy + age < 3600s."""
    recent = (datetime.now() - timedelta(minutes=30)).isoformat()
    db = _fake_db_factory({
        "SELECT 1": [],
        "SELECT started_at, status": [(recent, "success", "")],
        "SELECT started_at, error_message": [],
    })
    response = await _get_health(_make_app(db))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["sync"]["status"] == "ok"
    assert 0 <= body["sync"]["last_success_age_seconds"] < 3600
    assert body["sync"]["last_success_at"] == recent


@pytest.mark.asyncio
async def test_health_reports_stale_sync_as_unhealthy():
    """Sync >24h old → unhealthy with explanatory status. This is the case
    the migration-008 incident SHOULD have triggered but didn't."""
    stale = (datetime.now() - timedelta(days=3, hours=5)).isoformat()
    db = _fake_db_factory({
        "SELECT 1": [],
        "SELECT started_at, status": [(stale, "success", "")],
        "SELECT started_at, error_message": [
            (
                (datetime.now() - timedelta(hours=1)).isoformat(),
                "Sync aborted: 5/5 chunks failed (ON CONFLICT clause does not match)",
            )
        ],
    })
    response = await _get_health(_make_app(db))
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert "stale" in body["sync"]["status"]
    assert "77h ago" in body["sync"]["status"] or "76h ago" in body["sync"]["status"]
    # Last error surfaces too so the operator can read the root cause directly.
    assert "ON CONFLICT" in body["sync"]["last_error_message"]


@pytest.mark.asyncio
async def test_health_reports_never_synced():
    """Brand-new DB with no successful sync ever → unhealthy + never_succeeded."""
    db = _fake_db_factory({
        "SELECT 1": [],
        "SELECT started_at, status": [],
        "SELECT started_at, error_message": [],
    })
    response = await _get_health(_make_app(db))
    assert response.status_code == 503
    body = response.json()
    assert body["sync"]["status"] == "never_succeeded"


@pytest.mark.asyncio
async def test_health_handles_naive_local_time_correctly():
    """Regression for the 'negative age' bug.

    sync_history stores naive local time (datetime.now().isoformat() with no
    tz). The first implementation treated it as UTC, producing negative ages
    on machines in non-UTC timezones (Asia/Shanghai → -8h skew). Verify the
    parser treats naive timestamps as naive local.
    """
    # 5 minutes ago in local time, no tz suffix
    five_min_ago_local = (datetime.now() - timedelta(minutes=5)).isoformat()
    db = _fake_db_factory({
        "SELECT 1": [],
        "SELECT started_at, status": [(five_min_ago_local, "success", "")],
        "SELECT started_at, error_message": [],
    })
    response = await _get_health(_make_app(db))
    body = response.json()
    age = body["sync"]["last_success_age_seconds"]
    assert 0 < age < 600, f"expected ~300s, got {age} (negative = local/UTC bug)"


@pytest.mark.asyncio
async def test_health_tolerates_malformed_timestamp():
    """Garbled timestamp shouldn't crash the health probe."""
    db = _fake_db_factory({
        "SELECT 1": [],
        "SELECT started_at, status": [("not-a-date", "success", "")],
        "SELECT started_at, error_message": [],
    })
    response = await _get_health(_make_app(db))
    body = response.json()
    # Status defaults to 'ok' when age can't be computed — debatable, but
    # explicit: we'd rather not page on a parse failure. Document via test.
    assert body["sync"]["status"] == "ok"
    assert "last_success_age_seconds" not in body["sync"]
