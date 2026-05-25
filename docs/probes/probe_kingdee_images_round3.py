#!/usr/bin/env python3
"""
Round-3 probe: definitive check — does ANY material in Kingdee have a photo?

Round 2 sampled 20 materials across 4 prefixes and ALL had empty image fields.
This round filters directly for non-empty image fields across the whole BD_MATERIAL
table so we can answer: are photos actually populated for ANY material in this tenant?

Also probes BOS-level attachment storage.
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


def find_materials_with_field(sdk, field_name: str, sample_limit: int = 200):
    """Find any material where the image field is non-empty/non-whitespace."""
    # Try: filter for field != ' ' AND field != ''
    filter_string = f"({field_name} <> ' ' AND {field_name} <> '' AND {field_name} IS NOT NULL)"
    params = {
        "FormId": "BD_MATERIAL",
        "FieldKeys": f"FNumber,FName,{field_name}",
        "FilterString": filter_string,
        "Limit": sample_limit,
    }
    try:
        resp = sdk.ExecuteBillQuery(params)
        if not resp:
            return {"field": field_name, "ok": True, "rows": []}
        parsed = json.loads(resp) if isinstance(resp, str) else resp
        if isinstance(parsed, dict):
            return {"field": field_name, "ok": False, "error": str(parsed)[:300]}
        return {"field": field_name, "ok": True, "rows": parsed}
    except Exception as e:
        return {"field": field_name, "ok": False, "error": str(e)}


def find_materials_with_upload_flag(sdk, sample_limit: int = 200):
    """Materials where FUploadSkuImage = TRUE — uploaded SKU images."""
    params = {
        "FormId": "BD_MATERIAL",
        "FieldKeys": "FNumber,FName,FUploadSkuImage,FImageFileServer,FImgFile_CMK",
        "FilterString": "FUploadSkuImage = '1'",
        "Limit": sample_limit,
    }
    try:
        resp = sdk.ExecuteBillQuery(params)
        if not resp:
            return {"ok": True, "rows": []}
        parsed = json.loads(resp) if isinstance(resp, str) else resp
        if isinstance(parsed, dict):
            return {"ok": False, "error": str(parsed)[:300]}
        return {"ok": True, "rows": parsed}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def try_attachment_query(sdk):
    """Try the BOS attachment list service via generic Execute."""
    # Candidate service paths Kingdee uses
    candidates = [
        ("Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.AttachmentQuery", {"data": {"FormId": "BD_MATERIAL", "InteralId": "1"}}),
        ("Kingdee.BOS.WebApi.ServicesStub.AttachmentService.GetAttachmentList", {"data": {"FormId": "BD_MATERIAL", "InteralId": "1"}}),
    ]
    results = []
    for service_name, data in candidates:
        try:
            raw = sdk.Execute(service_name, data)  # type: ignore[attr-defined]
            parsed = json.loads(raw) if isinstance(raw, str) else raw
            results.append({"service": service_name, "response": parsed})
        except Exception as e:
            results.append({"service": service_name, "error": str(e)[:300]})
    return results


def try_bos_attachment_table(sdk):
    """Try ExecuteBillQuery on the BOS attachment storage table."""
    candidates = [
        "BOS_Attachment",
        "T_BAS_ATTACHMENT",
        "Bos_AttachmentItem",
    ]
    results = []
    for form_id in candidates:
        params = {"FormId": form_id, "FieldKeys": "FId,FFileName", "Limit": 3}
        try:
            resp = sdk.ExecuteBillQuery(params)
            parsed = json.loads(resp) if isinstance(resp, str) else resp
            results.append({"form": form_id, "response": parsed if not isinstance(parsed, list) or len(parsed) <= 3 else parsed[:3], "type": type(parsed).__name__})
        except Exception as e:
            results.append({"form": form_id, "error": str(e)[:200]})
    return results


def main():
    sdk = init_sdk()

    print("="*70)
    print("ROUND 3 — Decisive probe: does ANY material have a photo?")
    print("="*70)

    # Test each image field for non-empty data
    for field in ["FImageFileServer", "FImgFile_CMK", "FUploadSkuImage"]:
        print(f"\n→ Searching BD_MATERIAL for non-empty `{field}`...")
        if field == "FUploadSkuImage":
            r = find_materials_with_upload_flag(sdk)
        else:
            r = find_materials_with_field(sdk, field)
        if not r.get("ok"):
            print(f"   ✗ Error: {r.get('error')}")
            continue
        rows = r.get("rows") or []
        # Filter rows that aren't error packets
        clean = [row for row in rows if isinstance(row, list)]
        print(f"   Found: {len(clean)} materials with populated {field}")
        for row in clean[:10]:
            print(f"     {row}")

    print(f"\n{'='*70}")
    print("Probe attachment list services")
    print("="*70)
    att_results = try_attachment_query(sdk)
    for r in att_results:
        if "error" in r:
            print(f"  ✗ {r['service']}: {r['error'][:200]}")
        else:
            print(f"  → {r['service']}")
            print(f"    Response: {json.dumps(r['response'], ensure_ascii=False)[:500]}")

    print(f"\n{'='*70}")
    print("Probe BOS-level attachment tables")
    print("="*70)
    bos_results = try_bos_attachment_table(sdk)
    for r in bos_results:
        if "error" in r:
            print(f"  ✗ {r['form']}: {r['error'][:200]}")
        else:
            print(f"  → {r['form']} ({r['type']}): {json.dumps(r['response'], ensure_ascii=False)[:300]}")

    out_path = OUTPUT_DIR / "BD_MATERIAL_image_probe_round3.json"
    out_path.write_text(json.dumps({
        "attachment_services": att_results,
        "bos_tables": bos_results,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ Round-3 saved → {out_path}")


if __name__ == "__main__":
    main()
