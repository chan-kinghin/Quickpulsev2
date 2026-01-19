"""Tests for /api/mto/* endpoints."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.routers.auth import create_access_token, router as auth_router
from src.api.routers.mto import router as mto_router
from src.models.mto_status import (
    ChildItem,
    MTOStatusResponse,
    ParentItem,
)


@pytest.fixture
def mock_mto_handler():
    """Create mock MTO handler."""
    handler = MagicMock()
    handler.get_status = AsyncMock()
    return handler


@pytest.fixture
def mock_db():
    """Create mock database."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=[])
    return db


@pytest.fixture
def sample_mto_response():
    """Create sample MTO status response."""
    from datetime import datetime

    return MTOStatusResponse(
        mto_number="AK2510034",
        parent=ParentItem(
            mto_number="AK2510034",
            customer_name="Test Customer",
            delivery_date="2025-02-01",
        ),
        children=[
            ChildItem(
                material_code="C001",
                material_name="Component 1",
                specification="Spec C1",
                aux_attributes="",
                material_type=1,
                material_type_name="Self-made",
                required_qty=Decimal("50"),
                picked_qty=Decimal("30"),
                unpicked_qty=Decimal("20"),
                order_qty=Decimal("50"),
                receipt_qty=Decimal("25"),
                unreceived_qty=Decimal("25"),
                pick_request_qty=Decimal("50"),
                pick_actual_qty=Decimal("30"),
                delivered_qty=Decimal("10"),
                inventory_qty=Decimal("15"),
                receipt_source="PRD_INSTOCK",
            ),
        ],
        query_time=datetime(2025, 1, 15, 10, 0),
        data_source="live",
    )


@pytest.fixture
def app_with_mto(mock_mto_handler, mock_db):
    """Create app with MTO router and mocked state."""
    app = FastAPI()

    # Set up mocked state
    app.state.mto_handler = mock_mto_handler
    app.state.db = mock_db

    app.include_router(auth_router)
    app.include_router(mto_router)
    return app


@pytest.fixture
def auth_headers():
    """Create valid auth headers."""
    token = create_access_token(data={"sub": "testuser"})
    return {"Authorization": f"Bearer {token}"}


class TestGetMTOStatus:
    """Tests for GET /api/mto/{mto_number}."""

    @pytest.mark.asyncio
    async def test_get_mto_success(
        self, app_with_mto, auth_headers, mock_mto_handler, sample_mto_response
    ):
        """Test successful MTO query."""
        mock_mto_handler.get_status.return_value = sample_mto_response

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/mto/AK2510034", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["mto_number"] == "AK2510034"
        assert data["parent_item"]["mto_number"] == "AK2510034"
        assert len(data["child_items"]) == 1
        mock_mto_handler.get_status.assert_called_once_with(
            "AK2510034", use_cache=True
        )

    @pytest.mark.asyncio
    async def test_get_mto_not_found(self, app_with_mto, auth_headers, mock_mto_handler):
        """Test MTO not found returns 404."""
        mock_mto_handler.get_status.side_effect = ValueError(
            "MTO not found: NONEXISTENT"
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/mto/NONEXISTENT", headers=auth_headers)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_mto_use_cache_false(
        self, app_with_mto, auth_headers, mock_mto_handler, sample_mto_response
    ):
        """Test use_cache=false parameter."""
        mock_mto_handler.get_status.return_value = sample_mto_response

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/mto/AK2510034?use_cache=false", headers=auth_headers
            )

        assert response.status_code == 200
        mock_mto_handler.get_status.assert_called_once_with(
            "AK2510034", use_cache=False
        )

    @pytest.mark.asyncio
    async def test_get_mto_requires_auth(self, app_with_mto):
        """Test MTO endpoint requires authentication."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/mto/AK2510034")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_mto_invalid_token(self, app_with_mto):
        """Test MTO endpoint rejects invalid token."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            headers = {"Authorization": "Bearer invalid_token"}
            response = await client.get("/api/mto/AK2510034", headers=headers)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_mto_server_error(
        self, app_with_mto, auth_headers, mock_mto_handler
    ):
        """Test server error returns 500."""
        mock_mto_handler.get_status.side_effect = Exception("API connection failed")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/mto/AK2510034", headers=auth_headers)

        assert response.status_code == 500
        assert "connection failed" in response.json()["detail"].lower()


