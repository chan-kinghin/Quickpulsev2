#!/usr/bin/env python3
"""Reconcile cache vs live MTO query results.

Queries the QuickPulse API for each MTO number twice — once with
``source=cache`` and once with ``source=live`` — and compares the
responses to detect discrepancies between cached and live data.

Usage:
    python scripts/reconcile.py AK2510034 AK2512059 --url http://localhost:8000
    python scripts/reconcile.py --url https://fltpulse.szfluent.cn --random 5
    python scripts/reconcile.py AK2510034 --url http://localhost:8000 --output json
"""

import argparse
import json
import sys
from typing import Dict, List

import requests

from reconcile_report import (
    Difference,
    Severity,
    compare_responses,
    format_report,
)


def _get_auth_token(base_url: str) -> str:
    """Obtain a Bearer token via OAuth2 password flow."""
    resp = requests.post(
        f"{base_url}/api/auth/token",
        data={"username": "admin", "password": "quickpulse"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _fetch_mto(base_url: str, mto_number: str, token: str, source: str) -> dict:
    """Fetch a single MTO status from the API.

    Args:
        source: 'cache' or 'live' — passed as ?source= query parameter.
    """
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(
        f"{base_url}/api/mto/{mto_number}",
        params={"source": source},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _diff_to_dict(d: Difference) -> dict:
    """Serialize a Difference to a JSON-friendly dict."""
    return {
        "mto_number": d.mto_number,
        "material_code": d.material_code,
        "aux_attributes": d.aux_attributes,
        "field_name": d.field_name,
        "cache_value": d.cache_value,
        "live_value": d.live_value,
        "severity": d.severity.value,
        "description": d.description,
    }


def reconcile(
    mto_numbers: List[str],
    base_url: str,
) -> Dict[str, List[Difference]]:
    """Run reconciliation for a list of MTO numbers.

    Fetches each MTO twice: once with source=cache (cache-only path) and
    once with source=live (live Kingdee API path), then compares them.
    """
    token = _get_auth_token(base_url)
    all_diffs: Dict[str, List[Difference]] = {}

    for mto in mto_numbers:
        print(f"  Checking {mto} ...", end=" ", flush=True)
        try:
            cache_resp = _fetch_mto(base_url, mto, token, source="cache")
            live_resp = _fetch_mto(base_url, mto, token, source="live")
            diffs = compare_responses(cache_resp, live_resp, mto)
            all_diffs[mto] = diffs
            status = f"{len(diffs)} diff(s)" if diffs else "OK"
            print(status)
        except requests.HTTPError as exc:
            print(f"HTTP error: {exc.response.status_code}")
            all_diffs[mto] = []
        except requests.ConnectionError:
            print("connection failed")
            all_diffs[mto] = []

    return all_diffs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconcile cache vs live MTO query results."
    )
    parser.add_argument(
        "mto_numbers",
        nargs="*",
        help="MTO numbers to check (e.g. AK2510034 AK2512059)",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Server base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--output",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--random",
        type=int,
        default=0,
        metavar="N",
        help="Pick N random MTOs from the database (not yet implemented)",
    )
    args = parser.parse_args()

    mto_numbers: List[str] = list(args.mto_numbers)

    if args.random > 0:
        # TODO: Query /api/sync/status or a dedicated endpoint to get
        # random MTO numbers from the database once that endpoint exists.
        print(
            f"--random {args.random} requested but not yet implemented. "
            "Please provide MTO numbers as positional arguments.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not mto_numbers:
        parser.error("No MTO numbers provided. Pass them as arguments or use --random N.")

    print(f"Reconciling {len(mto_numbers)} MTO(s) against {args.url} ...")
    all_diffs = reconcile(mto_numbers, args.url)

    if args.output == "json":
        json_out = {
            mto: [_diff_to_dict(d) for d in diffs]
            for mto, diffs in all_diffs.items()
        }
        print(json.dumps(json_out, indent=2, ensure_ascii=False))
    else:
        print()
        print(format_report(all_diffs))

    # Exit code: 1 if any critical diffs found
    all_flat = [d for ds in all_diffs.values() for d in ds]
    critical = sum(1 for d in all_flat if d.severity == Severity.CRITICAL)
    sys.exit(1 if critical > 0 else 0)


if __name__ == "__main__":
    main()
