#!/usr/bin/env python3
"""
Probe BD_MATERIAL.MaterialBase.ErpClsID for sample codes across all prefixes.

Purpose: verify whether ErpClsID is a reliable routing classifier before
swapping the broken PPBOM.FMaterialType-based routing (mto_handler.py:1525).

Open questions from docs/MATERIAL_CLASSIFICATION_FIELDS_2026-05-09.md:
  1. Is 05.xx half-finished really ErpClsID="2" (自制)?
  2. Is 03.xx purchased really ErpClsID="1" (外购)?
  3. Is 08.xx outsourcing really ErpClsID="3" (委外)?
  4. What about 01/02/06/07?

Outputs:
  - Per-code table: code | name | ErpClsID | CategoryID.Number | CategoryID.Name | MaterialGroup
  - Per-prefix rollup: how many distinct ErpClsID values per prefix
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from k3cloud_webapi_sdk.main import K3CloudApiSdk

# Curated sample: 5 codes per prefix, drawn from local cache.
# Plus 4 obvious-packaging codes that the user's colleagues think should be 包材.
SAMPLES = [
    # (prefix, code, hint)
    ("03", "03.03.001", "外箱 — 应该是 外购"),
    ("03", "03.04.001", "内盒 — 应该是 外购"),
    ("03", "03.01.001", ""),
    ("03", "03.01.002", ""),
    ("03", "03.02.02.067", "热压吸塑"),
    ("05", "05.01.03", ""),
    ("05", "05.01.05", ""),
    ("05", "05.01.06", ""),
    ("05", "05.20.01.11.066", "镜带 已印刷 — 截图里被标自制的样本"),
    ("06", "06.02.003", ""),
    ("06", "06.02.007", ""),
    ("06", "06.02.008", ""),
    ("07", "07.01.03", ""),
    ("07", "07.01.05", ""),
    ("07", "07.41.001", "硅胶防水袋 — 2026-05-09 验证过 ErpClsID=9"),
    ("08", "08.01.45", ""),
    ("08", "08.01.46.01", ""),
    ("08", "08.01.48", ""),
    ("01", "01.22.002", ""),
    ("01", "01.22.003", ""),
    ("02", "02.04.038", ""),
    ("02", "02.10.01", ""),
]

# Map both str and int keys — found live ErpClsID can come back as int.
# WARNING: convention to be VERIFIED by this probe; do not trust until printout
# shows it matches reality.
ERP_CLS_LABEL = {
    1: "外购?", 2: "自制?", 3: "委外?", 9: "成品?",
    "1": "外购?", "2": "自制?", "3": "委外?", "9": "成品?",
}


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


def view_material(sdk: K3CloudApiSdk, number: str) -> dict | None:
    data = {"Number": number}
    try:
        resp = sdk.View("BD_MATERIAL", data)
        if isinstance(resp, str):
            resp = json.loads(resp)
        if not resp.get("Result", {}).get("ResponseStatus", {}).get("IsSuccess"):
            err = resp.get("Result", {}).get("ResponseStatus", {}).get("Errors", [{}])
            print(f"  [error] {err[0].get('Message') if err else 'unknown'}")
            return None
        return resp["Result"]["Result"]
    except Exception as e:
        print(f"  [exception] {e}")
        return None


def _multilang(v):
    """Extract the localised value from Kingdee's MultiLanguage Name field."""
    if isinstance(v, list) and v:
        first = v[0]
        if isinstance(first, dict):
            return first.get("Value") or first.get("Name") or ""
    return v if isinstance(v, str) else ""


def extract_fields(data: dict) -> dict:
    """Pull just the routing-relevant fields out of the BD_MATERIAL response."""
    name_text = _multilang(data.get("Name"))

    # MaterialBase is a LIST in this tenant — use [0]
    mb_raw = data.get("MaterialBase")
    mb = mb_raw[0] if isinstance(mb_raw, list) and mb_raw else (mb_raw or {})
    erp_cls = mb.get("ErpClsID")

    cat = mb.get("CategoryID") or {}
    cat_number = cat.get("Number") if isinstance(cat, dict) else None
    cat_name = _multilang(cat.get("Name")) if isinstance(cat, dict) else ""

    mg = data.get("MaterialGroup") or {}
    mg_number = mg.get("Number") if isinstance(mg, dict) else None
    mg_name = _multilang(mg.get("Name")) if isinstance(mg, dict) else ""

    return {
        "name": name_text,
        "erp_cls": erp_cls,
        "cat_number": cat_number,
        "cat_name": cat_name,
        "mg_number": mg_number,
        "mg_name": mg_name,
    }


def main():
    sdk = init_sdk()
    print(f"{'CODE':<22} {'PFX':<4} {'ErpCls':<6} {'→Label':<14} {'CategoryID':<14} {'CatName':<12} {'Group':<10} NAME")
    print("-" * 130)

    prefix_to_clsids: dict[str, set] = defaultdict(set)
    rows = []
    for prefix, code, hint in SAMPLES:
        data = view_material(sdk, code)
        if data is None:
            continue
        f = extract_fields(data)
        cls_raw = f["erp_cls"] if f["erp_cls"] is not None else "?"
        cls_str = str(cls_raw)
        label = ERP_CLS_LABEL.get(cls_raw, ERP_CLS_LABEL.get(cls_str, "?"))
        prefix_to_clsids[prefix].add(cls_str)
        rows.append((code, prefix, cls_str, label, f, hint))
        print(
            f"{code:<22} {prefix:<4} {cls_str:<6} {label:<14} "
            f"{str(f['cat_number'] or ''):<14} {str(f['cat_name'] or '')[:12]:<12} "
            f"{str(f['mg_number'] or ''):<10} {f['name']}"
        )
        if hint:
            print(f"   ↳ hint: {hint}")

    print()
    print("=" * 60)
    print("PREFIX → ErpClsID rollup (distinct values seen)")
    print("=" * 60)
    for prefix in sorted(prefix_to_clsids):
        ids = sorted(prefix_to_clsids[prefix])
        labels = [f"{i}={ERP_CLS_LABEL.get(i, '?')}" for i in ids]
        consistent = "✅ consistent" if len(ids) == 1 else "⚠️  mixed"
        print(f"  {prefix}.xx → {labels}  {consistent}")

    # Also roll up by CategoryID — this might be the real routing field
    print()
    print("=" * 60)
    print("PREFIX → CategoryID.Name rollup")
    print("=" * 60)
    prefix_to_cats: dict[str, set] = defaultdict(set)
    for _, prefix, _, _, f, _ in rows:
        prefix_to_cats[prefix].add(f"{f['cat_number']}|{f['cat_name']}")
    for prefix in sorted(prefix_to_cats):
        cats = sorted(prefix_to_cats[prefix])
        consistent = "✅" if len(cats) == 1 else "⚠️ "
        print(f"  {prefix}.xx → {cats}  {consistent}")

    # Save raw output for follow-up
    out = PROJECT_ROOT / "scripts/_probe_output/erp_cls_routing.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps([{"code": r[0], "prefix": r[1], "erp_cls": r[2], "label": r[3], "fields": r[4]} for r in rows], ensure_ascii=False, indent=2))
    print(f"\nRaw data saved to {out.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
