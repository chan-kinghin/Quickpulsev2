"""Tests for input validation on MTO endpoints (Path params, pagination)."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.middleware.rate_limit import setup_rate_limiting
from src.api.routers.auth import create_access_token, router as auth_router
from src.api.routers.mto import router as mto_router
from src.models.mto_status import ChildItem, MTOStatusResponse, ParentItem


def _make_sample_response(mto_number="AK2510034"):
    """Build a valid MTOStatusResponse for testing."""
    return MTOStatusResponse(
        mto_number=mto_number,
        parent=ParentItem(
            mto_number=mto_number,
            customer_name="Test",
            delivery_date="2025-01-01",
        ),
        children=[],
        query_time=datetime(2025, 1, 1),
        data_source="live",
    )


@pytest.fixture
def mock_mto_handler():
    handler = MagicMock()
    handler.get_status = AsyncMock(return_value=_make_sample_response())
    handler.get_related_orders = AsyncMock(return_value=MagicMock())
    return handler


@pytest.fixture
def mock_db():
    db = MagicMock()
    # Return (count_result, search_results) pattern
    db.execute = AsyncMock(return_value=[])
    db.execute_read = AsyncMock(return_value=[])
    return db


@pytest.fixture
def app_with_mto(mock_mto_handler, mock_db):
    app = FastAPI()
    setup_rate_limiting(app)
    app.state.mto_handler = mock_mto_handler
    app.state.db = mock_db
    app.include_router(auth_router)
    app.include_router(mto_router)
    return app


@pytest.fixture
def auth_headers():
    token = create_access_token(data={"sub": "testuser"})
    return {"Authorization": f"Bearer {token}"}


class TestMTONumberPathValidation:
    """Test Path validation on mto_number: min_length=2, max_length=50, pattern=alphanumeric+hyphens."""

    @pytest.mark.asyncio
    async def test_valid_mto_standard(self, app_with_mto, auth_headers, mock_mto_handler):
        """Test standard MTO number passes validation."""
        mock_mto_handler.get_status.return_value = _make_sample_response("AK2510034")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/mto/AK2510034", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_valid_mto_min_length(self, app_with_mto, auth_headers, mock_mto_handler):
        """Test 2-char MTO number passes (min_length=2)."""
        mock_mto_handler.get_status.return_value = _make_sample_response("AB")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/mto/AB", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_valid_mto_with_hyphens(self, app_with_mto, auth_headers, mock_mto_handler):
        """Test MTO number with hyphens passes validation."""
        mock_mto_handler.get_status.return_value = _make_sample_response("test-123")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/mto/test-123", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_valid_mto_max_length(self, app_with_mto, auth_headers, mock_mto_handler):
        """Test 50-char MTO number passes (max_length=50)."""
        mto = "A" * 50
        mock_mto_handler.get_status.return_value = _make_sample_response(mto)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/api/mto/{mto}", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_mto_too_short(self, app_with_mto, auth_headers):
        """Test single-char MTO number rejected (min_length=2)."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/mto/A", headers=auth_headers)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_mto_too_long(self, app_with_mto, auth_headers):
        """Test 51-char MTO number rejected (max_length=50)."""
        mto = "A" * 51
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get(f"/api/mto/{mto}", headers=auth_headers)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_mto_with_space(self, app_with_mto, auth_headers):
        """Test MTO number with space rejected by pattern."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            # URL-encode the space as %20
            response = await client.get("/api/mto/AK%2025", headers=auth_headers)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_mto_with_special_char(self, app_with_mto, auth_headers):
        """Test MTO number with @ rejected by pattern."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/mto/AK%4025", headers=auth_headers)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_mto_with_slash(self, app_with_mto, auth_headers):
        """Test MTO number with slash rejected."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            # Use encoded slash %2F
            response = await client.get("/api/mto/AK%2F25", headers=auth_headers)
        # Slash in path causes either 404 (route not matched) or 422
        assert response.status_code in (404, 422)


class TestSearchPagination:
    """Test pagination params on /api/search."""

    @pytest.mark.asyncio
    async def test_pagination_defaults(self, app_with_mto, auth_headers, mock_db):
        """Test default limit=20, offset=0."""
        mock_db.execute_read = AsyncMock(side_effect=[[(5,)], []])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/search?q=AK251", headers=auth_headers)
        assert response.status_code == 200
        # Verify default params were used in the LIMIT/OFFSET query
        calls = mock_db.execute_read.call_args_list
        # Second call is the data query with LIMIT ? OFFSET ?
        data_call_args = calls[1][0][1]
        assert data_call_args[2] == 20  # default limit
        assert data_call_args[3] == 0   # default offset

    @pytest.mark.asyncio
    async def test_pagination_custom_values(self, app_with_mto, auth_headers, mock_db):
        """Test custom limit and offset."""
        mock_db.execute_read = AsyncMock(side_effect=[[(50,)], []])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/search?q=AK251&limit=10&offset=5", headers=auth_headers
            )
        assert response.status_code == 200
        calls = mock_db.execute_read.call_args_list
        data_call_args = calls[1][0][1]
        assert data_call_args[2] == 10
        assert data_call_args[3] == 5

    @pytest.mark.asyncio
    async def test_pagination_limit_max(self, app_with_mto, auth_headers):
        """Test limit > 100 rejected (le=100)."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/search?q=AK251&limit=101", headers=auth_headers
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_pagination_limit_min(self, app_with_mto, auth_headers):
        """Test limit < 1 rejected (ge=1)."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/search?q=AK251&limit=0", headers=auth_headers
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_pagination_offset_negative(self, app_with_mto, auth_headers):
        """Test negative offset rejected (ge=0)."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/search?q=AK251&offset=-1", headers=auth_headers
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_x_total_count_header(self, app_with_mto, auth_headers, mock_db):
        """Test X-Total-Count header present in search response."""
        mock_db.execute_read = AsyncMock(side_effect=[[(42,)], []])
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_mto),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/search?q=AK251", headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["x-total-count"] == "42"
