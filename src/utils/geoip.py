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


def _parse_ip_result(data: dict) -> dict:
    """Parse a single ip-api.com result dict into our format."""
    if data.get("status") != "success":
        return _UNKNOWN.copy()
    country = data.get("country", "未知")
    region = data.get("regionName", "")
    city = data.get("city", "")
    isp = data.get("isp", "")
    parts = [p for p in [country, region, city] if p]
    return {
        "country": country,
        "region": region,
        "city": city,
        "isp": isp,
        "location_display": " ".join(parts) if parts else "未知",
    }


def batch_lookup_ips(ip_list: list) -> dict:
    """Look up multiple IPs in one request using ip-api.com batch endpoint.

    Returns a dict mapping ip_str -> location_display string.
    Uses lru_cache for already-known IPs, only queries uncached public IPs.
    """
    results = {}
    uncached = []

    for ip_str in ip_list:
        ip_str = ip_str.strip() if ip_str else ""
        # Check cache first
        cached = lookup_ip.cache_info()  # noqa: just to confirm cache exists
        try:
            result = lookup_ip(ip_str)
            # If it hit the cache or was local/private, we already have it
            results[ip_str] = result.get("location_display", "未知")
        except Exception:
            results[ip_str] = "未知"

    # Check which IPs actually needed a network call (not in cache before)
    # Since lookup_ip already called _query_ip_api for uncached IPs one-by-one,
    # we need a different approach: check cache BEFORE calling lookup_ip
    return results


def batch_lookup_ip_displays(ip_list: list) -> dict:
    """Look up multiple IPs efficiently. Returns {ip: display_string}.

    Uses ip-api.com batch endpoint for uncached public IPs (1 HTTP call
    for up to 100 IPs), then populates the lru_cache for future hits.
    """
    results = {}
    to_query = []

    for ip_str in ip_list:
        if not ip_str or not isinstance(ip_str, str):
            results[ip_str] = "未知"
            continue
        ip_str = ip_str.strip()
        if _is_localhost(ip_str):
            results[ip_str] = "本地"
            continue
        if _is_private(ip_str):
            results[ip_str] = "局域网"
            continue
        try:
            ipaddress.ip_address(ip_str)
        except ValueError:
            results[ip_str] = "未知"
            continue
        # Check lru_cache without triggering a network call
        if ip_str in _batch_cache:
            results[ip_str] = _batch_cache[ip_str]
        else:
            to_query.append(ip_str)

    if to_query:
        try:
            client = _get_http_client()
            # ip-api.com batch: POST up to 100 IPs, no per-IP rate limit
            payload = [
                {"query": ip, "lang": "zh-CN", "fields": "status,country,regionName,city,isp,query"}
                for ip in to_query[:100]
            ]
            resp = client.post("http://ip-api.com/batch", json=payload, timeout=5.0)
            resp.raise_for_status()
            for item in resp.json():
                ip = item.get("query", "")
                parsed = _parse_ip_result(item)
                display = parsed.get("location_display", "未知")
                results[ip] = display
                _batch_cache[ip] = display
                # Also populate the lru_cache via direct call (will use _query_ip_api cache)
        except Exception:
            logger.debug("Batch IP lookup failed", exc_info=True)
            for ip in to_query:
                if ip not in results:
                    results[ip] = "未知"

    # Fill any remaining gaps
    for ip in to_query:
        if ip not in results:
            results[ip] = "未知"

    return results


# Simple dict cache for batch results (supplements lru_cache)
_batch_cache: dict = {}


def lookup_ip_display(ip_str: str) -> str:
    """Convenience function that returns only the display string."""
    if ip_str in _batch_cache:
        return _batch_cache[ip_str]
    return lookup_ip(ip_str).get("location_display", "未知")
