"""Tests for auth hardening: env var overrides, token expiry config, rate limiting."""

from datetime import datetime, timedelta
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from jose import jwt

import src.api.routers.auth as auth_mod
from src.api.middleware.rate_limit import limiter, setup_rate_limiting


def _make_auth_app():
    """Create a fresh FastAPI app with auth router."""
    app = FastAPI()
    setup_rate_limiting(app)
    app.include_router(auth_mod.router)
    return app


class TestAuthPasswordEnvVar:
    """Test AUTH_PASSWORD environment variable override."""

    @pytest.mark.asyncio
    async def test_custom_password_works(self):
        """Test login succeeds with custom AUTH_PASSWORD."""
        with patch.object(auth_mod, "AUTH_PASSWORD", "supersecret"):
            app = _make_auth_app()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/api/auth/token",
                    data={"username": "admin", "password": "supersecret"},
                )
            assert response.status_code == 200
            assert "access_token" in response.json()

    @pytest.mark.asyncio
    async def test_default_password_rejected_when_overridden(self):
        """Test default password fails when AUTH_PASSWORD is overridden."""
        with patch.object(auth_mod, "AUTH_PASSWORD", "supersecret"):
            app = _make_auth_app()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/api/auth/token",
                    data={"username": "admin", "password": "quickpulse"},
                )
            assert response.status_code == 401


class TestTokenExpiryEnvVar:
    """Test AUTH_TOKEN_EXPIRE_MINUTES environment variable."""

    @pytest.mark.asyncio
    async def test_custom_expiry_applied(self):
        """Test token uses custom expiry from env var."""
        with patch.object(auth_mod, "ACCESS_TOKEN_EXPIRE_MINUTES", 30):
            app = _make_auth_app()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.post(
                    "/api/auth/token",
                    data={"username": "admin", "password": "quickpulse"},
                )
            assert response.status_code == 200
            token = response.json()["access_token"]
            payload = jwt.decode(
                token, auth_mod.SECRET_KEY, algorithms=[auth_mod.ALGORITHM]
            )
            # Token should expire in ~30 minutes, not 24 hours
            exp_dt = datetime.utcfromtimestamp(payload["exp"])
            diff = exp_dt - datetime.utcnow()
            assert diff < timedelta(minutes=31)
            assert diff > timedelta(minutes=28)


class TestAuthRateLimiting:
    """Test rate limiting on auth endpoint."""

    @pytest.mark.asyncio
    async def test_login_rate_limit_triggers(self):
        """Test hitting login endpoint rapidly triggers 429."""
        limiter.reset()
        app = _make_auth_app()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            responses = []
            for _ in range(7):
                resp = await client.post(
                    "/api/auth/token",
                    data={"username": "admin", "password": "quickpulse"},
                )
                responses.append(resp.status_code)

        # At least one should be 429 (rate limit is 5/minute)
        assert 429 in responses, f"Expected 429 in responses but got: {responses}"
