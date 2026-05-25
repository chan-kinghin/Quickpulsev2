#!/usr/bin/env python3
"""
Probe Kingdee K3Cloud for image / photo / attachment fields.

Strategy:
1. Pick a known material code from a recent MTO (PRD_PPBOM).
2. Use BD_MATERIAL ExecuteBillQuery to find its FId.
3. Use View() to dump the FULL BD_MATERIAL document.
4. Scan the response recursively for any key matching image-related patterns.
5. Repeat for PRD_MO header to check if production orders carry attachments.

Output: pretty summary to stdout + raw JSON to scripts/_probe_output/.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Ensure project root is on path for src imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from k3cloud_webapi_sdk.main import K3CloudApiSdk

OUTPUT_DIR = PROJECT_ROOT / "scripts" / "_probe_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Patterns that suggest image / attachment fields
IMAGE_PATTERNS = [
    r"image", r"photo", r"picture", r"pic\b", r"pict",
    r"attach", r"file", r"url", r"thumb",
    r"图片", r"附件", r"照片",
]
IMAGE_RE = re.compile("|".join(IMAGE_PATTERNS), re.IGNORECASE)


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


def walk(obj, path=""):
    """Yield (key_path, value) for every leaf and every key node."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            sub = f"{path}.{k}" if path else k
            yield sub, v
            yield from walk(v, sub)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):  # only first 3 entries to limit noise
            sub = f"{path}[{i}]"
            yield from walk(v, sub)


def scan_for_images(label: str, doc: dict) -> list[tuple[str, object]]:
    hits = []
    for key_path, value in walk(doc):
        leaf_name = key_path.split(".")[-1].split("[")[0]
        if IMAGE_RE.search(leaf_name):
            # only keep leaf values, not nested dicts
            if not isinstance(value, (dict, list)):
                hits.append((key_path, value))
    return hits


def query_first_material(sdk: K3CloudApiSdk, mto: str) -> str | None:
    """Get one material code (07.xx/05.xx/03.xx) from PRD_PPBOM for an MTO."""
    params = {
        "FormId": "PRD_PPBOM",
        "FieldKeys": "FMaterialId.FNumber,FMTONO",
        "FilterString": f"FMTONO='{mto}'",
        "Limit": 5,
    }
    resp = sdk.ExecuteBillQuery(params)
    if not resp:
        return None
    rows = json.loads(resp) if isinstance(resp, str) else resp
    if not rows or not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, list) and row and row[0]:
            return row[0]
    return None


def view_material(sdk: K3CloudApiSdk, material_number: str) -> dict | None:
    """View() the BD_MATERIAL master to get every field, including images."""
    view_para = {
        "CreateOrgId": 0,
        "Number": material_number,
        "Id": "",
        "IsSortBySeq": "false",
    }
    raw = sdk.View("BD_MATERIAL", view_para)
    if not raw:
        return None
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    result = parsed.get("Result", {})
    status = result.get("ResponseStatus", {})
    if status and not status.get("IsSuccess", True):
        print(f"   ! View(BD_MATERIAL) failed: {status}")
        return None
    return result.get("Result")


def view_prd_mo(sdk: K3CloudApiSdk, mto: str) -> dict | None:
    """View() a PRD_MO header to check for attachment fields on the order itself."""
    params = {
        "FormId": "PRD_MO",
        "FieldKeys": "FBillNo,FMTONo",
        "FilterString": f"FMTONo='{mto}'",
        "Limit": 1,
    }
    resp = sdk.ExecuteBillQuery(params)
    if not resp:
        return None
    rows = json.loads(resp) if isinstance(resp, str) else resp
    if not rows:
        return None
    bill_no = rows[0][0]
    view_para = {
        "CreateOrgId": 0,
        "Number": bill_no,
        "Id": "",
        "IsSortBySeq": "false",
    }
    raw = sdk.View("PRD_MO", view_para)
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    return parsed.get("Result", {}).get("Result")


def try_attachment_api(sdk: K3CloudApiSdk, form_id: str, internal_id: str) -> dict | None:
    """Try Kingdee's AttachmentUpLoad/DownLoad family — there's an
    'GetAttachmentList' style endpoint exposed as 'AttachmentDownLoad' / 'Attachment'."""
    try:
        # The SDK exposes a generic CustomRequest path.
        # Try the documented "Get attachment list" service:
        # K3Cloud has: Kingdee.BOS.WebApi.ServicesStub.AttachmentService.GetAttachmentList
        param = {
            "data": {
                "FormId": form_id,
                "InteralId": internal_id,
                "FileName": "",
                "AttachmentField": "FATTACHMENTS",
            }
        }
        # Try AttachmentDownLoad via generic request
        # (some Kingdee tenants expose it as part of the manager)
        raw = sdk.AttachmentDownLoad(param)  # type: ignore[attr-defined]
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        return {"_error": str(e)}


