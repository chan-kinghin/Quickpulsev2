# Kingdee Photo Attachments — How They Work (Fluent tenant)

**Probed 2026-05-11** against `http://flt.hotker.com:8200/k3cloud/`.
Outputs live in `docs/probes/_probe_output/`. Probe scripts themselves live in `docs/probes/`.

## TL;DR

- **Where**: Photos live on **`PRD_MO.TreeEntity`** (production-order detail rows), **not** on `BD_MATERIAL`, `SAL_SaleOrder`, `PUR_PurchaseOrder`, `STK_InStock`, or `PRD_INSTOCK`.
- **How they're stored**: As 3 Fluent-custom photo slots per detail row, plus 2 attachment fields:

  | Field | Meaning | Type |
  |---|---|---|
  | `F_QWJI_YSTP1` | 原始图片 1 | FileID string (32-char hex GUID) |
  | `F_QWJI_YSTP2` | 原始图片 2 | FileID string |
  | `F_QWJI_YSTP3` | 原始图片 3 | FileID string |
  | `F_QWJI_YSWZFJ` | 原始物资附件 | path/text |
  | `F_QWJI_YSWZFJ_Files` | 同上 — file list | list of file metadata |
  | `F_QWJI_YSFJ` | 原始附件 | path/text |

- **Coverage**: 299 / 2000 most-recent `PRD_MO` records (~15%) have ≥1 populated photo. Older orders (e.g. `DK251003S`, Oct 2025) are blank.
- **The stock `FATTACHMENTS` BOS field does NOT exist on this tenant.** Fluent built their own photo system inside the `F_QWJI_*` custom-field namespace instead of using K3Cloud's native BOS attachments.

## Reading photos via API

### Step 1 — Find FileIDs (ExecuteBillQuery)

```python
sdk.ExecuteBillQuery({
    "FormId": "PRD_MO",
    "FieldKeys": "FBillNo,FId,FMTONo,F_QWJI_YSTP1,F_QWJI_YSTP2,F_QWJI_YSTP3",
    "FilterString": "FMTONo='DS264102S'",
    "Limit": 100,
})
```

Returns rows like:
```
['MO260501414', 256720, 'DS264102S',
 '8978cffd01404da595bdc8be907fbcce',   # photo 1 FileID
 'd8b7e9b6fed143efae647b77c742cd67',   # photo 2 FileID
 '4ec577b82824455c9cb7a1aed25c85f8']   # photo 3 FileID
```

Empty slots come back as `''` or `None`.

### Step 2 — Download bytes (AttachmentDownLoad)

```python
sdk.attachmentDownLoad({"FileID": "8978cffd01404da595bdc8be907fbcce"})
```

Response shape:
```json
{
  "Result": {
    "ResponseStatus": {"IsSuccess": true, "MsgCode": 0, ...},
    "StartIndex": 4194304,
    "IsLast": true,
    "FileSize": 381264,
    "FileName": "8683f275b8a747378669c9eb98b1cab5.png",
    "FilePart": "<base64-encoded chunk>"
  }
}
```

- `FileID` is the **only** required parameter (FormId / InternalId are ignored).
- `FilePart` is base64. Decode with `base64.b64decode(result["FilePart"])`.
- `IsLast = true` confirms the response is the entire file. For files larger than the chunk window, loop with increasing `StartIndex` until `IsLast = true`.
- The returned `FileName` is the **stored** filename on the BOS server (a different GUID than the FileID — Kingdee renames on upload).

### Verified sample

| MTO | Bill | FileID | Decoded | Content |
|---|---|---|---|---|
| `DS264102S` | `MO260501414` | `8978cffd01404da595bdc8be907fbcce` | 381,264 bytes PNG | MARES dive mask + snorkel reference photo |

Sample binary was saved to `docs/probes/_probe_output/8683f275b8a747378669c9eb98b1cab5.png` during the probe; not retained in git (re-fetchable via `attachmentDownLoad({"FileID": "8683f275b8a747378669c9eb98b1cab5"})`).

## What we tried and why it failed

| Attempt | Result | Lesson |
|---|---|---|
| `BD_MATERIAL.FImageFileServer`, `FImgFile_CMK`, `FUploadSkuImage` | 0 rows populated across the entire material master | Photos aren't stored on the material — they're per-order |
| `PRD_MO.FATTACHMENTS`, `FAttachmentSign`, etc. (9 BOS attachment variants) | All return `元数据中标识为 X 的字段不存在` | This tenant doesn't use the stock BOS attachment system |
| `BOS_Attachment` form direct query | Form exists, but standard fields (`FFileName`, `FUrl`, …) not in metadata; `FId` returns `-1` sentinel (no rows) | BOS attachment store is empty / not accessible via WebAPI |
| `AttachmentQuery`, `AttachmentService.GetAttachmentList` services | `service no found` | Listing endpoints not registered on this Kingdee build |
| `SAL_SaleOrder.F_QWJI_YSTP1` | Field doesn't exist on sales orders | Custom photo fields are PRD_MO-only |

## What we still don't know

- Whether the **same** photo set is also exposed on related forms in newer Fluent customizations (e.g., quality-inspection records, BOM, picking lists).
- Whether other `F_QWJI_*` fields (`F_QWJI_YSWZFJ_Files`, `F_QWJI_YSFJ`) carry useful image data when populated — all the samples we found were `[]` / `' '`. They may only be set for specific business types (e.g., outsourcing, rework).
- The maximum number of photos per order — we only confirmed 3 slots (`YSTP1/2/3`).

## How to wire this into QuickPulse (if/when needed)

1. **Schema**: add a `photo_file_ids: list[str]` field to `ChildItem` (or a sibling `OrderPhotos` model keyed by `bill_no`). Map from `F_QWJI_YSTP1/2/3` in `factory.py`.
2. **Cache**: store FileIDs in SQLite as a comma-separated string on the `production_orders` table. Image bytes themselves should not be cached server-side — download on demand from the frontend instead.
3. **Frontend**: render a thumbnail strip per row. Use a dedicated backend endpoint `GET /api/photo/{file_id}` that wraps `sdk.attachmentDownLoad`, sets `Content-Type: image/png`, and streams the decoded bytes. Set a short browser cache (e.g. `Cache-Control: max-age=3600`) since FileIDs are immutable.
4. **Auth**: photos are tied to Kingdee credentials. Don't expose `/api/photo/{file_id}` without the same auth as the rest of QuickPulse.
5. **Cost**: each photo is ~300-500 KB. Lazy-load on hover or modal-open rather than eagerly fetching for every visible row.

## Reproduction

```bash
# 1. Discover field names exist and what's populated
python3 docs/probes/probe_fluent_photo_fields.py

# 2. Download one to verify the binary
python3 docs/probes/probe_attachment_download.py
```
