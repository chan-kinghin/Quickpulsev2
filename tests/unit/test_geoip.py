"""Tests for src/utils/geoip.py"""

from unittest.mock import MagicMock, patch

import pytest

from src.utils.geoip import lookup_ip, lookup_ip_display


# Clear the LRU cache before each test to avoid cross-test pollution
@pytest.fixture(autouse=True)
def _clear_lru_cache():
    lookup_ip.cache_clear()
    yield
    lookup_ip.cache_clear()


def _mock_ip_api_response(country="中国", region="广东省", city="深圳", isp="电信"):
    """Build a fake ip-api.com JSON response."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "status": "success",
        "country": country,
        "regionName": region,
        "city": city,
        "isp": isp,
    }
    return resp


class TestLookupPublicIP:
    """Tests for public IP lookups (mocked HTTP)."""

    @patch("src.utils.geoip._get_http_client")
    def test_lookup_known_ip(self, mock_client_fn):
        """A well-known public IP returns a dict with expected keys."""
        client = MagicMock()
        client.get.return_value = _mock_ip_api_response(
            country="美国", region="加利福尼亚", city="洛杉矶", isp="Google LLC"
        )
        mock_client_fn.return_value = client

        result = lookup_ip("8.8.8.8")

        assert isinstance(result, dict)
        for key in ("country", "region", "city", "isp", "location_display"):
            assert key in result
        assert result["country"] == "美国"
        assert "美国" in result["location_display"]

    @patch("src.utils.geoip._get_http_client")
    def test_lookup_chinese_ip(self, mock_client_fn):
        """A known Chinese IP returns Chinese location text."""
        client = MagicMock()
        client.get.return_value = _mock_ip_api_response(
            country="中国", region="广东省", city="深圳", isp="电信"
        )
        mock_client_fn.return_value = client

        result = lookup_ip("1.2.4.8")

        assert result["country"] == "中国"
        assert "中国" in result["location_display"]
        assert "广东省" in result["location_display"]


class TestPrivateIPs:
    """Tests for private / RFC-1918 addresses."""

    def test_private_ip_192(self):
        """192.168.1.1 is detected as LAN."""
        result = lookup_ip("192.168.1.1")
        assert result["location_display"] == "局域网"

    def test_private_ip_10(self):
        """10.0.0.1 is detected as LAN."""
        result = lookup_ip("10.0.0.1")
        assert result["location_display"] == "局域网"

    def test_private_ip_172(self):
        """172.16.0.1 is detected as LAN."""
        result = lookup_ip("172.16.0.1")
        assert result["location_display"] == "局域网"


class TestLocalhost:
    """Tests for localhost addresses."""

    def test_localhost_127(self):
        """127.0.0.1 returns local marker."""
        result = lookup_ip("127.0.0.1")
        assert result["location_display"] == "本地"

    def test_localhost_ipv6(self):
        """::1 returns local marker."""
        result = lookup_ip("::1")
        assert result["location_display"] == "本地"


class TestEdgeCases:
    """Tests for unknown, invalid, and empty inputs."""

    def test_unknown_ip_string(self):
        """The literal string 'unknown' returns fallback."""
        result = lookup_ip("unknown")
        assert result["location_display"] == "未知"

    def test_invalid_ip(self):
        """Garbage string does not raise and returns fallback."""
        result = lookup_ip("not-an-ip-address")
        assert isinstance(result, dict)
        assert result["location_display"] == "未知"

    def test_empty_string(self):
        """Empty string does not raise and returns fallback."""
        result = lookup_ip("")
        assert isinstance(result, dict)
        assert result["location_display"] == "未知"

    def test_none_input(self):
        """None input does not raise and returns fallback."""
        result = lookup_ip(None)
        assert result["location_display"] == "未知"


class TestReturnShape:
    """Verify the structure of returned dicts."""

    def test_return_dict_keys(self):
        """Return dict always has the expected keys."""
        result = lookup_ip("127.0.0.1")
        expected_keys = {"country", "region", "city", "isp", "location_display"}
        assert set(result.keys()) == expected_keys

    def test_return_dict_keys_for_unknown(self):
        """Unknown input also has all expected keys."""
        result = lookup_ip("garbage")
        expected_keys = {"country", "region", "city", "isp", "location_display"}
        assert set(result.keys()) == expected_keys


class TestCaching:
    """Verify LRU cache behavior."""

    @patch("src.utils.geoip._get_http_client")
    def test_cache_hit(self, mock_client_fn):
        """Calling lookup twice with same IP uses cache (only one HTTP call)."""
        client = MagicMock()
        client.get.return_value = _mock_ip_api_response()
        mock_client_fn.return_value = client

        result1 = lookup_ip("8.8.4.4")
        result2 = lookup_ip("8.8.4.4")

        assert result1 == result2
        # The HTTP client's get method should only be called once
        assert client.get.call_count == 1


class TestDisplayConvenience:
    """Tests for the lookup_ip_display shortcut."""

    def test_display_localhost(self):
        """lookup_ip_display returns the display string directly."""
        assert lookup_ip_display("127.0.0.1") == "本地"

    def test_display_private(self):
        assert lookup_ip_display("192.168.0.1") == "局域网"

    def test_display_unknown(self):
        assert lookup_ip_display("") == "未知"
