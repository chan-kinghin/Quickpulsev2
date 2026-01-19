"""Tests for src/config.py"""

import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError


class TestKingdeeConfig:
    """Tests for KingdeeConfig class."""

    def test_from_ini_valid(self, tmp_path):
        """Test loading from valid INI file."""
        ini_content = """
[config]
X-KDApi-ServerUrl = http://test.com/k3cloud/
X-KDApi-AcctID = test_acct
X-KDApi-UserName = test_user
X-KDApi-AppID = test_app
X-KDApi-AppSec = test_secret
X-KDApi-LCID = 2052
"""
        ini_path = tmp_path / "conf.ini"
        ini_path.write_text(ini_content)

        from src.config import KingdeeConfig

        config = KingdeeConfig.from_ini(str(ini_path))

        assert config.server_url == "http://test.com/k3cloud/"
        assert config.acct_id == "test_acct"
        assert config.user_name == "test_user"
        assert config.app_id == "test_app"
        assert config.app_sec == "test_secret"
        assert config.lcid == 2052

    def test_from_ini_missing_section(self, tmp_path):
        """Test error when INI section missing."""
        ini_path = tmp_path / "conf.ini"
        ini_path.write_text("[wrong_section]\nkey=value")

        from src.config import KingdeeConfig

        with pytest.raises(KeyError):
            KingdeeConfig.from_ini(str(ini_path))

    def test_default_timeout_values(self, mock_kingdee_config):
        """Test default timeout values."""
        assert mock_kingdee_config.connect_timeout == 15
        assert mock_kingdee_config.request_timeout == 30

    def test_custom_timeout_values(self, tmp_path):
        """Test custom timeout values from INI."""
        ini_content = """
[config]
X-KDApi-ServerUrl = http://test.com/k3cloud/
X-KDApi-AcctID = test_acct
X-KDApi-UserName = test_user
X-KDApi-AppID = test_app
X-KDApi-AppSec = test_secret
X-KDApi-LCID = 2052
X-KDApi-ConnectTimeout = 30
X-KDApi-RequestTimeout = 60
"""
        ini_path = tmp_path / "conf.ini"
        ini_path.write_text(ini_content)

        from src.config import KingdeeConfig

        config = KingdeeConfig.from_ini(str(ini_path))

        assert config.connect_timeout == 30
        assert config.request_timeout == 60

    def test_direct_instantiation(self):
        """Test direct instantiation with all required fields."""
        from src.config import KingdeeConfig

        config = KingdeeConfig(
            server_url="http://example.com/k3cloud/",
            acct_id="acct",
            user_name="user",
            app_id="app",
            app_sec="secret",
        )

        assert config.server_url == "http://example.com/k3cloud/"
        assert config.lcid == 2052  # Default


class TestAutoSyncConfig:
    """Tests for AutoSyncConfig validation."""

    def test_valid_schedule(self):
        """Test valid schedule times."""
        from src.config import AutoSyncConfig

        config = AutoSyncConfig(schedule=["07:00", "12:00", "18:00"])
        assert len(config.schedule) == 3
        assert config.schedule[0] == "07:00"

    def test_default_schedule(self):
        """Test default schedule values."""
        from src.config import AutoSyncConfig

        config = AutoSyncConfig()
        assert config.schedule == ["07:00", "12:00", "16:00", "18:00"]
        assert config.enabled is True
        assert config.days_back == 90

    def test_invalid_schedule_format_invalid_hour(self):
        """Test invalid hour in schedule raises ValidationError."""
        from src.config import AutoSyncConfig

        with pytest.raises(ValidationError):
            AutoSyncConfig(schedule=["25:00"])  # Hour > 23

    def test_invalid_schedule_format_invalid_minute(self):
        """Test invalid minute in schedule raises ValidationError."""
        from src.config import AutoSyncConfig

        with pytest.raises(ValidationError):
            AutoSyncConfig(schedule=["12:60"])  # Minute > 59

    def test_invalid_schedule_format_wrong_format(self):
        """Test wrong format raises ValidationError."""
        from src.config import AutoSyncConfig

        with pytest.raises(ValidationError):
            AutoSyncConfig(schedule=["noon"])  # Not HH:MM format

    def test_days_back_valid_bounds(self):
        """Test days_back validation with valid values."""
        from src.config import AutoSyncConfig

        config = AutoSyncConfig(days_back=1)
        assert config.days_back == 1

        config = AutoSyncConfig(days_back=365)
        assert config.days_back == 365

    def test_days_back_too_low(self):
        """Test days_back below minimum raises ValidationError."""
        from src.config import AutoSyncConfig

        with pytest.raises(ValidationError):
            AutoSyncConfig(days_back=0)

    def test_days_back_too_high(self):
        """Test days_back above maximum raises ValidationError."""
        from src.config import AutoSyncConfig

        with pytest.raises(ValidationError):
            AutoSyncConfig(days_back=400)


