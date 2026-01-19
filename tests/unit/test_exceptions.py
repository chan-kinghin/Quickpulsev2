"""Tests for src/exceptions.py"""

import pytest

from src.exceptions import (
    ConfigError,
    DatabaseError,
    KingdeeConnectionError,
    KingdeeError,
    KingdeeQueryError,
    QuickPulseError,
    SyncError,
)


class TestExceptionHierarchy:
    """Test exception inheritance."""

    def test_all_inherit_from_quickpulse_error(self):
        """All custom exceptions should inherit from QuickPulseError."""
        assert issubclass(ConfigError, QuickPulseError)
        assert issubclass(KingdeeError, QuickPulseError)
        assert issubclass(DatabaseError, QuickPulseError)
        assert issubclass(SyncError, QuickPulseError)

    def test_kingdee_errors_inherit_from_kingdee_error(self):
        """Kingdee-specific errors inherit from KingdeeError."""
        assert issubclass(KingdeeConnectionError, KingdeeError)
        assert issubclass(KingdeeQueryError, KingdeeError)

    def test_quickpulse_error_is_exception(self):
        """QuickPulseError should inherit from Exception."""
        assert issubclass(QuickPulseError, Exception)


class TestExceptionMessages:
    """Test exception message handling."""

    def test_exception_message_preserved(self):
        """Test that exception messages are preserved."""
        msg = "Test error message"

        assert str(QuickPulseError(msg)) == msg
        assert str(ConfigError(msg)) == msg
        assert str(KingdeeError(msg)) == msg
        assert str(KingdeeConnectionError(msg)) == msg
        assert str(KingdeeQueryError(msg)) == msg
        assert str(DatabaseError(msg)) == msg
        assert str(SyncError(msg)) == msg

    def test_exception_with_empty_message(self):
        """Test exception with empty message."""
        exc = QuickPulseError("")
        assert str(exc) == ""

    def test_exception_with_unicode_message(self):
        """Test exception with Unicode message (Chinese characters)."""
        msg = "Query failed: invalid field"
        exc = KingdeeQueryError(msg)
        assert str(exc) == msg


class TestExceptionRaising:
    """Test exception raising behavior."""

    def test_raise_quickpulse_error(self):
        """Test raising QuickPulseError."""
        with pytest.raises(QuickPulseError):
            raise QuickPulseError("Base error")

    def test_raise_config_error(self):
        """Test raising ConfigError."""
        with pytest.raises(ConfigError):
            raise ConfigError("Config error")

        # Should also be catchable as QuickPulseError
        with pytest.raises(QuickPulseError):
            raise ConfigError("Config error")

    def test_raise_kingdee_error(self):
        """Test raising KingdeeError."""
        with pytest.raises(KingdeeError):
            raise KingdeeError("Kingdee error")

    def test_raise_kingdee_connection_error(self):
        """Test raising KingdeeConnectionError."""
        with pytest.raises(KingdeeConnectionError):
            raise KingdeeConnectionError("Connection failed")

        # Should also be catchable as KingdeeError
        with pytest.raises(KingdeeError):
            raise KingdeeConnectionError("Connection failed")

        # Should also be catchable as QuickPulseError
        with pytest.raises(QuickPulseError):
            raise KingdeeConnectionError("Connection failed")

    def test_raise_kingdee_query_error(self):
        """Test raising KingdeeQueryError."""
        with pytest.raises(KingdeeQueryError):
            raise KingdeeQueryError("Query failed")

    def test_raise_database_error(self):
        """Test raising DatabaseError."""
        with pytest.raises(DatabaseError):
            raise DatabaseError("Database error")

    def test_raise_sync_error(self):
        """Test raising SyncError."""
        with pytest.raises(SyncError):
            raise SyncError("Sync error")


class TestExceptionChaining:
    """Test exception chaining."""

    def test_exception_from_clause(self):
        """Test exception chaining with 'from' clause."""
        try:
            try:
                raise ValueError("Original error")
            except ValueError as e:
                raise KingdeeQueryError("Query failed") from e
        except KingdeeQueryError as exc:
            assert exc.__cause__ is not None
            assert isinstance(exc.__cause__, ValueError)
            assert str(exc.__cause__) == "Original error"

    def test_exception_with_context(self):
        """Test exception with implicit context."""
        try:
            try:
                raise ValueError("Original error")
            except ValueError:
                raise KingdeeQueryError("Query failed")
        except KingdeeQueryError as exc:
            assert exc.__context__ is not None
            assert isinstance(exc.__context__, ValueError)
