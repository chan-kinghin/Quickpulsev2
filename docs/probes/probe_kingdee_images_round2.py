#!/usr/bin/env python3
"""
Round-2 probe: confirm whether BD_MATERIAL image fields are actually populated.

Round 1 found these image-like fields on BD_MATERIAL:
    Image, ImageFileServer, IsImgFileServer,
    MaterialCMK[0].FImgFile_CMK, MaterialCMK[0].UploadSkuImage,
    MaterialSale[0].ISPRODUCTFILES

For 05.01.07.01 they were all None / empty / False — but that's a self-made
intermediate. We need to check finished goods (07.xx) where customer-facing
photos are far more likely.

This round:
1. Pull 20 candidate materials across prefixes 07.xx / 03.xx / 05.xx.
2. View() each and check the image fields' actual values.
3. Report which materials carry non-empty image data.
4. Also try ExecuteBillQuery against BD_MATERIAL with image FieldKeys —
   that's how QuickPulse would consume them if we add support.
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


IMAGE_FIELDS_HEADER = ["Image", "ImageFileServer", "IsImgFileServer"]
IMAGE_FIELDS_CMK = ["FImgFile_CMK", "UploadSkuImage"]
IMAGE_FIELDS_SALE = ["ISPRODUCTFILES"]


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


def query_candidates(sdk: K3CloudApiSdk, prefix: str, limit: int = 5) -> list[str]:
    params = {
        "FormId": "BD_MATERIAL",
        "FieldKeys": "FNumber,FName",
        "FilterString": f"FNumber like '{prefix}%' AND FDocumentStatus='C'",
        "Limit": limit,
    }
    resp = sdk.ExecuteBillQuery(params)
    if not resp:
        return []
    rows = json.loads(resp) if isinstance(resp, str) else resp
    out = []
    for r in rows or []:
        if isinstance(r, list) and r and r[0]:
            out.append(r[0])
    return out


def query_image_fields(sdk: K3CloudApiSdk, material_numbers: list[str]) -> list[dict]:
    """Try to pull image fields via ExecuteBillQuery directly.

    This is the key test — if these field keys work, QuickPulse can read
    photos without using the heavier View() API per material.
    """
    if not material_numbers:
        return []
    in_list = ",".join(f"'{m}'" for m in material_numbers)
    # Try each potential field-key name Kingdee might use in ExecuteBillQuery
    candidate_keys_by_test = [
        ["FNumber", "FImage"],                       # most common ECC naming
        ["FNumber", "FImageFileServer"],
        ["FNumber", "FImgFile_CMK"],
        ["FNumber", "FMaterialCMK_FImgFile_CMK"],    # parent_entity_field pattern
        ["FNumber", "FUploadSkuImage"],
    ]
    results = []
    for keys in candidate_keys_by_test:
        params = {
            "FormId": "BD_MATERIAL",
            "FieldKeys": ",".join(keys),
            "FilterString": f"FNumber IN ({in_list})",
            "Limit": 50,
        }
        try:
            resp = sdk.ExecuteBillQuery(params)
            parsed = json.loads(resp) if isinstance(resp, str) else resp
            # Detect error responses (dict with Result)
            if isinstance(parsed, dict):
                err = parsed.get("Result", {}).get("ResponseStatus", {}).get("Errors", [])
                msg = err[0].get("Message") if err else None
                results.append({"keys": keys, "ok": False, "error": msg or "unknown"})
                continue
            results.append({
                "keys": keys,
                "ok": True,
                "sample_rows": parsed[:3] if isinstance(parsed, list) else parsed,
                "n_rows": len(parsed) if isinstance(parsed, list) else 0,
            })
        except Exception as e:
            results.append({"keys": keys, "ok": False, "error": str(e)})
    return results


def view_and_extract(sdk: K3CloudApiSdk, material_number: str) -> dict:
    view_para = {
        "CreateOrgId": 0,
        "Number": material_number,
        "Id": "",
        "IsSortBySeq": "false",
    }
    raw = sdk.View("BD_MATERIAL", view_para)
    if not raw:
        return {"material": material_number, "ok": False, "error": "empty response"}
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    res = parsed.get("Result", {})
    status = res.get("ResponseStatus", {})
    if status and not status.get("IsSuccess", True):
        return {"material": material_number, "ok": False, "error": status}
    doc = res.get("Result") or {}
    out = {
        "material": material_number,
        "ok": True,
        "name": doc.get("Name") or doc.get("FName"),
        "ErpClsID": (doc.get("ErpClsID") or {}).get("FNumber") if isinstance(doc.get("ErpClsID"), dict) else doc.get("ErpClsID"),
        "header_image_fields": {f: doc.get(f) for f in IMAGE_FIELDS_HEADER},
    }
    cmk = doc.get("MaterialCMK") or []
    if cmk and isinstance(cmk, list) and isinstance(cmk[0], dict):
        out["cmk_image_fields"] = {f: cmk[0].get(f) for f in IMAGE_FIELDS_CMK}
    sale = doc.get("MaterialSale") or []
    if sale and isinstance(sale, list) and isinstance(sale[0], dict):
        out["sale_flags"] = {f: sale[0].get(f) for f in IMAGE_FIELDS_SALE}
    return out


def main():
    sdk = init_sdk()

    # Pull candidates by prefix
    prefixes = ["07.", "03.", "05.", "06."]
    by_prefix: dict[str, list[str]] = {}
    for p in prefixes:
        cands = query_candidates(sdk, p, limit=5)
        by_prefix[p] = cands
        print(f"  Prefix {p}: {len(cands)} candidates → {cands}")

    all_materials = [m for v in by_prefix.values() for m in v]

    # Test ExecuteBillQuery with image FieldKeys
    print(f"\n{'='*70}\nProbe A: Try image fields via ExecuteBillQuery\n{'='*70}")
    qresults = query_image_fields(sdk, all_materials[:5])
    for r in qresults:
        if r.get("ok"):
            print(f"  ✓ {r['keys']}  → {r['n_rows']} rows")
            for row in r.get("sample_rows", [])[:3]:
                print(f"      {row}")
        else:
            print(f"  ✗ {r['keys']}  → error: {r.get('error')!s:.150}")

    # Probe each material via View()
    print(f"\n{'='*70}\nProbe B: View() each material, extract image fields\n{'='*70}")
    findings = []
    for mat in all_materials:
        try:
            data = view_and_extract(sdk, mat)
            findings.append(data)
            non_empty = []
            for grp_name in ["header_image_fields", "cmk_image_fields", "sale_flags"]:
                grp = data.get(grp_name) or {}
                for k, v in grp.items():
                    if v not in (None, "", " ", False, 0):
                        non_empty.append(f"{grp_name}.{k}={v!r}")
            tag = "📷" if non_empty else "  "
            name = data.get("name", "")
            cls = data.get("ErpClsID", "?")
            print(f"  {tag} {mat:<20} cls={cls!s:<3}  name={str(name)[:30]:<30}  populated={non_empty if non_empty else 'all empty'}")
        except Exception as e:
            print(f"  ✗ {mat}: {e}")

    out_path = OUTPUT_DIR / "BD_MATERIAL_image_probe_round2.json"
    out_path.write_text(json.dumps({
        "candidates_by_prefix": by_prefix,
        "executebillquery_tests": qresults,
        "view_findings": findings,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ Round-2 saved → {out_path}")


if __name__ == "__main__":
    main()