def main():
    sdk = init_sdk()

    # Pick a known MTO from recent memory/commits
    candidate_mtos = ["DK251003S", "AK2510034", "AS2511012", "AS251008", "AK2412023"]

    material_number = None
    chosen_mto = None
    for mto in candidate_mtos:
        try:
            print(f"\n→ Looking for materials in MTO {mto}...")
            material_number = query_first_material(sdk, mto)
            if material_number:
                chosen_mto = mto
                print(f"  Found material: {material_number}")
                break
        except Exception as e:
            print(f"  ! Query failed for {mto}: {e}")
            continue

    if not material_number:
        print("No materials found in any candidate MTO. Trying generic BD_MATERIAL query...")
        params = {
            "FormId": "BD_MATERIAL",
            "FieldKeys": "FNumber,FName",
            "FilterString": "FNumber like '07.%'",
            "Limit": 1,
        }
        resp = sdk.ExecuteBillQuery(params)
        rows = json.loads(resp) if isinstance(resp, str) else resp
        if rows and rows[0]:
            material_number = rows[0][0]
            chosen_mto = None
            print(f"  Fallback material: {material_number}")
        else:
            print("FATAL: could not locate any material to probe.")
            return

    # ---- Probe 1: BD_MATERIAL ----
    print(f"\n{'='*70}")
    print(f"Probe 1: View(BD_MATERIAL) for {material_number}")
    print(f"{'='*70}")
    mat_doc = view_material(sdk, material_number)
    if not mat_doc:
        print("No data returned for BD_MATERIAL.View()")
    else:
        out_path = OUTPUT_DIR / f"BD_MATERIAL_{material_number.replace('.','_')}.json"
        out_path.write_text(json.dumps(mat_doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Saved → {out_path}")
        # Print top-level keys
        if isinstance(mat_doc, dict):
            print(f"  Top-level keys ({len(mat_doc)}): {sorted(mat_doc.keys())[:25]}...")
        hits = scan_for_images("BD_MATERIAL", mat_doc)
        print(f"\n  IMAGE-LIKE FIELDS FOUND ({len(hits)}):")
        for k, v in hits:
            preview = str(v)
            if len(preview) > 120:
                preview = preview[:117] + "..."
            print(f"    • {k}  =  {preview}")

    # ---- Probe 2: PRD_MO header ----
    if chosen_mto:
        print(f"\n{'='*70}")
        print(f"Probe 2: View(PRD_MO) for MTO {chosen_mto}")
        print(f"{'='*70}")
        try:
            mo_doc = view_prd_mo(sdk, chosen_mto)
            if mo_doc:
                out_path = OUTPUT_DIR / f"PRD_MO_{chosen_mto}.json"
                out_path.write_text(json.dumps(mo_doc, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  Saved → {out_path}")
                hits = scan_for_images("PRD_MO", mo_doc)
                print(f"\n  IMAGE/ATTACH-LIKE FIELDS FOUND ({len(hits)}):")
                for k, v in hits[:40]:
                    preview = str(v)
                    if len(preview) > 120:
                        preview = preview[:117] + "..."
                    print(f"    • {k}  =  {preview}")
        except Exception as e:
            print(f"  ! View(PRD_MO) failed: {e}")

    # ---- Probe 3: Try AttachmentDownLoad endpoint ----
    print(f"\n{'='*70}")
    print(f"Probe 3: try AttachmentDownLoad service (if SDK exposes it)")
    print(f"{'='*70}")
    # Need internal FId. Use BD_MATERIAL FId from probe 1 if available.
    if mat_doc and isinstance(mat_doc, dict):
        fid = mat_doc.get("Id") or mat_doc.get("FMASTERID") or mat_doc.get("FId")
        if fid:
            res = try_attachment_api(sdk, "BD_MATERIAL", str(fid))
            print(f"  Result: {json.dumps(res, ensure_ascii=False)[:500]}")
        else:
            print("  Skipped — could not find FId in BD_MATERIAL doc")
    else:
        print("  Skipped — no material doc available")

    print(f"\n✓ Done. Raw outputs at: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
