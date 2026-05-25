#!/usr/bin/env python3
"""
Probe BOS-attachment hook on order-level forms.

You confirmed photos exist in the K3Cloud web UI tied to orders.
This script identifies WHICH field key surfaces those attachments via
ExecuteBillQuery, on each candidate form.

Strategy per form (PRD_MO, SAL_SaleOrder, PUR_PurchaseOrder, SUB_POORDER):
1. Try each candidate field key alone, see which the form accepts.
2. For accepted keys, scan recent docs for any non-zero / non-empty value.
3. Save first hit as (FormId, FInternalId, FBillNo) for follow-up download.
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


# Candidate attachment field keys we'll try on each form.
# Kingdee uses several conventions across versions/tenants.
ATTACHMENT_FIELD_CANDIDATES = [
    "FATTACHMENTS",
    "FAttachments",
    "FAttachmentCount",
    "F_ATTACHMENTS",
    "FAttachmentField",
    "FAttachmentSign",   # newer K3Cloud — boolean "has attachments"
    "FHASATTACH",
    "FHasAttach",
    "FAttachCount",
]

# Forms to test
FORMS_TO_TEST = [
    ("PRD_MO", "FBillNo"),
    ("SAL_SaleOrder", "FBillNo"),
    ("PUR_PurchaseOrder", "FBillNo"),
    ("SUB_POORDER", "FBillNo"),
    ("STK_InStock", "FBillNo"),
    ("PRD_INSTOCK", "FBillNo"),
]


def is_error_packet(row) -> tuple[bool, str | None]:
    """Detect Kingdee's error-wrapped response shape."""
    if isinstance(row, dict) and "Result" in row:
        err = row.get("Result", {}).get("ResponseStatus", {}).get("Errors", [])
        msg = err[0].get("Message") if err else None
        return True, msg
    return False, None


def probe_field_on_form(sdk: K3CloudApiSdk, form_id: str, field: str) -> dict:
    """Return {"accepted": bool, "sample": value_or_None, "error": str_or_None}."""
    params = {
        "FormId": form_id,
        "FieldKeys": f"FBillNo,{field}",
        "Limit": 1,
    }
    try:
        resp = sdk.ExecuteBillQuery(params)
        if not resp:
            return {"accepted": True, "sample": None, "error": "empty"}
        parsed = json.loads(resp) if isinstance(resp, str) else resp
        if not isinstance(parsed, list) or not parsed:
            return {"accepted": False, "error": f"unexpected shape: {type(parsed).__name__}"}
        row = parsed[0]
        is_err, msg = is_error_packet(row)
        if is_err:
            # "字段不存在" → field doesn't exist on this form
            if msg and "不存在" in msg:
                return {"accepted": False, "error": "field-not-found"}
            return {"accepted": False, "error": msg or "unknown error"}
        if isinstance(row, list):
            return {"accepted": True, "sample": row}
        return {"accepted": False, "error": "weird row shape"}
    except Exception as e:
        return {"accepted": False, "error": str(e)[:200]}


def find_doc_with_attachment(sdk: K3CloudApiSdk, form_id: str, field: str, limit: int = 500) -> list:
    """Pull `limit` recent docs and report any where attachment field is non-empty."""
    params = {
        "FormId": form_id,
        "FieldKeys": f"FBillNo,FId,{field}",
        "OrderString": "FId desc",
        "Limit": limit,
    }
    try:
        resp = sdk.ExecuteBillQuery(params)
        if not resp:
            return []
        parsed = json.loads(resp) if isinstance(resp, str) else resp
        if not isinstance(parsed, list):
            return []
        with_attach = []
        for row in parsed:
            is_err, _ = is_error_packet(row)
            if is_err:
                continue
            if not isinstance(row, list) or len(row) < 3:
                continue
            bill_no, fid, attach = row[0], row[1], row[2]
            # Different field types: int count, bool flag, JSON list, string
            has = False
            if isinstance(attach, bool):
                has = attach
            elif isinstance(attach, (int, float)):
                has = attach > 0
            elif isinstance(attach, str):
                has = bool(attach.strip())
            elif isinstance(attach, list):
                has = len(attach) > 0
            elif attach not in (None, "", " "):
                has = True
            if has:
                with_attach.append({"bill_no": bill_no, "fid": fid, "attach_value": attach})
        return with_attach
    except Exception as e:
        return [{"_error": str(e)[:200]}]


def main():
    sdk = init_sdk()
    findings = {}

    for form_id, _ in FORMS_TO_TEST:
        print(f"\n{'='*70}\nForm: {form_id}\n{'='*70}")
        accepted_fields = []
        for field in ATTACHMENT_FIELD_CANDIDATES:
            r = probe_field_on_form(sdk, form_id, field)
            mark = "✓" if r["accepted"] else " "
            err = r.get("error") or ""
            sample = r.get("sample")
            if r["accepted"]:
                accepted_fields.append(field)
                print(f"  {mark} {field:25s} accepted — sample={sample}")
            elif err == "field-not-found":
                pass  # silent
            else:
                print(f"    {field:25s} → {err[:80]}")

        if accepted_fields:
            print(f"\n  Accepted attachment fields: {accepted_fields}")
            # For each accepted field, scan 500 recent docs for non-empty values
            for field in accepted_fields:
                hits = find_doc_with_attachment(sdk, form_id, field, limit=500)
                hits_clean = [h for h in hits if "_error" not in h]
                errs = [h for h in hits if "_error" in h]
                if errs:
                    print(f"\n  ! Scan error for {field}: {errs[0]['_error']}")
                else:
                    print(f"\n  Scanned 500 docs; {len(hits_clean)} have non-empty {field}")
                    for h in hits_clean[:5]:
                        print(f"      • {h}")
                findings.setdefault(form_id, {})[field] = hits_clean[:20]
        else:
            print(f"\n  ✗ No attachment field key accepted on {form_id}")

    out_path = OUTPUT_DIR / "order_attachment_hooks.json"
    out_path.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n\n✓ Findings saved → {out_path}")
    print(f"\nSummary by form:")
    for form_id, fields in findings.items():
        total_hits = sum(len(v) for v in fields.values())
        print(f"  {form_id:25s} → {total_hits} docs with attachments (across {len(fields)} field(s))")


if __name__ == "__main__":
    main()
