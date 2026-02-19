"""Tests for /api/chat/* endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from src.api.middleware.rate_limit import setup_rate_limiting
from src.api.routers.auth import create_access_token, router as auth_router
from src.api.routers.chat import router as chat_router
from src.config import DeepSeekConfig


@pytest.fixture
def auth_headers():
    token = create_access_token(data={"sub": "testuser"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_chat_client():
    client = MagicMock()
    client.stream_chat = AsyncMock()
    client.chat = AsyncMock(return_value="```sql\nSELECT 1\n```")
    return client


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute_read = AsyncMock(return_value=[(1,)])
    db._connection = MagicMock()

    # Mock the async context manager for _get_column_names
    mock_cursor = MagicMock()
    mock_cursor.description = [("result",)]
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=False)
    db._connection.execute = MagicMock(return_value=mock_cursor)

    return db


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.deepseek = DeepSeekConfig(api_key="test-key", model="test-model")
    return config


@pytest.fixture
def app_with_chat(mock_chat_client, mock_db, mock_config):
    app = FastAPI()
    setup_rate_limiting(app)
    app.state.chat_client = mock_chat_client
    app.state.chat_providers = {"deepseek": mock_chat_client}
    app.state.active_chat_provider = "deepseek"
    app.state.db = mock_db
    app.state.config = mock_config
    app.include_router(auth_router)
    app.include_router(chat_router)
    return app


@pytest.fixture
def app_without_chat():
    app = FastAPI()
    setup_rate_limiting(app)
    app.state.chat_client = None
    app.state.chat_providers = {}
    app.state.active_chat_provider = None
    app.state.config = MagicMock()
    app.state.config.deepseek = DeepSeekConfig()
    app.include_router(auth_router)
    app.include_router(chat_router)
    return app


class TestChatStatus:
    """Tests for GET /api/chat/status."""

    @pytest.mark.asyncio
    async def test_status_available(self, app_with_chat, auth_headers):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_chat),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/chat/status", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert data["model"] == "test-model"

    @pytest.mark.asyncio
    async def test_status_unavailable(self, app_without_chat, auth_headers):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_without_chat),
            base_url="http://test",
        ) as client:
            resp = await client.get("/api/chat/status", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert data["model"] is None


class TestChatStream:
    """Tests for POST /api/chat/stream."""

    @pytest.mark.asyncio
    async def test_requires_auth(self, app_with_chat):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_chat),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/chat/stream",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_503_when_no_client(self, app_without_chat, auth_headers):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_without_chat),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/chat/stream",
                json={"messages": [{"role": "user", "content": "hi"}]},
                headers=auth_headers,
            )
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_unknown_fields_ignored(self, app_with_chat, auth_headers, mock_chat_client):
        """Extra fields like 'mode' are ignored by Pydantic (no 422)."""
        mock_chat_client.chat = AsyncMock(return_value="No SQL here")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_chat),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "hi"}],
                    "mode": "anything",
                },
                headers=auth_headers,
            )
        # Should not 422 — extra field is just ignored
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_analytics_streams(self, app_with_chat, auth_headers, mock_chat_client):
        """Chat always uses analytics mode (SQL generation)."""
        mock_chat_client.chat = AsyncMock(return_value="No SQL, just a response")

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_chat),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/chat/stream",
                json={"messages": [{"role": "user", "content": "test"}]},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        body = resp.text
        assert '"type": "token"' in body
        assert '"type": "done"' in body

    @pytest.mark.asyncio
    async def test_mto_context_injected(self, app_with_chat, auth_headers, mock_chat_client):
        """When mto_context is provided, MTO number is injected into system prompt."""
        captured_prompts = []

        async def capture_chat(messages, system_prompt):
            captured_prompts.append(system_prompt)
            return "No SQL here"

        mock_chat_client.chat = capture_chat

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_chat),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/chat/stream",
                json={
                    "messages": [{"role": "user", "content": "test"}],
                    "mto_context": {
                        "parent_item": {"mto_number": "AK2510034"},
                        "child_items": [],
                    },
                },
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert len(captured_prompts) == 1
        assert "AK2510034" in captured_prompts[0]
        assert "WHERE mto_number" in captured_prompts[0]
