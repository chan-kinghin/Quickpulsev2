"""Tests for src/api/routers/auth.py"""

from datetime import timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

from src.api.routers.auth import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    get_current_user,
)


class TestCreateAccessToken:
    """Tests for JWT token creation."""

    def test_create_access_token_basic(self):
        """Test basic token creation."""
        token = create_access_token(data={"sub": "testuser"})

        # Should be a valid JWT
        assert isinstance(token, str)
        assert len(token) > 0

        # Decode and verify
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "testuser"
        assert "exp" in payload

    def test_create_access_token_with_custom_expiry(self):
        """Test token with custom expiry."""
        token = create_access_token(
            data={"sub": "testuser"}, expires_delta=timedelta(hours=2)
        )

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "testuser"
        # expiry should be set (we can't easily verify exact time)
        assert "exp" in payload

    def test_create_access_token_with_additional_data(self):
        """Test token with additional custom data."""
        token = create_access_token(
            data={"sub": "testuser", "role": "admin", "custom_field": "value"}
        )

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "testuser"
        assert payload["role"] == "admin"
        assert payload["custom_field"] == "value"

    def test_create_access_token_default_expiry(self):
        """Test token uses default expiry when not specified."""
        from datetime import datetime, timezone
        from unittest.mock import patch

        frozen_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        with patch("src.api.routers.auth.datetime") as mock_dt:
            mock_dt.now.return_value = frozen_now
            # Keep timedelta usable
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            token = create_access_token(data={"sub": "testuser"})

        payload = jwt.decode(
            token, SECRET_KEY, algorithms=[ALGORITHM],
            options={"verify_exp": False},
        )
        exp_timestamp = payload["exp"]

        expected_exp = frozen_now + timedelta(minutes=1440)
        assert exp_timestamp == int(expected_exp.timestamp())


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_valid_token(self):
        """Test valid token returns username."""
        token = create_access_token(data={"sub": "testuser"})
        user = await get_current_user(token)

        assert user == "testuser"

    @pytest.mark.asyncio
    async def test_invalid_token_raises(self):
        """Test invalid token raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user("invalid_token")

        assert exc_info.value.status_code == 401
        assert "credentials" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_token_without_sub_raises(self):
        """Test token without 'sub' claim raises 401."""
        # Create token without 'sub'
        token = jwt.encode({"data": "value", "exp": 9999999999}, SECRET_KEY, algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_raises(self):
        """Test expired token raises 401."""
        # Create already-expired token
        token = create_access_token(
            data={"sub": "testuser"}, expires_delta=timedelta(seconds=-1)
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_algorithm_raises(self):
        """Test token with wrong algorithm raises 401."""
        # Create token with different algorithm
        token = jwt.encode({"sub": "testuser"}, SECRET_KEY, algorithm="HS384")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_secret_raises(self):
        """Test token signed with wrong secret raises 401."""
        token = jwt.encode({"sub": "testuser"}, "wrong-secret", algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_malformed_jwt_raises(self):
        """Test malformed JWT raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user("not.a.valid.jwt.token")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_token_raises(self):
        """Test empty token raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user("")

        assert exc_info.value.status_code == 401
