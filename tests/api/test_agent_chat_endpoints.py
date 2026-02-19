"""Tests for /api/agent-chat/* endpoints."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from src.api.middleware.rate_limit import setup_rate_limiting
from src.api.routers.auth import create_access_token, router as auth_router
from src.api.routers.agent_chat import router as agent_chat_router, _sse_event, _build_mto_context_str
from src.config import DeepSeekConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_headers():
    token = create_access_token(data={"sub": "testuser"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_deepseek_config():
    return DeepSeekConfig(api_key="test-key", model="test-model")


@pytest.fixture
def unavailable_deepseek_config():
    """DeepSeekConfig with no API key — explicitly set to empty string."""
    return DeepSeekConfig(api_key="", model="deepseek-chat")


@pytest.fixture
def mock_mto_config():
    config = MagicMock()
    config.material_classes = []
    config.receipt_sources = {}
    return config


@pytest.fixture
def mock_mto_handler():
    handler = MagicMock()
    handler.query = AsyncMock(return_value=None)
    return handler


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute_read = AsyncMock(return_value=[])
    db.execute_read_with_columns = AsyncMock(return_value=([], []))
    db._connection = MagicMock()
    return db


@pytest.fixture
def app_with_agent_chat(mock_deepseek_config, mock_db, mock_mto_handler, mock_mto_config):
    app = FastAPI()
    setup_rate_limiting(app)

    config = MagicMock()
    config.deepseek = mock_deepseek_config
    app.state.config = config
    app.state.db = mock_db
    app.state.mto_handler = mock_mto_handler
    app.state.mto_config = mock_mto_config

    app.include_router(auth_router)
    app.include_router(agent_chat_router)
    return app


@pytest.fixture
def app_without_deepseek(unavailable_deepseek_config):
    app = FastAPI()
    setup_rate_limiting(app)

    config = MagicMock()
    config.deepseek = unavailable_deepseek_config
    app.state.config = config
    app.state.db = MagicMock()
    app.state.mto_handler = MagicMock()
    app.state.mto_config = MagicMock()

    app.include_router(auth_router)
    app.include_router(agent_chat_router)
    return app


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestSSEEvent:
    """Tests for the _sse_event helper."""

    def test_formats_dict_as_sse(self):
        result = _sse_event({"type": "done"})
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        data = json.loads(result[6:].strip())
        assert data["type"] == "done"

    def test_handles_chinese_text(self):
        result = _sse_event({"type": "token", "content": "入库完成率"})
        assert "入库完成率" in result


class TestBuildMtoContextStr:
    """Tests for _build_mto_context_str helper."""

    def test_with_valid_mto_context(self):
        ctx = {"parent_item": {"mto_number": "AK2510034"}}
        result = _build_mto_context_str(ctx)
        assert "AK2510034" in result

    def test_with_no_parent(self):
        ctx = {"parent_item": None}
        result = _build_mto_context_str(ctx)
        assert result is None

    def test_with_none(self):
        result = _build_mto_context_str(None)
        assert result is None

    def test_with_empty_dict(self):
        result = _build_mto_context_str({})
        assert result is None


# ---------------------------------------------------------------------------
# GET /api/agent-chat/status
# ---------------------------------------------------------------------------


class TestAgentChatStatus:
    """Tests for the status endpoint."""

    @pytest.mark.asyncio
    async def test_status_available(self, app_with_agent_chat, auth_headers):
        mock_agent_config = MagicMock()
        mock_agent_config.is_available.return_value = True
        mock_agent_config.resolve.return_value = DeepSeekConfig(
            api_key="test-key", model="test-model"
        )
        with patch(
            "src.config.AgentLLMConfig",
            return_value=mock_agent_config,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_with_agent_chat),
                base_url="http://test",
            ) as client:
                resp = await client.get("/api/agent-chat/status", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert data["model"] == "test-model"
        assert data["mode"] == "agent"

    @pytest.mark.asyncio
    async def test_status_unavailable(self, app_without_deepseek, auth_headers):
        mock_agent_config = MagicMock()
        mock_agent_config.is_available.return_value = False
        with patch(
            "src.config.AgentLLMConfig",
            return_value=mock_agent_config,
        ):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_without_deepseek),
                base_url="http://test",
            ) as client:
                resp = await client.get("/api/agent-chat/status", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert data["mode"] == "agent"


# ---------------------------------------------------------------------------
# POST /api/agent-chat/stream
# ---------------------------------------------------------------------------


class TestAgentChatStream:
    """Tests for the streaming endpoint."""

    @pytest.mark.asyncio
    async def test_requires_auth(self, app_with_agent_chat):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_with_agent_chat),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/agent-chat/stream",
                json={"messages": [{"role": "user", "content": "test"}]},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_503_when_not_configured(self, app_without_deepseek, auth_headers):
        mock_agent_config = MagicMock()
        mock_agent_config.resolve.return_value = DeepSeekConfig(api_key="", model="")
        with patch("src.config.AgentLLMConfig", return_value=mock_agent_config):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_without_deepseek),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/agent-chat/stream",
                    json={"messages": [{"role": "user", "content": "test"}]},
                    headers=auth_headers,
                )
        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_stream_returns_sse_content_type(self, app_with_agent_chat, auth_headers):
        """The stream endpoint should return text/event-stream."""
        # Patch AgentLLMClient at the source module where it's imported lazily
        with patch("src.agents.base.AgentLLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat_with_tools = AsyncMock(return_value={
                "role": "assistant",
                "content": "Test answer",
                "tool_calls": [],
                "usage": {"total_tokens": 10},
            })
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_with_agent_chat),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/agent-chat/stream",
                    json={"messages": [{"role": "user", "content": "test"}]},
                    headers=auth_headers,
                )

            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_stream_emits_done_event(self, app_with_agent_chat, auth_headers):
        """The SSE stream should always end with a done event."""
        with patch("src.agents.base.AgentLLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat_with_tools = AsyncMock(return_value={
                "role": "assistant",
                "content": "Response",
                "tool_calls": [],
                "usage": {"total_tokens": 10},
            })
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_with_agent_chat),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/agent-chat/stream",
                    json={"messages": [{"role": "user", "content": "hello"}]},
                    headers=auth_headers,
                )

            body = resp.text
            assert '"type": "done"' in body

    @pytest.mark.asyncio
    async def test_stream_with_mto_context(self, app_with_agent_chat, auth_headers):
        """MTO context should be accepted without errors."""
        with patch("src.agents.base.AgentLLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat_with_tools = AsyncMock(return_value={
                "role": "assistant",
                "content": "Answer with context",
                "tool_calls": [],
                "usage": {"total_tokens": 10},
            })
            mock_instance.close = AsyncMock()
            MockClient.return_value = mock_instance

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_with_agent_chat),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/agent-chat/stream",
                    json={
                        "messages": [{"role": "user", "content": "status?"}],
                        "mto_context": {
                            "parent_item": {"mto_number": "AK2510034"},
                        },
                    },
                    headers=auth_headers,
                )

            assert resp.status_code == 200
            body = resp.text
            assert '"type": "done"' in body
