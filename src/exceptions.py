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


class ChatError(QuickPulseError):
    """Chat/LLM service errors."""


class ChatConnectionError(ChatError):
    """Connection to LLM API failed."""


class ChatRateLimitError(ChatError):
    """LLM API rate limit exceeded."""


class ChatSQLError(ChatError):
    """SQL validation or execution failed."""


class DatabaseError(QuickPulseError):
    """Database operation errors."""


class SyncError(QuickPulseError):
    """Data synchronization errors."""
