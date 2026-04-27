"""Tests for src/api/middleware/ — access_log and rate_limit."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.middleware.access_log import _get_client_ip, _write_log
from src.api.middleware.rate_limit import (
    custom_rate_limit_handler,
    limiter,
    setup_rate_limiting,
)


# ---------------------------------------------------------------------------
# _get_client_ip
# ---------------------------------------------------------------------------

class TestGetClientIP:
    """Tests for IP extraction from request."""

    def _make_request(self, headers=None, client_host=None):
        request = MagicMock()
        request.headers = headers or {}
        if client_host:
            request.client = MagicMock()
            request.client.host = client_host
        else:
            request.client = None
        return request

    def test_xff_single_ip(self):
        req = self._make_request(headers={"x-forwarded-for": "1.2.3.4"})
        assert _get_client_ip(req) == "1.2.3.4"

    def test_xff_multiple_ips_takes_first(self):
        req = self._make_request(
            headers={"x-forwarded-for": "10.0.0.1, 192.168.1.1, 172.16.0.1"}
        )
        assert _get_client_ip(req) == "10.0.0.1"

    def test_xff_with_whitespace(self):
        req = self._make_request(
            headers={"x-forwarded-for": "  203.0.113.50  , 10.0.0.1"}
        )
        assert _get_client_ip(req) == "203.0.113.50"

    def test_no_xff_uses_client_host(self):
        req = self._make_request(client_host="127.0.0.1")
        assert _get_client_ip(req) == "127.0.0.1"

    def test_no_xff_no_client_returns_unknown(self):
        req = self._make_request()
        assert _get_client_ip(req) == "unknown"

    def test_xff_takes_precedence_over_client(self):
        req = self._make_request(
            headers={"x-forwarded-for": "8.8.8.8"}, client_host="127.0.0.1"
        )
        assert _get_client_ip(req) == "8.8.8.8"


# ---------------------------------------------------------------------------
# _write_log
# ---------------------------------------------------------------------------

class TestWriteLog:
    """Tests for background log writing."""

    @pytest.mark.asyncio
    async def test_write_log_calls_execute_write(self):
        db = MagicMock()
        db.execute_write = AsyncMock()

        await _write_log(db, "1.2.3.4", "GET", "/api/mto/X", 200, 12.345, "Mozilla/5.0")

        db.execute_write.assert_called_once()
        args = db.execute_write.call_args
        params = args[0][1]
        assert params[0] == "1.2.3.4"
        assert params[1] == "GET"
        assert params[2] == "/api/mto/X"
        assert params[3] == 200
        assert params[4] == 12.35  # rounded to 2 decimals
        assert params[5] == "Mozilla/5.0"

    @pytest.mark.asyncio
    async def test_write_log_swallows_exceptions(self):
        db = MagicMock()
        db.execute_write = AsyncMock(side_effect=RuntimeError("DB locked"))

        # Should not raise
        await _write_log(db, "1.2.3.4", "GET", "/", 500, 0.0, None)

    @pytest.mark.asyncio
    async def test_write_log_none_user_agent(self):
        db = MagicMock()
        db.execute_write = AsyncMock()

        await _write_log(db, "1.2.3.4", "POST", "/api/sync", 201, 100.0, None)

        params = db.execute_write.call_args[0][1]
        assert params[5] is None


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    """Tests for rate limiter configuration."""

    def test_limiter_exists(self):
        assert limiter is not None

    def test_setup_rate_limiting_attaches_to_app(self):
        app = MagicMock()
        app.state = MagicMock()

        result = setup_rate_limiting(app)

        assert result is limiter
        assert app.state.limiter is limiter
        app.add_exception_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_custom_rate_limit_handler_returns_429(self):
        request = MagicMock()
        exc = MagicMock()

        response = await custom_rate_limit_handler(request, exc)

        assert response.status_code == 429
        # Check body contains expected keys
        import json
        body = json.loads(response.body.decode())
        assert body["error_code"] == "rate_limited"
        assert "Rate limit" in body["detail"]
