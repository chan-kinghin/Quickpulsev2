#!/usr/bin/env python3
"""
Download a real attachment via Kingdee's AttachmentDownLoad service.

Picks a FileID from fluent_photo_field_hits.json (Round 4 output) and
calls sdk.attachmentDownLoad with several parameter-shape variants until
one returns binary data.

Saves the bytes to scripts/_probe_output/sample_attachment.* with
detected extension.
"""
from __future__ import annotations

import base64
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


def magic_extension(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:2] == b"PK":
        return "zip"  # also docx/xlsx
    return "bin"


def try_download(sdk, params, label):
    print(f"\n→ Variant '{label}'")
    print(f"  params = {json.dumps(params, ensure_ascii=False)[:200]}")
    try:
        raw = sdk.attachmentDownLoad(params)
    except Exception as e:
        print(f"  ✗ exception: {e}")
        return None
    if raw is None:
        print(f"  ✗ None response")
        return None
    # Response is usually a JSON string with base64-encoded file bytes
    if isinstance(raw, (bytes, bytearray)):
        print(f"  Got raw bytes: {len(raw)}")
        return raw
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except Exception as e:
        print(f"  ✗ not JSON: {e}; raw[:200]={str(raw)[:200]}")
        return None
    # Inspect for error or for file content
    if isinstance(parsed, dict):
        result = parsed.get("Result", {})
        if isinstance(result, dict):
            status = result.get("ResponseStatus", {})
            if status and not status.get("IsSuccess", True):
                errs = status.get("Errors", [])
                msg = errs[0].get("Message") if errs else None
                print(f"  ✗ error: {msg}")
                return None
            # Kingdee streaming response: {Result: {FilePart: <base64>, FileName, FileSize, StartIndex, IsLast}}
            if "FilePart" in result:
                file_name = result.get("FileName")
                file_size = result.get("FileSize")
                is_last = result.get("IsLast")
                try:
                    data = base64.b64decode(result["FilePart"])
                    print(f"  ✓ decoded {len(data)} bytes  (FileName={file_name}, FileSize={file_size}, IsLast={is_last})")
                    return (data, file_name)
                except Exception as e:
                    print(f"  ! base64 decode failed: {e}")
        print(f"  ? unrecognized JSON shape: keys={list(parsed.keys())[:6]}")
        return None
    print(f"  ? unrecognized response type {type(parsed).__name__}")
    return None


def main():
    hits_path = OUTPUT_DIR / "fluent_photo_field_hits.json"
    if not hits_path.exists():
        print(f"FATAL: {hits_path} missing. Run probe_fluent_photo_fields.py first.")
        return

    hits = json.loads(hits_path.read_text())["hits"]
    if not hits:
        print("No populated photo records — cannot test download.")
        return

    # Pick the first hit with at least one populated FileID
    target = None
    for h in hits:
        for fname, fid in h["populated"].items():
            if isinstance(fid, str) and len(fid) >= 16:
                target = {"bill_no": h["bill_no"], "fid": h["fid"], "mto": h["mto"], "field": fname, "file_id": fid}
                break
        if target:
            break

    if not target:
        print("No usable FileID in hits.")
        return

    print(f"\nTarget: {target}")
    sdk = init_sdk()

    # Try parameter shape variants. Kingdee tenants vary in spelling.
    variants = [
        ("FileID-only", {"FileID": target["file_id"]}),
        ("FormId+InteralId+FileID", {"FormId": "PRD_MO", "InteralId": str(target["fid"]), "FileID": target["file_id"]}),
        ("FormId+InternalId+FileID", {"FormId": "PRD_MO", "InternalId": str(target["fid"]), "FileID": target["file_id"]}),
        ("FormId+InteralId+FileID+AttachmentField",
            {"FormId": "PRD_MO", "InteralId": str(target["fid"]), "FileID": target["file_id"], "AttachmentField": target["field"]}),
        ("FormId+InteralId+FileID(lowercase fileid)",
            {"FormId": "PRD_MO", "InteralId": str(target["fid"]), "fileid": target["file_id"]}),
    ]

    binary = None
    server_name = None
    used_variant = None
    for label, params in variants:
        result = try_download(sdk, params, label)
        if result is None:
            continue
        if isinstance(result, tuple):
            data, server_name = result
        else:
            data = result
        if data and len(data) > 64:
            binary = data
            used_variant = (label, params)
            break

    if binary is None:
        print("\n✗ No variant returned a binary payload.")
        return

    ext = magic_extension(binary)
    base = server_name or f"sample_attachment_{target['bill_no']}.{ext}"
    if not base.endswith(f".{ext}"):
        base = f"{base}.{ext}"
    out_path = OUTPUT_DIR / base
    out_path.write_bytes(binary)
    print(f"\n✓ Wrote {len(binary)} bytes → {out_path}")
    print(f"  Format detected: {ext}")
    print(f"  Server-side name: {server_name}")
    print(f"  Variant used: {used_variant[0]}")
    print(f"  Variant params: {json.dumps(used_variant[1], ensure_ascii=False)}")


if __name__ == "__main__":
    main()
