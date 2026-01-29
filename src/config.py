"""
Configuration Management Module

Responsibilities:
1. Read Kingdee API credentials from environment variables (preferred)
2. Fallback to conf.ini for backwards compatibility
3. Read sync config from sync_config.json
4. Config validation and defaults

Environment Variables (preferred):
    KINGDEE_SERVER_URL - K3Cloud server URL
    KINGDEE_ACCT_ID    - Account ID (data center)
    KINGDEE_USER_NAME  - Username
    KINGDEE_APP_ID     - Application ID
    KINGDEE_APP_SEC    - Application Secret
    KINGDEE_LCID       - Language ID (default: 2052)
"""

import configparser
import json
import os
from functools import lru_cache
from pathlib import Path

from fastapi import Depends
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.database.connection import Database
from src.kingdee.client import KingdeeClient


class KingdeeConfig(BaseSettings):
    """Kingdee K3Cloud API Configuration.

    Credentials are loaded in this priority order:
    1. Environment variables (KINGDEE_*)
    2. .env file (if exists)
    3. conf.ini file (legacy, not recommended)
    """

    model_config = SettingsConfigDict(
        env_prefix="KINGDEE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    server_url: str = Field(default="", description="K3Cloud server URL")
    acct_id: str = Field(default="", description="Account ID")
    user_name: str = Field(default="", description="Username")
    app_id: str = Field(default="", description="Application ID")
    app_sec: str = Field(default="", description="Application Secret")
    lcid: int = Field(default=2052, description="Language ID (2052=Chinese)")
    connect_timeout: int = Field(default=15, description="Connection timeout (seconds)")
    request_timeout: int = Field(default=30, description="Request timeout (seconds)")

    @classmethod
    def from_env(cls) -> "KingdeeConfig":
        """Load config from environment variables (preferred method)."""
        return cls()

    @classmethod
    def from_ini(cls, ini_path: str = "conf.ini") -> "KingdeeConfig":
        """Load config from INI file (legacy fallback)."""
        config = configparser.ConfigParser()
        config.read(ini_path, encoding="utf-8")

        section = config["config"]
        return cls(
            server_url=section["X-KDApi-ServerUrl"],
            acct_id=section["X-KDApi-AcctID"],
            user_name=section["X-KDApi-UserName"],
            app_id=section["X-KDApi-AppID"],
            app_sec=section["X-KDApi-AppSec"],
            lcid=int(section.get("X-KDApi-LCID", 2052)),
            connect_timeout=int(section.get("X-KDApi-ConnectTimeout", 15)),
            request_timeout=int(section.get("X-KDApi-RequestTimeout", 30)),
        )

    @classmethod
    def load(cls) -> "KingdeeConfig":
        """Load config with automatic source detection.

        Priority: Environment variables > .env file > conf.ini
        """
        # Try environment variables first (includes .env via pydantic-settings)
        config = cls.from_env()

        # Check if we got valid credentials from env
        if config.server_url and config.acct_id and config.app_id and config.app_sec:
            return config

        # Fallback to conf.ini if it exists
        ini_path = Path("conf.ini")
        if ini_path.exists():
            return cls.from_ini(str(ini_path))

        # Return empty config (will fail on use, but allows app to start)
        return config

    def is_valid(self) -> bool:
        """Check if credentials are configured."""
        return bool(self.server_url and self.acct_id and self.app_id and self.app_sec)


class AutoSyncConfig(BaseSettings):
    """Auto Sync Configuration"""

    enabled: bool = Field(True, description="Enable auto sync")
    schedule: list[str] = Field(
        ["07:00", "12:00", "16:00", "18:00"],
        description="Auto sync schedule (HH:MM format)",
    )
    days_back: int = Field(90, ge=1, le=365, description="Days to sync")

    @field_validator("schedule")
    def validate_schedule(cls, value: list[str]) -> list[str]:
        import re

        for time_str in value:
            if not re.match(r"^([01]?\d|2[0-3]):([0-5]\d)$", time_str):
                raise ValueError(f"Invalid time format: {time_str}")
        return value


class ManualSyncConfig(BaseSettings):
    """Manual Sync Configuration"""

    default_days: int = Field(90, description="Default sync days")
    max_days: int = Field(365, description="Maximum sync days")
    min_days: int = Field(1, description="Minimum sync days")


class PerformanceConfig(BaseSettings):
    """Performance Configuration"""

    chunk_days: int = Field(7, ge=1, le=30, description="Chunk days")
    batch_size: int = Field(1000, ge=100, le=10000, description="Batch insert size")
    parallel_chunks: int = Field(2, ge=1, le=4, description="Parallel chunk count")
    retry_count: int = Field(3, ge=1, le=5, description="Retry count")


class QueryCacheConfig(BaseSettings):
    """Query Cache Configuration for MTO lookups"""

    enabled: bool = Field(True, description="Enable cache-first queries")
    ttl_minutes: int = Field(60, ge=1, le=1440, description="Cache TTL in minutes")
    fallback_on_stale: bool = Field(True, description="Fallback to live API if cache stale")


class MemoryCacheConfig(BaseSettings):
    """In-Memory Cache Configuration for sub-10ms query responses"""

    enabled: bool = Field(True, description="Enable in-memory L1 cache")
    max_size: int = Field(2000, ge=100, le=10000, description="Max cached MTO entries")
    ttl_seconds: int = Field(1800, ge=60, le=7200, description="Cache TTL in seconds")
    warm_on_startup: bool = Field(True, description="Pre-load cache on startup")
    warm_count: int = Field(100, ge=0, le=500, description="Number of MTOs to warm on startup")


class SyncConfig(BaseSettings):
    """Complete Sync Configuration"""

    auto_sync: AutoSyncConfig = Field(default_factory=AutoSyncConfig)
    manual_sync: ManualSyncConfig = Field(default_factory=ManualSyncConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    query_cache: QueryCacheConfig = Field(default_factory=QueryCacheConfig)
    memory_cache: MemoryCacheConfig = Field(default_factory=MemoryCacheConfig)

    _config_path: str = "sync_config.json"

    @classmethod
    def load(cls, path: str = "sync_config.json") -> "SyncConfig":
        """Load config from JSON file."""
        config_path = Path(path)
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            instance = cls(**data)
        else:
            instance = cls()
        instance._config_path = path
        return instance

    def save(self) -> None:
        """Save config to JSON file."""
        with open(self._config_path, "w", encoding="utf-8") as handle:
            json.dump(self.model_dump(), handle, indent=2, ensure_ascii=False)

    def reload(self) -> None:
        """Reload config (for detecting runtime changes)."""
        new_config = SyncConfig.load(self._config_path)
        self.auto_sync = new_config.auto_sync
        self.manual_sync = new_config.manual_sync
        self.performance = new_config.performance
        self.query_cache = new_config.query_cache
        self.memory_cache = new_config.memory_cache


class Config:
    """Main Config Class - Factory Pattern (NOT Singleton).

    Use FastAPI's Depends() for dependency injection instead of singleton.
    This enables easier testing and follows Dependency Inversion Principle.
    """

    def __init__(
        self,
        kingdee: KingdeeConfig,
        sync: SyncConfig,
        db_path: Path = Path("data/quickpulse.db"),
        reports_dir: Path = Path("reports"),
    ):
        self.kingdee = kingdee
        self.sync = sync
        self.db_path = db_path
        self.reports_dir = reports_dir

    @classmethod
    def load(cls, sync_path: str = "sync_config.json") -> "Config":
        """Factory method to load config.

        Kingdee credentials: Environment variables > .env > conf.ini
        Sync config: sync_config.json
        """
        return cls(
            kingdee=KingdeeConfig.load(),
            sync=SyncConfig.load(sync_path),
        )


@lru_cache()
def get_config() -> Config:
    """Get config instance (cached for performance)."""
    return Config.load()


def get_kingdee_client(config: Config = Depends(get_config)) -> KingdeeClient:
    """Get KingdeeClient via dependency injection."""
    return KingdeeClient(config.kingdee)


def get_database(config: Config = Depends(get_config)) -> Database:
    """Get Database via dependency injection."""
    return Database(config.db_path)
