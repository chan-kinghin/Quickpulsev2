"""Tests for /api/sync/* endpoints."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.routers.auth import create_access_token, router as auth_router
from src.api.routers.sync import router as sync_router
from src.sync.progress import SyncProgressData


@pytest.fixture
def mock_sync_service():
    """Create mock sync service."""
    service = MagicMock()
    service.is_running = MagicMock(return_value=False)
    service.run_sync = AsyncMock()
    return service


@pytest.fixture
def mock_sync_progress():
    """Create mock sync progress."""
    progress = MagicMock()
    progress.load = MagicMock(
        return_value=SyncProgressData(
            status="success",
            phase="complete",
            message="Sync completed",
            days_back=90,
            started_at=datetime(2025, 1, 15, 10, 0),
            finished_at=datetime(2025, 1, 15, 10, 30),
            progress={"percent": 100, "records_synced": 1500},
        )
    )
    return progress


@pytest.fixture
def mock_config():
    """Create mock config."""
    config = MagicMock()
    config.sync = MagicMock()
    config.sync.auto_sync = MagicMock()
    config.sync.auto_sync.enabled = True
    config.sync.auto_sync.schedule = ["07:00", "12:00", "18:00"]
    config.sync.auto_sync.days_back = 90
    config.sync.manual_sync = MagicMock()
    config.sync.manual_sync.default_days = 30
    config.sync.save = MagicMock()
    return config


@pytest.fixture
def mock_db():
    """Create mock database."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=[])
    return db


@pytest.fixture
def app_with_sync(mock_sync_service, mock_sync_progress, mock_config, mock_db):
    """Create app with sync router and mocked state."""
    app = FastAPI()

    app.state.sync_service = mock_sync_service
    app.state.sync_progress = mock_sync_progress
    app.state.config = mock_config
    app.state.db = mock_db

    app.include_router(auth_router)
    app.include_router(sync_router)
    return app


@pytest.fixture
def auth_headers():
    """Create valid auth headers."""
    token = create_access_token(data={"sub": "testuser"})
    return {"Authorization": f"Bearer {token}"}


class TestTriggerSync:
    """Tests for POST /api/sync/trigger."""

    @pytest.mark.asyncio
    async def test_trigger_sync_success(
        self, app_with_sync, auth_headers, mock_sync_service
    ):
        """Test successful sync trigger."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/sync/trigger",
                json={"days_back": 30},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sync_started"
        assert data["days_back"] == 30

    @pytest.mark.asyncio
    async def test_trigger_sync_already_running(
        self, app_with_sync, auth_headers, mock_sync_service
    ):
        """Test sync already running returns 409."""
        mock_sync_service.is_running.return_value = True

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/sync/trigger",
                json={"days_back": 30},
                headers=auth_headers,
            )

        assert response.status_code == 409
        assert "already running" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_trigger_sync_default_values(
        self, app_with_sync, auth_headers, mock_sync_service
    ):
        """Test sync uses default values."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/sync/trigger",
                json={},
                headers=auth_headers,
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_trigger_sync_custom_params(
        self, app_with_sync, auth_headers, mock_sync_service
    ):
        """Test sync with custom parameters."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/sync/trigger",
                json={
                    "days_back": 60,
                    "chunk_days": 14,
                    "force_full": True,
                },
                headers=auth_headers,
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_trigger_sync_requires_auth(self, app_with_sync):
        """Test sync trigger requires authentication."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/sync/trigger", json={"days_back": 30}
            )

        assert response.status_code == 401


class TestGetSyncStatus:
    """Tests for GET /api/sync/status."""

    @pytest.mark.asyncio
    async def test_get_status_success(
        self, app_with_sync, auth_headers, mock_sync_service
    ):
        """Test get sync status success."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/sync/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "is_running" in data
        assert "progress" in data
        assert "status" in data
        assert data["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_status_shows_running(
        self, app_with_sync, auth_headers, mock_sync_service, mock_sync_progress
    ):
        """Test status shows running state."""
        mock_sync_service.is_running.return_value = True
        mock_sync_progress.load.return_value = SyncProgressData(
            status="running",
            phase="chunk",
            message="Processing chunk 3/10",
            days_back=90,
            progress={"percent": 30, "chunk_index": 3},
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/sync/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["is_running"] is True
        assert data["status"] == "running"
        assert data["progress"] == 30

    @pytest.mark.asyncio
    async def test_get_status_shows_error(
        self, app_with_sync, auth_headers, mock_sync_service, mock_sync_progress
    ):
        """Test status shows error state."""
        mock_sync_progress.load.return_value = SyncProgressData(
            status="error",
            phase="",
            message="",
            days_back=90,
            error="Connection timeout",
        )

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/sync/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"
        assert data["error"] == "Connection timeout"

    @pytest.mark.asyncio
    async def test_get_status_requires_auth(self, app_with_sync):
        """Test status endpoint requires authentication."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/sync/status")

        assert response.status_code == 401


