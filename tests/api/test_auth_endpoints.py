"""Tests for /api/auth/* endpoints."""

import httpx
import pytest
from fastapi import FastAPI
from jose import jwt

from src.api.middleware.rate_limit import setup_rate_limiting
from src.api.routers.auth import router as auth_router, SECRET_KEY, ALGORITHM


@pytest.fixture
def app_with_auth():
    """Create app with auth router and rate limiting."""
    app = FastAPI()
    setup_rate_limiting(app)
    app.include_router(auth_router)
    return app


class TestLoginEndpoint:
    """Tests for POST /api/auth/token."""

    @pytest.mark.asyncio
    async def test_login_success(self, app_with_auth):
        """Test successful login returns JWT token."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_auth),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/auth/token",
                data={"username": "testuser", "password": "quickpulse"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

        # Verify token is valid JWT
        payload = jwt.decode(data["access_token"], SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "testuser"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, app_with_auth):
        """Test login with wrong password returns 401."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_auth),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/auth/token",
                data={"username": "testuser", "password": "wrongpassword"},
            )

        assert response.status_code == 401
        assert "incorrect" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_empty_password(self, app_with_auth):
        """Test login with empty password fails validation."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_auth),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/auth/token",
                data={"username": "testuser", "password": ""},
            )

        # OAuth2PasswordRequestForm requires non-empty password
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, app_with_auth):
        """Test login without required fields returns 422."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_auth),
            base_url="http://test",
        ) as client:
            # Missing password
            response = await client.post(
                "/api/auth/token",
                data={"username": "testuser"},
            )
            assert response.status_code == 422

            # Missing username
            response = await client.post(
                "/api/auth/token",
                data={"password": "quickpulse"},
            )
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_login_any_username_allowed(self, app_with_auth):
        """Test any username is accepted with correct password."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_auth),
            base_url="http://test",
        ) as client:
            # Login with different usernames
            for username in ["admin", "user1", "test@example.com"]:
                response = await client.post(
                    "/api/auth/token",
                    data={"username": username, "password": "quickpulse"},
                )

                assert response.status_code == 200
                payload = jwt.decode(
                    response.json()["access_token"],
                    SECRET_KEY,
                    algorithms=[ALGORITHM],
                )
                assert payload["sub"] == username

    @pytest.mark.asyncio
    async def test_login_token_has_expiry(self, app_with_auth):
        """Test token has expiry claim."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_auth),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/auth/token",
                data={"username": "testuser", "password": "quickpulse"},
            )

        assert response.status_code == 200
        token = response.json()["access_token"]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        assert "exp" in payload

    @pytest.mark.asyncio
    async def test_login_content_type(self, app_with_auth):
        """Test login requires form data, not JSON."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_auth),
            base_url="http://test",
        ) as client:
            # JSON body should fail (needs form data)
            response = await client.post(
                "/api/auth/token",
                json={"username": "testuser", "password": "quickpulse"},
            )

        # Should fail because OAuth2PasswordRequestForm expects form data
        assert response.status_code == 422


class TestTokenValidation:
    """Tests for token validation behavior."""

    @pytest.mark.asyncio
    async def test_valid_token_format(self, app_with_auth):
        """Test token is proper JWT format (3 parts)."""
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_auth),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/auth/token",
                data={"username": "testuser", "password": "quickpulse"},
            )

        token = response.json()["access_token"]
        parts = token.split(".")

        # JWT has 3 parts: header.payload.signature
        assert len(parts) == 3

    @pytest.mark.asyncio
    async def test_token_uses_hs256(self, app_with_auth):
        """Test token uses HS256 algorithm."""
        import base64
        import json

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_auth),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/auth/token",
                data={"username": "testuser", "password": "quickpulse"},
            )

        token = response.json()["access_token"]
        header_b64 = token.split(".")[0]

        # Add padding if needed
        padded = header_b64 + "=" * (4 - len(header_b64) % 4)
        header = json.loads(base64.urlsafe_b64decode(padded))

        assert header["alg"] == "HS256"