class TestManualSyncConfig:
    """Tests for ManualSyncConfig."""

    def test_default_values(self):
        """Test default values."""
        from src.config import ManualSyncConfig

        config = ManualSyncConfig()
        assert config.default_days == 90
        assert config.max_days == 365
        assert config.min_days == 1


class TestPerformanceConfig:
    """Tests for PerformanceConfig."""

    def test_default_values(self):
        """Test default values."""
        from src.config import PerformanceConfig

        config = PerformanceConfig()
        assert config.chunk_days == 7
        assert config.batch_size == 1000
        assert config.parallel_chunks == 2
        assert config.retry_count == 3

    def test_chunk_days_bounds(self):
        """Test chunk_days validation bounds."""
        from src.config import PerformanceConfig

        # Valid bounds
        config = PerformanceConfig(chunk_days=1)
        assert config.chunk_days == 1

        config = PerformanceConfig(chunk_days=30)
        assert config.chunk_days == 30

        # Invalid bounds
        with pytest.raises(ValidationError):
            PerformanceConfig(chunk_days=0)

        with pytest.raises(ValidationError):
            PerformanceConfig(chunk_days=31)


class TestQueryCacheConfig:
    """Tests for QueryCacheConfig."""

    def test_default_values(self):
        """Test default values."""
        from src.config import QueryCacheConfig

        config = QueryCacheConfig()
        assert config.enabled is True
        assert config.ttl_minutes == 60
        assert config.fallback_on_stale is True

    def test_ttl_bounds(self):
        """Test TTL validation bounds."""
        from src.config import QueryCacheConfig

        # Valid bounds
        config = QueryCacheConfig(ttl_minutes=1)
        assert config.ttl_minutes == 1

        config = QueryCacheConfig(ttl_minutes=1440)  # 24 hours
        assert config.ttl_minutes == 1440

        # Invalid bounds
        with pytest.raises(ValidationError):
            QueryCacheConfig(ttl_minutes=0)

        with pytest.raises(ValidationError):
            QueryCacheConfig(ttl_minutes=1441)


class TestSyncConfig:
    """Tests for SyncConfig load/save."""

    def test_load_nonexistent_uses_defaults(self, tmp_path):
        """Test loading nonexistent file returns defaults."""
        from src.config import SyncConfig

        config = SyncConfig.load(str(tmp_path / "nonexistent.json"))

        assert config.auto_sync.enabled is True
        assert config.performance.batch_size == 1000
        assert config.query_cache.ttl_minutes == 60

    def test_save_and_load_roundtrip(self, tmp_path):
        """Test save then load preserves values."""
        from src.config import AutoSyncConfig, SyncConfig

        config = SyncConfig(auto_sync=AutoSyncConfig(enabled=False, days_back=30))
        config._config_path = str(tmp_path / "sync_config.json")
        config.save()

        loaded = SyncConfig.load(config._config_path)
        assert loaded.auto_sync.enabled is False
        assert loaded.auto_sync.days_back == 30

    def test_save_creates_file(self, tmp_path):
        """Test save creates the JSON file."""
        from src.config import SyncConfig

        config = SyncConfig()
        config_path = tmp_path / "sync_config.json"
        config._config_path = str(config_path)
        config.save()

        assert config_path.exists()

        # Verify JSON content
        with config_path.open() as f:
            data = json.load(f)

        assert "auto_sync" in data
        assert "performance" in data

    def test_reload_updates_values(self, tmp_path):
        """Test reload() updates values from disk."""
        from src.config import SyncConfig

        config_path = tmp_path / "sync_config.json"

        # Create initial config
        config = SyncConfig()
        config._config_path = str(config_path)
        config.save()

        # Modify file directly
        with config_path.open() as f:
            data = json.load(f)
        data["auto_sync"]["enabled"] = False
        with config_path.open("w") as f:
            json.dump(data, f)

        # Reload and verify
        config.reload()
        assert config.auto_sync.enabled is False


class TestConfig:
    """Tests for main Config class."""

    def test_factory_load_creates_config(self, tmp_path):
        """Test Config.load() factory method."""
        # Create INI file
        ini_content = """
[config]
X-KDApi-ServerUrl = http://test.com/k3cloud/
X-KDApi-AcctID = test_acct
X-KDApi-UserName = test_user
X-KDApi-AppID = test_app
X-KDApi-AppSec = test_secret
"""
        ini_path = tmp_path / "conf.ini"
        ini_path.write_text(ini_content)

        from src.config import Config

        config = Config.load(str(ini_path), str(tmp_path / "sync.json"))

        assert config.kingdee.server_url == "http://test.com/k3cloud/"
        assert config.sync.auto_sync.enabled is True

    def test_direct_instantiation(self, mock_kingdee_config, mock_sync_config, tmp_path):
        """Test direct instantiation."""
        from src.config import Config

        config = Config(
            kingdee=mock_kingdee_config,
            sync=mock_sync_config,
            db_path=tmp_path / "test.db",
            reports_dir=tmp_path / "reports",
        )

        assert config.kingdee == mock_kingdee_config
        assert config.sync == mock_sync_config
        assert config.db_path == tmp_path / "test.db"
