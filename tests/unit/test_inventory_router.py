"""Tests for src/api/routers/inventory.py"""

from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.middleware.rate_limit import setup_rate_limiting
from src.api.routers.auth import create_access_token
from src.api.routers.inventory import router
from src.exceptions import KingdeeConnectionError
from src.models.inventory import InventoryDetail, InventorySearchResponse, MaterialMatch


def _auth_header():
    token = create_access_token(data={"sub": "tester"})
    return {"Authorization": f"Bearer {token}"}


def _build_app(reader=None):
    app = FastAPI()
    setup_rate_limiting(app)
    app.include_router(router)
    if reader is not None:
        app.state.inventory_reader = reader
    return app


def _mock_reader():
    reader = AsyncMock()
    reader.search_materials = AsyncMock(
        return_value=InventorySearchResponse(
            query="test",
            total=1,
            items=[
                MaterialMatch(
                    material_code="07.01.001",
                    material_name="潜水镜",
                    specification="GT38-BLK",
                    erp_class="9",
                    erp_class_label="成品",
                )
            ],
        )
    )
    reader.get_inventory_by_material = AsyncMock(
        return_value=InventoryDetail(
            material_code="07.01.001",
            material_name="潜水镜",
            specification="GT38-BLK",
            erp_class="9",
            erp_class_label="成品",
            total_qty=Decimal("1234"),
            warehouse_count=2,
            rows=[],
        )
    )
    return reader


# ---------------------------------------------------------------------------
# TestSearch
# ---------------------------------------------------------------------------


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_requires_auth(self):
        app = _build_app(_mock_reader())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/inventory/search?q=GT38")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_search_validates_q_min_length(self):
        app = _build_app(_mock_reader())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/inventory/search?q=a", headers=_auth_header())
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_search_validates_q_max_length(self):
        app = _build_app(_mock_reader())
        long_q = "x" * 51
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/inventory/search?q={long_q}", headers=_auth_header()
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_search_returns_response_model(self):
        app = _build_app(_mock_reader())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/inventory/search?q=GT38", headers=_auth_header()
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "query" in body
        assert "total" in body
        assert "items" in body
        assert body["total"] == 1
        assert body["items"][0]["material_code"] == "07.01.001"

    @pytest.mark.asyncio
    async def test_search_value_error_returns_400(self):
        reader = _mock_reader()
        reader.search_materials = AsyncMock(side_effect=ValueError("Invalid characters in query"))
        app = _build_app(reader)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/inventory/search?q=GT38", headers=_auth_header()
            )
        assert resp.status_code == 400
        assert "Invalid characters" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_search_kingdee_error_returns_502(self):
        reader = _mock_reader()
        reader.search_materials = AsyncMock(
            side_effect=KingdeeConnectionError("connection refused")
        )
        app = _build_app(reader)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/inventory/search?q=GT38", headers=_auth_header()
            )
        assert resp.status_code == 502
        assert resp.json()["detail"] == "ERP system unavailable"

    @pytest.mark.asyncio
    async def test_search_unexpected_exception_returns_500(self):
        reader = _mock_reader()
        reader.search_materials = AsyncMock(side_effect=RuntimeError("boom"))
        app = _build_app(reader)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/inventory/search?q=GT38", headers=_auth_header()
            )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# TestGetMaterial
# ---------------------------------------------------------------------------


class TestGetMaterial:
    @pytest.mark.asyncio
    async def test_get_material_validates_code_pattern(self):
        app = _build_app(_mock_reader())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/inventory/material/ab;cd", headers=_auth_header()
            )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_material_returns_detail(self):
        app = _build_app(_mock_reader())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/inventory/material/07.01.001", headers=_auth_header()
            )
        assert resp.status_code == 200
        body = resp.json()
        assert "rows" in body
        assert "total_qty" in body
        assert "warehouse_count" in body
        assert body["material_code"] == "07.01.001"
        assert body["warehouse_count"] == 2

    @pytest.mark.asyncio
    async def test_get_material_passes_include_zero_flag(self):
        reader = _mock_reader()
        app = _build_app(reader)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/inventory/material/07.01.001?include_zero=true",
                headers=_auth_header(),
            )
        assert resp.status_code == 200
        reader.get_inventory_by_material.assert_called_once_with(
            material_code="07.01.001", include_zero=True
        )

    @pytest.mark.asyncio
    async def test_get_material_kingdee_error_returns_502(self):
        reader = _mock_reader()
        reader.get_inventory_by_material = AsyncMock(
            side_effect=KingdeeConnectionError("timeout")
        )
        app = _build_app(reader)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/inventory/material/07.01.001", headers=_auth_header()
            )
        assert resp.status_code == 502

    @pytest.mark.asyncio
    async def test_get_material_unexpected_exception_returns_500(self):
        reader = _mock_reader()
        reader.get_inventory_by_material = AsyncMock(side_effect=RuntimeError("crash"))
        app = _build_app(reader)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/inventory/material/07.01.001", headers=_auth_header()
            )
        assert resp.status_code == 500

    @pytest.mark.asyncio
    async def test_get_material_requires_auth(self):
        app = _build_app(_mock_reader())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/inventory/material/07.01.001")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestRateLimit
# ---------------------------------------------------------------------------


class TestRateLimit:
    @pytest.mark.asyncio
    async def test_search_rate_limited(self):
        """21 rapid-fire requests from the same IP should trigger at least one 429."""
        app = _build_app(_mock_reader())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            responses = []
            for _ in range(21):
                resp = await client.get(
                    "/api/inventory/search?q=GT38", headers=_auth_header()
                )
                responses.append(resp.status_code)
        assert 429 in responses
