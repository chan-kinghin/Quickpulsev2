"""Custom exceptions for QuickPulse V2."""


class QuickPulseError(Exception):
    """Base exception for all QuickPulse errors."""


class ConfigError(QuickPulseError):
    """Configuration-related errors."""


class KingdeeError(QuickPulseError):
    """Kingdee API errors."""


class KingdeeConnectionError(KingdeeError):
    """Connection to Kingdee failed."""


class KingdeeQueryError(KingdeeError):
    """Query execution failed."""


class DatabaseError(QuickPulseError):
    """Database operation errors."""


class SyncError(QuickPulseError):
    """Data synchronization errors."""
