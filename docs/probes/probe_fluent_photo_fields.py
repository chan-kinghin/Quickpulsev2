#!/usr/bin/env python3
"""
Find PRD_MO records where Fluent's custom photo fields are populated.

From View(PRD_MO) on DK251003S we discovered these custom fields on TreeEntity:
  F_QWJI_YSTP1, F_QWJI_YSTP2, F_QWJI_YSTP3   — 原始图片 1/2/3
  F_QWJI_YSWZFJ, F_QWJI_YSWZFJ_Files         — 原始物资附件 / file list
  F_QWJI_YSFJ                                 — 原始附件
  F_QWJI_MS, F_QWJI_MS2                       — 描述

Probe strategy:
1. Query PRD_MO with each field key (ExecuteBillQuery uses entity_field naming).
2. Scan 2000 recent orders for any with non-empty values.
3. Surface one or two examples for the user to verify in the UI.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from k3cloud_webapi_sdk.main import K3CloudApiSdk

OUTPUT_DIR = PROJECT_ROOT / "scripts" / "_probe_output"
OUTPUT_DIR.mkdir(exist_ok=True)


# Each TreeEntity-level custom field, with the ExecuteBillQuery alias
# Kingdee accepts both raw names and entity_FIELD style; we try both.
PHOTO_FIELDS = [
    "FF_QWJI_YSTP1",
    "FF_QWJI_YSTP2",
    "FF_QWJI_YSTP3",
    "FF_QWJI_YSWZFJ",
    "FF_QWJI_YSFJ",
    "FF_QWJI_MS",
    "FF_QWJI_MS2",
    # Try also without leading F:
    "F_QWJI_YSTP1",
    "F_QWJI_YSTP2",
    "F_QWJI_YSTP3",
    "F_QWJI_YSWZFJ",
    "F_QWJI_YSFJ",
    # Try entity-prefixed:
    "FTreeEntity_F_QWJI_YSTP1",
]


def init_sdk() -> K3CloudApiSdk:
    sdk = K3CloudApiSdk(os.environ["KINGDEE_SERVER_URL"])
    sdk.InitConfig(
        acct_id=os.environ["KINGDEE_ACCT_ID"],
        user_name=os.environ["KINGDEE_USER_NAME"],
        app_id=os.environ["KINGDEE_APP_ID"],
        app_secret=os.environ["KINGDEE_APP_SEC"],
        server_url=os.environ["KINGDEE_SERVER_URL"],
        lcid=int(os.environ.get("KINGDEE_LCID", 2052)),
    )
    return sdk


def is_error_row(row) -> tuple[bool, str | None]:
    if isinstance(row, dict) and "Result" in row:
        err = row.get("Result", {}).get("ResponseStatus", {}).get("Errors", [{}])
        return True, err[0].get("Message") if err else None
    if isinstance(row, list) and row and isinstance(row[0], dict) and "Result" in row[0]:
        err = row[0].get("Result", {}).get("ResponseStatus", {}).get("Errors", [{}])
        return True, err[0].get("Message") if err else None
    return False, None


def probe_field(sdk: K3CloudApiSdk, field: str) -> str:
    """Check if Kingdee accepts this field name on PRD_MO."""
    params = {
        "FormId": "PRD_MO",
        "FieldKeys": f"FBillNo,{field}",
        "Limit": 1,
    }
    try:
        resp = sdk.ExecuteBillQuery(params)
        if not resp:
            return "empty"
        parsed = json.loads(resp) if isinstance(resp, str) else resp
        if not parsed:
            return "empty"
        row = parsed[0]
        is_err, msg = is_error_row(row)
        if is_err:
            if msg and "不存在" in msg:
                return "field-not-found"
            return f"error: {msg}"
        return "accepted"
    except Exception as e:
        return f"exception: {e}"


def scan_for_populated(sdk: K3CloudApiSdk, fields: list[str], limit: int = 2000) -> list[dict]:
    keys = "FBillNo,FId,FMTONo,FDate," + ",".join(fields)
    params = {
        "FormId": "PRD_MO",
        "FieldKeys": keys,
        "OrderString": "FDate desc",
        "Limit": limit,
    }
    resp = sdk.ExecuteBillQuery(params)
    parsed = json.loads(resp) if isinstance(resp, str) else resp
    if not isinstance(parsed, list):
        return []
    n_meta = 4  # FBillNo, FId, FMTONo, FDate
    hits = []
    for row in parsed:
        is_err, msg = is_error_row(row)
        if is_err:
            print(f"  ! scan error: {msg}")
            return []
        if not isinstance(row, list) or len(row) < n_meta + len(fields):
            continue
        bill_no, fid, mto, dt = row[0], row[1], row[2], row[3]
        photo_vals = dict(zip(fields, row[n_meta:]))
        non_empty = {k: v for k, v in photo_vals.items() if v not in (None, "", " ", [], 0, False)}
        if non_empty:
            hits.append({
                "bill_no": bill_no,
                "fid": fid,
                "mto": mto,
                "date": dt,
                "populated": non_empty,
            })
    return hits


def main():
    sdk = init_sdk()

    # Phase 1: figure out which field-name conventions Kingdee accepts
    print("="*70)
    print("Phase 1: probe each Fluent-custom photo field name")
    print("="*70)
    accepted = []
    for f in PHOTO_FIELDS:
        status = probe_field(sdk, f)
        mark = "✓" if status == "accepted" else " "
        if status == "field-not-found":
            continue  # silent
        print(f"  {mark} {f:35s} → {status}")
        if status == "accepted":
            accepted.append(f)

    if not accepted:
        print("\n✗ No photo fields accepted by ExecuteBillQuery — they may only be reachable via View().")
        return

    # Phase 2: scan 2000 most-recent PRD_MO for populated photo fields
    print(f"\n{'='*70}\nPhase 2: scan 2000 most-recent PRD_MO for populated photo fields\n{'='*70}")
    print(f"  Fields scanned: {accepted}")
    hits = scan_for_populated(sdk, accepted, limit=2000)
    print(f"\n  Orders with ≥1 populated photo field: {len(hits)}")
    for h in hits[:10]:
        print(f"\n  • Bill {h['bill_no']}  MTO {h['mto']}  date {h['date']}")
        for k, v in h["populated"].items():
            preview = str(v)
            if len(preview) > 100:
                preview = preview[:97] + "..."
            print(f"      {k} = {preview}")

    out = OUTPUT_DIR / "fluent_photo_field_hits.json"
    out.write_text(json.dumps({"accepted_fields": accepted, "hits": hits}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ Saved → {out}")


if __name__ == "__main__":
    main()
