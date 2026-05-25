#!/usr/bin/env python3
"""
Discover BOS_Attachment's real field names and check if any attachments exist.
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


def main():
    sdk = init_sdk()

    # Try common attachment field names; whichever doesn't error reveals the schema
    candidate_fields = [
        "FId", "FFileId", "FFileID", "FBillNo", "FNumber",
        "FFormId", "FInterId", "FInternalId", "FBillID",
        "FAttachFileName", "FFileNameOriginal", "FName", "FFileSize",
        "FOriginalName", "FFileType", "FUrl", "FFilePath",
        "FCreateDate", "FCreatorId", "FFileName",
    ]
    print(f"\n[1] Probe each field name individually on BOS_Attachment:\n")
    valid = []
    for f in candidate_fields:
        params = {"FormId": "BD_MATERIAL", "FieldKeys": "FNumber", "FilterString": "", "Limit": 1}  # baseline
        # Actually probe the attachment form
        params = {"FormId": "BOS_Attachment", "FieldKeys": f, "Limit": 1}
        try:
            resp = sdk.ExecuteBillQuery(params)
            parsed = json.loads(resp) if isinstance(resp, str) else resp
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], list):
                print(f"  ✓ {f:25s} → sample = {parsed[0]}")
                valid.append(f)
            elif isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                msg = parsed[0].get("Result", {}).get("ResponseStatus", {}).get("Errors", [{}])[0].get("Message", "")
                if "不存在" in msg:
                    pass  # field doesn't exist — silent
                else:
                    print(f"  ? {f:25s} → {msg[:80]}")
            else:
                print(f"  - {f:25s} → empty or unknown shape")
        except Exception as e:
            print(f"  ✗ {f:25s} → exception {e}")

    if not valid:
        print("\nNo valid fields discovered.")
        return

    print(f"\n[2] Valid fields: {valid}")
    print(f"\n[3] Pull a sample of 10 rows from BOS_Attachment with valid fields:\n")
    params = {
        "FormId": "BOS_Attachment",
        "FieldKeys": ",".join(valid),
        "Limit": 10,
    }
    resp = sdk.ExecuteBillQuery(params)
    parsed = json.loads(resp) if isinstance(resp, str) else resp
    if isinstance(parsed, list):
        for row in parsed[:10]:
            print(f"  {row}")
        print(f"\n  Total rows in sample: {len(parsed)}")

    print(f"\n[4] Filter BOS_Attachment by FFormId='BD_MATERIAL' to find material attachments:")
    for filter_field in ["FFormId", "FFormID", "FBillTypeId.FNumber", "FOBJECTTYPEID"]:
        try:
            params = {
                "FormId": "BOS_Attachment",
                "FieldKeys": ",".join(valid),
                "FilterString": f"{filter_field}='BD_MATERIAL'",
                "Limit": 10,
            }
            resp = sdk.ExecuteBillQuery(params)
            parsed = json.loads(resp) if isinstance(resp, str) else resp
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], list):
                print(f"\n  ✓ Filter {filter_field}='BD_MATERIAL' worked, {len(parsed)} rows:")
                for row in parsed[:5]:
                    print(f"    {row}")
                break
            elif isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                msg = parsed[0].get("Result", {}).get("ResponseStatus", {}).get("Errors", [{}])[0].get("Message", "")
                print(f"  ✗ {filter_field}: {msg[:100]}")
            else:
                print(f"  - {filter_field}: empty")
        except Exception as e:
            print(f"  ✗ {filter_field}: {e}")


if __name__ == "__main__":
    main()
