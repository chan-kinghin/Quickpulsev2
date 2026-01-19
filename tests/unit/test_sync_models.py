"""Tests for src/models/sync.py"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.sync import (
    SyncConfigResponse,
    SyncConfigUpdateRequest,
    SyncStatusResponse,
    SyncTriggerRequest,
)


class TestSyncTriggerRequest:
    """Tests for SyncTriggerRequest model."""

    def test_default_values(self):
        """Test default values."""
        request = SyncTriggerRequest()
        assert request.days_back == 90
        assert request.chunk_days == 7
        assert request.force_full is False

    def test_custom_values(self):
        """Test custom values."""
        request = SyncTriggerRequest(
            days_back=30,
            chunk_days=14,
            force_full=True,
        )
        assert request.days_back == 30
        assert request.chunk_days == 14
        assert request.force_full is True

    def test_force_alias(self):
        """Test force_full can be set via 'force' alias."""
        request = SyncTriggerRequest(force=True)
        assert request.force_full is True

    def test_days_back_minimum(self):
        """Test days_back minimum bound."""
        request = SyncTriggerRequest(days_back=1)
        assert request.days_back == 1

        with pytest.raises(ValidationError):
            SyncTriggerRequest(days_back=0)

    def test_days_back_maximum(self):
        """Test days_back maximum bound."""
        request = SyncTriggerRequest(days_back=365)
        assert request.days_back == 365

        with pytest.raises(ValidationError):
            SyncTriggerRequest(days_back=366)

    def test_chunk_days_minimum(self):
        """Test chunk_days minimum bound."""
        request = SyncTriggerRequest(chunk_days=1)
        assert request.chunk_days == 1

        with pytest.raises(ValidationError):
            SyncTriggerRequest(chunk_days=0)

    def test_chunk_days_maximum(self):
        """Test chunk_days maximum bound."""
        request = SyncTriggerRequest(chunk_days=30)
        assert request.chunk_days == 30

        with pytest.raises(ValidationError):
            SyncTriggerRequest(chunk_days=31)


class TestSyncStatusResponse:
    """Tests for SyncStatusResponse model."""

    def test_idle_status(self):
        """Test idle status response."""
        response = SyncStatusResponse(
            status="idle",
            phase="",
            message="",
            days_back=0,
            progress={},
        )
        assert response.status == "idle"
        assert response.started_at is None

    def test_running_status(self):
        """Test running status response."""
        response = SyncStatusResponse(
            status="running",
            phase="chunk",
            message="Syncing 2025-01-01 to 2025-01-07",
            days_back=90,
            progress={"chunk_index": 1, "total_chunks": 13},
            started_at=datetime(2025, 1, 15, 10, 0, 0),
        )
        assert response.status == "running"
        assert response.phase == "chunk"
        assert response.progress["chunk_index"] == 1

    def test_success_status(self):
        """Test success status response."""
        response = SyncStatusResponse(
            status="success",
            phase="finalize",
            message="Sync completed successfully",
            days_back=90,
            progress={"records_synced": 1500},
            started_at=datetime(2025, 1, 15, 10, 0, 0),
            finished_at=datetime(2025, 1, 15, 10, 30, 0),
        )
        assert response.status == "success"
        assert response.finished_at is not None

    def test_error_status(self):
        """Test error status response."""
        response = SyncStatusResponse(
            status="error",
            phase="chunk",
            message="Connection failed",
            days_back=90,
            progress={},
            started_at=datetime(2025, 1, 15, 10, 0, 0),
            finished_at=datetime(2025, 1, 15, 10, 5, 0),
            error="Connection to Kingdee failed",
        )
        assert response.status == "error"
        assert response.error is not None


class TestSyncConfigResponse:
    """Tests for SyncConfigResponse model."""

    def test_config_response(self):
        """Test config response."""
        response = SyncConfigResponse(
            auto_sync_enabled=True,
            auto_sync_schedule=["07:00", "12:00", "18:00"],
            auto_sync_days=90,
            manual_sync_default_days=90,
        )
        assert response.auto_sync_enabled is True
        assert len(response.auto_sync_schedule) == 3
        assert response.auto_sync_days == 90
        assert response.manual_sync_default_days == 90


class TestSyncConfigUpdateRequest:
    """Tests for SyncConfigUpdateRequest model."""

    def test_all_optional(self):
        """Test all fields are optional."""
        request = SyncConfigUpdateRequest()
        assert request.auto_sync_enabled is None
        assert request.auto_sync_days is None
        assert request.manual_sync_default_days is None

    def test_partial_update(self):
        """Test partial update with some fields."""
        request = SyncConfigUpdateRequest(
            auto_sync_enabled=False,
            auto_sync_days=30,
        )
        assert request.auto_sync_enabled is False
        assert request.auto_sync_days == 30
        assert request.manual_sync_default_days is None

    def test_auto_sync_days_bounds(self):
        """Test auto_sync_days validation in update."""
        request = SyncConfigUpdateRequest(auto_sync_days=1)
        assert request.auto_sync_days == 1

        request = SyncConfigUpdateRequest(auto_sync_days=365)
        assert request.auto_sync_days == 365

        with pytest.raises(ValidationError):
            SyncConfigUpdateRequest(auto_sync_days=0)

        with pytest.raises(ValidationError):
            SyncConfigUpdateRequest(auto_sync_days=400)

    def test_manual_sync_default_days_bounds(self):
        """Test manual_sync_default_days validation."""
        request = SyncConfigUpdateRequest(manual_sync_default_days=1)
        assert request.manual_sync_default_days == 1

        request = SyncConfigUpdateRequest(manual_sync_default_days=365)
        assert request.manual_sync_default_days == 365

        with pytest.raises(ValidationError):
            SyncConfigUpdateRequest(manual_sync_default_days=0)

        with pytest.raises(ValidationError):
            SyncConfigUpdateRequest(manual_sync_default_days=400)