class TestGetSyncConfig:
    """Tests for GET /api/sync/config."""

    @pytest.mark.asyncio
    async def test_get_config_success(self, app_with_sync, auth_headers):
        """Test get sync config success."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/sync/config", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["auto_sync_enabled"] is True
        assert data["auto_sync_schedule"] == ["07:00", "12:00", "18:00"]
        assert data["auto_sync_days"] == 90
        assert data["manual_sync_default_days"] == 30

    @pytest.mark.asyncio
    async def test_get_config_requires_auth(self, app_with_sync):
        """Test config endpoint requires authentication."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/sync/config")

        assert response.status_code == 401


class TestUpdateSyncConfig:
    """Tests for PUT /api/sync/config."""

    @pytest.mark.asyncio
    async def test_update_config_success(
        self, app_with_sync, auth_headers, mock_config
    ):
        """Test update sync config success."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.put(
                "/api/sync/config",
                json={"auto_sync_days": 60},
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json()["status"] == "config_updated"
        mock_config.sync.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_config_enable_disable(
        self, app_with_sync, auth_headers, mock_config
    ):
        """Test enabling/disabling auto sync."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.put(
                "/api/sync/config",
                json={"auto_sync_enabled": False},
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert mock_config.sync.auto_sync.enabled is False

    @pytest.mark.asyncio
    async def test_update_config_multiple_fields(
        self, app_with_sync, auth_headers, mock_config
    ):
        """Test updating multiple config fields."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.put(
                "/api/sync/config",
                json={
                    "auto_sync_enabled": True,
                    "auto_sync_days": 120,
                    "manual_sync_default_days": 45,
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert mock_config.sync.auto_sync.days_back == 120
        assert mock_config.sync.manual_sync.default_days == 45

    @pytest.mark.asyncio
    async def test_update_config_empty_body(
        self, app_with_sync, auth_headers, mock_config
    ):
        """Test update with empty body succeeds (no changes)."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.put(
                "/api/sync/config",
                json={},
                headers=auth_headers,
            )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_config_requires_auth(self, app_with_sync):
        """Test config update requires authentication."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.put(
                "/api/sync/config",
                json={"auto_sync_days": 60},
            )

        assert response.status_code == 401


class TestGetSyncHistory:
    """Tests for GET /api/sync/history."""

    @pytest.mark.asyncio
    async def test_get_history_success(self, app_with_sync, auth_headers, mock_db):
        """Test get sync history success."""
        mock_db.execute.return_value = [
            ("2025-01-15T10:00:00", "2025-01-15T10:30:00", "success", 90, 1500, None),
            ("2025-01-14T10:00:00", "2025-01-14T10:25:00", "success", 90, 1400, None),
        ]

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/sync/history", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["status"] == "success"
        assert data[0]["records_synced"] == 1500

    @pytest.mark.asyncio
    async def test_get_history_empty(self, app_with_sync, auth_headers, mock_db):
        """Test empty sync history."""
        mock_db.execute.return_value = []

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/sync/history", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_history_with_error(self, app_with_sync, auth_headers, mock_db):
        """Test sync history with error entry."""
        mock_db.execute.return_value = [
            (
                "2025-01-15T10:00:00",
                "2025-01-15T10:05:00",
                "error",
                90,
                500,
                "Connection failed",
            ),
        ]

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/sync/history", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data[0]["status"] == "error"
        assert data[0]["error_message"] == "Connection failed"

    @pytest.mark.asyncio
    async def test_get_history_custom_limit(
        self, app_with_sync, auth_headers, mock_db
    ):
        """Test history with custom limit."""
        mock_db.execute.return_value = []

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.get(
                "/api/sync/history?limit=5", headers=auth_headers
            )

        assert response.status_code == 200
        # Verify the query used the limit
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args[0]
        assert 5 in call_args[1]  # Limit parameter

    @pytest.mark.asyncio
    async def test_get_history_requires_auth(self, app_with_sync):
        """Test history endpoint requires authentication."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_sync),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/sync/history")

        assert response.status_code == 401
