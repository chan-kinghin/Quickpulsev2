"""
Configuration Management Module

Responsibilities:
1. Read Kingdee API credentials from conf.ini
2. Read sync config from sync_config.json
3. Support environment variable overrides
4. Config validation and defaults
"""

import configparser
import json
from functools import lru_cache
from pathlib import Path

from fastapi import Depends
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from src.database.connection import Database
from src.kingdee.client import KingdeeClient


class KingdeeConfig(BaseSettings):
    """Kingdee K3Cloud API Configuration"""

    server_url: str = Field(..., description="K3Cloud server URL")
    acct_id: str = Field(..., description="Account ID")
    user_name: str = Field(..., description="Username")
    app_id: str = Field(..., description="Application ID")
    app_sec: str = Field(..., description="Application Secret")
    lcid: int = Field(2052, description="Language ID (2052=Chinese)")
    connect_timeout: int = Field(15, description="Connection timeout (seconds)")
    request_timeout: int = Field(30, description="Request timeout (seconds)")

    @classmethod
    def from_ini(cls, ini_path: str = "conf.ini") -> "KingdeeConfig":
        """Load config from INI file."""
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


class SyncConfig(BaseSettings):
    """Complete Sync Configuration"""

    auto_sync: AutoSyncConfig = Field(default_factory=AutoSyncConfig)
    manual_sync: ManualSyncConfig = Field(default_factory=ManualSyncConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)

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
    def load(cls, ini_path: str = "conf.ini", sync_path: str = "sync_config.json") -> "Config":
        """Factory method to load config from files."""
        return cls(
            kingdee=KingdeeConfig.from_ini(ini_path),
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
