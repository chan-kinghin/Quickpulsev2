"""IP geolocation utility for admin analytics.

Uses ipaddress stdlib for private/local detection and a lightweight
HTTP lookup (ip-api.com) with LRU caching for public IPs.
All results are in Chinese. Never raises exceptions.
"""

import ipaddress
import logging
from functools import lru_cache
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_UNKNOWN = {
    "country": "未知",
    "region": "",
    "city": "",
    "isp": "",
    "location_display": "未知",
}

_LOCAL = {
    "country": "本地",
    "region": "",
    "city": "",
    "isp": "",
    "location_display": "本地",
}

_LAN = {
    "country": "局域网",
    "region": "",
    "city": "",
    "isp": "",
    "location_display": "局域网",
}

# Shared httpx client for connection pooling
_http_client: Optional[httpx.Client] = None


def _get_http_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=3.0)
    return _http_client


def _is_localhost(ip_str: str) -> bool:
    return ip_str in ("127.0.0.1", "::1", "localhost")


def _is_private(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        return addr.is_private or addr.is_reserved or addr.is_link_local
    except ValueError:
        return False


def _query_ip_api(ip_str: str) -> dict:
    """Query ip-api.com free endpoint. Returns parsed dict or _UNKNOWN."""
    try:
        client = _get_http_client()
        # ip-api.com free tier: 45 req/min, supports lang=zh-CN
        resp = client.get(
            f"http://ip-api.com/json/{ip_str}",
            params={"lang": "zh-CN", "fields": "status,country,regionName,city,isp"},
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "success":
            return _UNKNOWN.copy()

        country = data.get("country", "未知")
        region = data.get("regionName", "")
        city = data.get("city", "")
        isp = data.get("isp", "")

        parts = [p for p in [country, region, city] if p]
        location_display = " ".join(parts) if parts else "未知"

        return {
            "country": country,
            "region": region,
            "city": city,
            "isp": isp,
            "location_display": location_display,
        }
    except Exception:
        logger.debug("IP geolocation lookup failed for %s", ip_str, exc_info=True)
        return _UNKNOWN.copy()


@lru_cache(maxsize=1024)
def lookup_ip(ip_str: str) -> dict:
    """Look up geographic location for an IP address.

    Returns a dict with keys: country, region, city, isp, location_display.
    All values are in Chinese. Never raises exceptions.
    """
    if not ip_str or not isinstance(ip_str, str):
        return _UNKNOWN.copy()

    ip_str = ip_str.strip()

    if _is_localhost(ip_str):
        return _LOCAL.copy()

    if _is_private(ip_str):
        return _LAN.copy()

    # Validate it's a real IP before making a network call
    try:
        ipaddress.ip_address(ip_str)
    except ValueError:
        return _UNKNOWN.copy()

    return _query_ip_api(ip_str)


def lookup_ip_display(ip_str: str) -> str:
    """Convenience function that returns only the display string."""
    return lookup_ip(ip_str).get("location_display", "未知")
