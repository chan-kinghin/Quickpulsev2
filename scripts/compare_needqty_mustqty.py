#!/usr/bin/env python3
"""Compare FNeedQty vs FMustQty in PRD_PPBOM for a specific MO."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from k3cloud_webapi_sdk.main import K3CloudApiSdk

load_dotenv()

api_sdk = K3CloudApiSdk(os.environ["KINGDEE_SERVER_URL"])
api_sdk.InitConfig(
    acct_id=os.environ["KINGDEE_ACCT_ID"],
    user_name=os.environ["KINGDEE_USER_NAME"],
    app_id=os.environ["KINGDEE_APP_ID"],
    app_secret=os.environ["KINGDEE_APP_SEC"],
    server_url=os.environ["KINGDEE_SERVER_URL"],
    lcid=int(os.environ.get("KINGDEE_LCID", 2052)),
)

# Pick MOs that have decimal need_qty in our cache
# MO260303296 is from the Kingdee screenshot showing integer 应发数量 (768)
test_mos = ["MO260303296", "MO260303230", "MO260300611"]

for mo in test_mos:
    print(f"\n{'='*60}")
    print(f"MO: {mo}")
    print(f"{'='*60}")

    params = {
        "FormId": "PRD_PPBOM",
        "FieldKeys": "FMOBillNO,FMaterialId.FNumber,FMaterialId.FName,FMustQty,FStdQty",
        "FilterString": f"FMOBillNO='{mo}'",
        "Limit": 50,
    }

    result = api_sdk.ExecuteBillQuery(json.dumps(params))

    if isinstance(result, str):
        result = json.loads(result)

    if not result:
        print("  No data returned")
        continue

    # Check for error
    if isinstance(result, list) and len(result) == 1 and isinstance(result[0], list) and isinstance(result[0][0], dict):
        print(f"  Error: {result[0][0]}")
        continue

    if not isinstance(result, list) or not result:
        print(f"  Unexpected: {result}")
        continue

    print(f"  {'物料编码':<16} {'物料名称':<12} {'FMustQty':>12} {'FStdQty':>10} {'整数?'}")
    print(f"  {'-'*16} {'-'*12} {'-'*12} {'-'*10} {'-'*5}")
    for row in result[:20]:
        mo_no, code, name, must_qty, std_qty = row
        is_int = "YES" if must_qty == int(must_qty) else f"NO ({must_qty})"
        print(f"  {code:<16} {name:<12} {must_qty:>12} {std_qty:>10} {is_int}")