class TestSearchMTO:
    """Tests for GET /api/search."""

    @pytest.mark.asyncio
    async def test_search_success(self, app_with_mto, auth_headers, mock_db):
        """Test successful search returns results."""
        mock_db.execute.return_value = [
            ("AK2510034", "Product 1", 100),
            ("AK2510035", "Product 2", 200),
        ]

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/search?q=AK251", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["mto_number"] == "AK2510034"
        assert data[1]["mto_number"] == "AK2510035"

    @pytest.mark.asyncio
    async def test_search_empty_results(self, app_with_mto, auth_headers, mock_db):
        """Test search with no results."""
        mock_db.execute.return_value = []

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/search?q=NONEXISTENT", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_search_requires_min_length(self, app_with_mto, auth_headers):
        """Test search requires minimum query length."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/search?q=A", headers=auth_headers)

        # Should fail validation (min_length=2)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_requires_query_param(self, app_with_mto, auth_headers):
        """Test search requires q parameter."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/search", headers=auth_headers)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_search_requires_auth(self, app_with_mto):
        """Test search endpoint requires authentication."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/search?q=AK251")

        assert response.status_code == 401


class TestExportMTO:
    """Tests for GET /api/export/mto/{mto_number}."""

    @pytest.mark.asyncio
    async def test_export_success(
        self, app_with_mto, auth_headers, mock_mto_handler, sample_mto_response
    ):
        """Test successful CSV export."""
        mock_mto_handler.get_status.return_value = sample_mto_response

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/export/mto/AK2510034", headers=auth_headers
            )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers["content-disposition"]
        assert "MTO_AK2510034.csv" in response.headers["content-disposition"]

        # Check CSV content
        content = response.content.decode("utf-8-sig")
        lines = content.strip().split("\n")
        assert len(lines) >= 2  # Header + at least 1 data row

    @pytest.mark.asyncio
    async def test_export_csv_headers(
        self, app_with_mto, auth_headers, mock_mto_handler, sample_mto_response
    ):
        """Test CSV has correct headers."""
        mock_mto_handler.get_status.return_value = sample_mto_response

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/export/mto/AK2510034", headers=auth_headers
            )

        content = response.content.decode("utf-8-sig")
        header_line = content.strip().split("\n")[0]

        # Check Chinese headers
        assert "物料编码" in header_line
        assert "物料名称" in header_line
        assert "需求量" in header_line

    @pytest.mark.asyncio
    async def test_export_not_found(
        self, app_with_mto, auth_headers, mock_mto_handler
    ):
        """Test export not found returns 404."""
        mock_mto_handler.get_status.side_effect = ValueError("MTO not found")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/export/mto/NONEXISTENT", headers=auth_headers
            )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_export_uses_live_data_by_default(
        self, app_with_mto, auth_headers, mock_mto_handler, sample_mto_response
    ):
        """Test export uses live data by default (use_cache=false)."""
        mock_mto_handler.get_status.return_value = sample_mto_response

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            await client.get("/api/export/mto/AK2510034", headers=auth_headers)

        mock_mto_handler.get_status.assert_called_once_with(
            "AK2510034", use_cache=False
        )

    @pytest.mark.asyncio
    async def test_export_can_use_cache(
        self, app_with_mto, auth_headers, mock_mto_handler, sample_mto_response
    ):
        """Test export can use cache when specified."""
        mock_mto_handler.get_status.return_value = sample_mto_response

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            await client.get(
                "/api/export/mto/AK2510034?use_cache=true", headers=auth_headers
            )

        mock_mto_handler.get_status.assert_called_once_with(
            "AK2510034", use_cache=True
        )

    @pytest.mark.asyncio
    async def test_export_requires_auth(self, app_with_mto):
        """Test export endpoint requires authentication."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/export/mto/AK2510034")

        assert response.status_code == 401
