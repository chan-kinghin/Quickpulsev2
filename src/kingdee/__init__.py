"""Kingdee K3Cloud API integration."""

__all__ = ["KingdeeClient"]


def __getattr__(name: str):
    """Lazy import to avoid circular dependency with external kingdee package."""
    if name == "KingdeeClient":
        from src.kingdee.client import KingdeeClient
        return KingdeeClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
