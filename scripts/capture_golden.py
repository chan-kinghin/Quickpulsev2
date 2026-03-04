#!/usr/bin/env python3
"""Capture golden-file snapshots from a running QuickPulse server.

Usage:
    python scripts/capture_golden.py AK2510034 --url http://localhost:8000
    python scripts/capture_golden.py AK2510034 AK2512059 --url https://fltpulse.szfluent.cn
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError


GOLDEN_DIR = Path(__file__).parent.parent / "tests" / "golden"


def get_auth_token(base_url: str) -> str:
    """Get OAuth2 token from the server."""
    token_url = f"{base_url}/api/auth/token"
    data = b"username=admin&password=quickpulse"
    req = Request(token_url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urlopen(req, timeout=10) as resp:
            token_data = json.loads(resp.read())
            return token_data["access_token"]
    except (HTTPError, URLError, KeyError) as exc:
        print(f"Warning: Could not get auth token: {exc}", file=sys.stderr)
        print("Trying without authentication...", file=sys.stderr)
        return ""


def capture(mto_number: str, base_url: str, token: str) -> dict:
    """Query the API and return normalized response."""
    url = f"{base_url}/api/mto/{mto_number}"
    req = Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    # Normalize volatile fields
    data.pop("query_time", None)
    data.pop("cache_age_seconds", None)
    data["_captured_at"] = datetime.utcnow().isoformat()
    data["_source_url"] = base_url
    return data


def main():
    parser = argparse.ArgumentParser(description="Capture golden-file snapshots")
    parser.add_argument("mto_numbers", nargs="+", help="MTO numbers to capture")
    parser.add_argument("--url", default="http://localhost:8000", help="Server URL")
    args = parser.parse_args()

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    token = get_auth_token(args.url)

    for mto in args.mto_numbers:
        try:
            data = capture(mto, args.url, token)
            children = data.get("child_items", data.get("children", []))
            output = GOLDEN_DIR / f"{mto}.json"
            output.write_text(
                json.dumps(data, indent=2, ensure_ascii=False, default=str)
            )
            print(f"Captured {mto} -> {output} ({len(children)} children)")
        except HTTPError as exc:
            print(f"Error capturing {mto}: HTTP {exc.code} - {exc.reason}", file=sys.stderr)
        except URLError as exc:
            print(f"Error capturing {mto}: {exc.reason}", file=sys.stderr)


if __name__ == "__main__":
    main()
