"""Tests for src/sync/progress.py"""

import json
import tempfile
from pathlib import Path

import pytest

from src.sync.progress import SyncProgress, SyncProgressData


class TestSyncProgressData:
    """Tests for SyncProgressData model."""

    def test_default_values(self):
        """Test default values."""
        data = SyncProgressData()
        assert data.status == "idle"
        assert data.phase == ""
        assert data.message == ""
        assert data.days_back == 0
        assert data.error is None
        assert data.started_at is None
        assert data.finished_at is None
        assert data.progress == {}

    def test_custom_values(self):
        """Test with custom values."""
        from datetime import datetime

        data = SyncProgressData(
            status="running",
            phase="chunk",
            message="Processing...",
            days_back=90,
            started_at=datetime(2025, 1, 15, 10, 0),
            progress={"chunk_index": 1},
        )
        assert data.status == "running"
        assert data.phase == "chunk"
        assert data.progress["chunk_index"] == 1


class TestSyncProgress:
    """Tests for SyncProgress class."""

    def test_start_sets_running(self, temp_reports_dir):
        """Test start() sets status to running."""
        progress = SyncProgress(temp_reports_dir / "status.json")
        progress.start(days_back=90)

        assert progress._data.status == "running"
        assert progress._data.phase == "init"
        assert progress._data.days_back == 90
        assert progress._data.started_at is not None

    def test_update_progress(self, temp_reports_dir):
        """Test update() modifies progress."""
        progress = SyncProgress(temp_reports_dir / "status.json")
        progress.start(90)
        progress.update("chunk", "Processing chunk 1", chunk_index=1, total_chunks=5)

        assert progress._data.phase == "chunk"
        assert progress._data.message == "Processing chunk 1"
        assert progress._data.progress["chunk_index"] == 1
        assert progress._data.progress["total_chunks"] == 5

    def test_update_accumulates_progress(self, temp_reports_dir):
        """Test update() accumulates progress keys."""
        progress = SyncProgress(temp_reports_dir / "status.json")
        progress.start(90)
        progress.update("phase1", "Message 1", key1="value1")
        progress.update("phase2", "Message 2", key2="value2")

        assert progress._data.progress["key1"] == "value1"
        assert progress._data.progress["key2"] == "value2"

    def test_finish_success(self, temp_reports_dir):
        """Test finish_success() sets correct state."""
        progress = SyncProgress(temp_reports_dir / "status.json")
        progress.start(90)
        progress.finish_success()

        assert progress._data.status == "success"
        assert progress._data.finished_at is not None
        assert progress._data.message == "Sync completed successfully"

    def test_finish_error(self, temp_reports_dir):
        """Test finish_error() preserves error message."""
        progress = SyncProgress(temp_reports_dir / "status.json")
        progress.start(90)
        progress.finish_error("Connection failed")

        assert progress._data.status == "error"
        assert progress._data.error == "Connection failed"
        assert progress._data.finished_at is not None

    def test_load_nonexistent(self, temp_reports_dir):
        """Test load() returns defaults for missing file."""
        progress = SyncProgress(temp_reports_dir / "nonexistent.json")
        data = progress.load()

        assert data.status == "idle"
        assert data.days_back == 0

    def test_save_creates_file(self, temp_reports_dir):
        """Test _save() creates the JSON file."""
        status_file = temp_reports_dir / "status.json"
        progress = SyncProgress(status_file)
        progress.start(90)

        assert status_file.exists()

    def test_save_creates_parent_directories(self, temp_reports_dir):
        """Test _save() creates parent directories."""
        status_file = temp_reports_dir / "nested" / "dir" / "status.json"
        progress = SyncProgress(status_file)
        progress.start(90)

        assert status_file.exists()
        assert status_file.parent.exists()

    def test_save_and_load_roundtrip(self, temp_reports_dir):
        """Test save then load preserves data."""
        status_file = temp_reports_dir / "status.json"

        # Save
        progress1 = SyncProgress(status_file)
        progress1.start(90)
        progress1.update("test", "Test message", custom_key="value")

        # Load in new instance
        progress2 = SyncProgress(status_file)
        data = progress2.load()

        assert data.status == "running"
        assert data.days_back == 90
        assert data.progress.get("custom_key") == "value"

    def test_save_serializes_datetime(self, temp_reports_dir):
        """Test datetime values are properly serialized."""
        status_file = temp_reports_dir / "status.json"
        progress = SyncProgress(status_file)
        progress.start(90)
        progress.finish_success()

        # Read raw JSON
        with status_file.open() as f:
            data = json.load(f)

        # datetime should be serialized as string
        assert isinstance(data["started_at"], str)
        assert isinstance(data["finished_at"], str)

    def test_load_with_timestamps(self, temp_reports_dir):
        """Test loading preserves timestamp values."""
        status_file = temp_reports_dir / "status.json"

        # Save with timestamps
        progress1 = SyncProgress(status_file)
        progress1.start(90)
        progress1.finish_success()

        # Load
        progress2 = SyncProgress(status_file)
        data = progress2.load()

        # Should load as datetime objects
        assert data.started_at is not None
        assert data.finished_at is not None


class TestSyncProgressStateTransitions:
    """Tests for state transitions."""

    def test_idle_to_running(self, temp_reports_dir):
        """Test transition from idle to running."""
        progress = SyncProgress(temp_reports_dir / "status.json")

        assert progress._data.status == "idle"
        progress.start(90)
        assert progress._data.status == "running"

    def test_running_to_success(self, temp_reports_dir):
        """Test transition from running to success."""
        progress = SyncProgress(temp_reports_dir / "status.json")
        progress.start(90)

        assert progress._data.status == "running"
        progress.finish_success()
        assert progress._data.status == "success"

    def test_running_to_error(self, temp_reports_dir):
        """Test transition from running to error."""
        progress = SyncProgress(temp_reports_dir / "status.json")
        progress.start(90)

        assert progress._data.status == "running"
        progress.finish_error("Test error")
        assert progress._data.status == "error"

    def test_multiple_updates_while_running(self, temp_reports_dir):
        """Test multiple updates while running."""
        progress = SyncProgress(temp_reports_dir / "status.json")
        progress.start(90)

        # Simulate sync phases
        progress.update("init", "Initializing...")
        assert progress._data.phase == "init"

        progress.update("chunk", "Processing chunk 1/5", chunk_index=1)
        assert progress._data.phase == "chunk"
        assert progress._data.progress["chunk_index"] == 1

        progress.update("chunk", "Processing chunk 2/5", chunk_index=2)
        assert progress._data.progress["chunk_index"] == 2

        progress.update("finalize", "Finalizing...")
        assert progress._data.phase == "finalize"

        progress.finish_success()
        assert progress._data.status == "success"
