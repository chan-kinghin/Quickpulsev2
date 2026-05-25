# Plan: Photo Column in QuickPulse Dashboard

## Status: Complete — shipped 2026-05-11

Shipped initially via `d232847`. Subsequent UX iterations: `bc476b1` (inline panel),
`7b52964` (header button), `8a8fe72` (modal fix). E2E proof: `0326a86` Playwright
screenshot against deployed dev. Cookie-auth fallback for direct `<img src>` use:
`8ea2ea9`. LLM schema awareness: `801ea7b`. Memory entry: `kingdee-photo-attachments.md`.

## Decisions (locked from 2026-05-11 conversation)

| Decision | Choice | Notes |
|---|---|---|
| UI placement | **Dedicated "Photo" column** | Click thumbnail → lightbox modal showing all 1–3 photos |
| Sync strategy | **Cache FileIDs in SQLite whenever Kingdee returns them** | Full 3-tier path: live reader + sync writer + cache reader |
| Browser cache | **`Cache-Control: public, max-age=31536000, immutable`** | FileIDs are content-addressed GUIDs, never re-issued |
| Auth | **Same session auth as the rest of QuickPulse** | New endpoint joins the existing FastAPI dependency tree |

## Design Spec

### Problem
QuickPulse rows currently show material code + name + quantities — but Fluent stores 1–3 reference photos per `PRD_MO` order in `TreeEntity.F_QWJI_YSTP1/2/3` (verified 2026-05-11, ~15% of recent orders carry photos). Users currently have to switch to the Kingdee web UI to see these. Goal: surface them directly in the dashboard.

### Solution overview

```
┌────────────────────────────────────────────────────────────────┐
│ Kingdee PRD_MO.TreeEntity.F_QWJI_YSTP1/2/3 (FileID strings)    │
└──────────────────────────────┬─────────────────────────────────┘
                               │  (sync; small strings)
                               ▼
┌────────────────────────────────────────────────────────────────┐
│ cached_production_orders  +  photo_file_id_1/2/3 columns       │
└──────────────────────────────┬─────────────────────────────────┘
                               │  (joined into ChildItem on query)
                               ▼
┌────────────────────────────────────────────────────────────────┐
│ ChildItem.photo_file_ids: list[str]  →  GET /api/mto/{n}       │
└──────────────────────────────┬─────────────────────────────────┘
                               │  (FileIDs only, no binary)
                               ▼
┌────────────────────────────────────────────────────────────────┐
│ Dashboard renders [📷] badge in Photo column when list nonempty │
│   click → modal calls GET /api/photo/{file_id} for each photo   │
└──────────────────────────────┬─────────────────────────────────┘
                               │  (one-shot per file, immutable cache)
                               ▼
┌────────────────────────────────────────────────────────────────┐
│ /api/photo/{file_id}  →  sdk.attachmentDownLoad → PNG bytes    │
│ Content-Type: image/png  Cache-Control: immutable max-age=1y   │
└────────────────────────────────────────────────────────────────┘
```

### Files to modify

| Layer | File | Change |
|---|---|---|
| Schema | `src/database/migrations/013_add_photo_file_ids.sql` | **new** — `ALTER TABLE cached_production_orders ADD COLUMN photo_file_id_1 TEXT; …_2 …_3` |
| Model | `src/readers/models.py` | Add `photo_file_id_1/2/3: Optional[str] = None` to `ProductionOrderModel` |
| Field map (live) | `src/readers/factory.py` (PRODUCTION_ORDER spec around line 259) | Add 3 `FieldMapping("F_QWJI_YSTP1")` entries on the TreeEntity, mapping to the new model fields |
| Sync writer | `src/sync/sync_service.py` | Add the 3 new columns to the INSERT/UPSERT statement that writes `cached_production_orders` |
| Cache reader | `src/query/cache_reader.py` | Add the 3 columns to the SELECT and to `_row_to_production_order` |
| Joined output | `src/query/mto_handler.py` + `ChildItem` model | New field `photo_file_ids: list[str]` collected from the matching ProductionOrder row; empty list when nothing |
| Backend endpoint | `src/api/routers/photo.py` | **new** router `/api/photo/{file_id}` — calls `sdk.attachmentDownLoad`, returns `StreamingResponse(image_bytes, media_type="image/png")` with immutable cache header; wires session auth via existing dependency |
| Router registration | `src/main.py` | Include the new photo router |
| Frontend column | `src/frontend/dashboard.html` (+ `dashboard.js`) | Add `{ id: 'photo', label: 'Photo', visible: true }` to the columns array; render `<button @click="openPhotos(row)">📷×N</button>` when nonempty, `—` otherwise |
| Frontend modal | `src/frontend/dashboard.html` | New Alpine.js modal component — shows `<img src="/api/photo/{id}">` for each FileID, supports keyboard nav |
| Column-prefs bump | `dashboard.js` | Bump `STORAGE_VERSION` so old users get the new column (this is the existing gotcha) |

### Data flow per request

1. User opens MTO `DS264102S` → `GET /api/mto/DS264102S`
2. `mto_handler` joins BOM rows with `cached_production_orders` — each row picks up `photo_file_id_1/2/3` from the matching parent order
3. Response includes `child.photo_file_ids = ["8978cffd…", "d8b7e9b6…", "4ec577b8…"]` (empty list if none)
4. Dashboard renders the column; rows with nonempty list get a clickable badge
5. User clicks → modal opens, makes 1–3 parallel `GET /api/photo/{id}` calls
6. Each `/api/photo/{id}` call: server invokes `sdk.attachmentDownLoad({"FileID": id})`, base64-decodes `FilePart`, streams bytes back with `Content-Type: image/png` and `Cache-Control: public, max-age=31536000, immutable`
7. Browser caches forever (FileIDs are immutable); subsequent views are zero-network

### Gotchas to actively defend against

- **3-tier consistency** (MEMORY.md rule): `photo_file_id_1/2/3` MUST appear in factory.py *and* sync_service.py *and* cache_reader.py — and the test row tuples in `tests/unit/test_cache_reader.py` MUST be updated to match the new column order
- **Column-index shift**: adding a new dashboard column rewrites every `columns[N]` reference downstream. We bump `STORAGE_VERSION` and check the `columns` array refs are all by-id, not by-index
- **Streaming chunks**: photos up to ~4 MB come back in a single `FilePart`; larger files would need the `StartIndex`/`IsLast` loop. We'll implement the loop now to be safe, even if today's samples are ~400 KB
- **Empty FileIDs**: Kingdee returns `''` or `None` for unused slots — the join must filter to `[id for id in (f1,f2,f3) if id]`
- **Migration order**: 013 must apply cleanly on prod (which has prior 011/012). Migration is additive ADD COLUMN, no backfill required — old rows naturally get `NULL` photo IDs which downstream code treats as no-photo

## Test Cases

### Unit Tests
- [ ] `ProductionOrderModel` accepts `photo_file_id_1/2/3 = None` and arbitrary strings
- [ ] `factory.PRODUCTION_ORDER` maps `F_QWJI_YSTP1/2/3` from a mock Kingdee response into the model
- [ ] `cache_reader._row_to_production_order` correctly indexes the 3 new columns (positional row tuple test)
- [ ] `mto_handler` produces `child.photo_file_ids` as a list with empty/None values filtered out
- [ ] `/api/photo/{id}` endpoint: 200 with image bytes for valid FileID; 404 for unknown; 401 without session
- [ ] `/api/photo/{id}` sets `Cache-Control: public, max-age=31536000, immutable` and `Content-Type` from magic bytes (png/jpg detection)
- [ ] Streaming-loop logic handles `IsLast=false` correctly (mock multi-chunk response)

### Integration Tests
- [ ] Full sync run captures `photo_file_id_*` columns from a known PRD_MO (use `MO260501414` MTO `DS264102S`)
- [ ] Cache query returns photo FileIDs for that MTO
- [ ] End-to-end: hit `/api/mto/DS264102S`, verify response contains `photo_file_ids` for the right child rows

### Manual Verification
1. Sync against live Kingdee → query `DS264102S` → confirm photo IDs appear in API response
2. Load dashboard → confirm Photo column renders, badge shows on rows with photos
3. Click badge → modal opens, all 1–3 photos render with the actual product image
4. Refresh page → confirm 0 network requests for previously-viewed photos (immutable cache working)
5. Open in incognito → confirm photos still load (session auth path works for fresh sessions)
6. Query an old MTO with no photos (`DK251003S`) → confirm Photo column shows `—` and badge does not appear

## Acceptance Criteria

- [ ] Photo column visible on dashboard, between an agreed pair of existing columns (TBD: which two — probably between Material Name and Qty)
- [ ] Badge shows actual photo count (`📷×2` not just `📷`)
- [ ] Click → modal with all photos at native resolution, keyboard arrow-key navigation
- [ ] Lazy load: zero network traffic for the photo column until a badge is clicked
- [ ] Cached: re-visiting a row's photos uses browser cache (DevTools → Network → "(disk cache)")
- [ ] Unauthenticated `/api/photo/<id>` returns 401
- [ ] All existing tests pass; new unit + integration tests pass
- [ ] Migration 013 applies cleanly on prod (verify on dev first)

## Scope & non-goals

**In scope**
- `PRD_MO.TreeEntity.F_QWJI_YSTP1/2/3` photo display
- Lazy/on-demand fetch with aggressive browser caching
- Session-authenticated `/api/photo/{file_id}` endpoint

**Out of scope (defer to follow-up)**
- `F_QWJI_YSWZFJ_Files` / `F_QWJI_YSFJ` attachment fields (always empty in current data — not worth wiring until they're used)
- Photo upload/edit from QuickPulse (read-only for now)
- Image resizing / WebP optimization (Kingdee photos are already ~300–500 KB PNG)
- BD_MATERIAL master photos (confirmed empty in this tenant 2026-05-11)
- Photos on `SAL_SaleOrder` / `PUR_PurchaseOrder` (fields don't exist on those forms)

## Rough effort estimate

| Wave | Work | Effort |
|---|---|---|
| 1 | Schema migration + model + factory mapping (live path works) | ~1.5 h |
| 2 | Sync writer + cache reader + test tuples (cache path works) | ~2 h |
| 3 | `/api/photo/{id}` endpoint + auth + streaming loop | ~1.5 h |
| 4 | `ChildItem.photo_file_ids` + mto_handler join | ~1 h |
| 5 | Dashboard column + lightbox modal + STORAGE_VERSION bump | ~2 h |
| 6 | Tests (unit + integration) + manual verification on dev | ~1.5 h |
| **Total** | | **~9.5 h** (1 focused day) |

## Open questions before I start

1. **Column position**: between which two existing columns should "Photo" sit? (Suggest: right after "Material Name", before quantity columns)
2. **Badge label**: `📷×3` (count) or just `📷` (icon-only)? Suggest count for utility.
3. **Modal style**: full-screen lightbox or in-page modal? Suggest in-page modal (matches existing dashboard aesthetic) with full-screen toggle button.
4. **Multi-PRD_MO case**: an MTO can have multiple PRD_MOs, and each can carry its own photos. Show union of all photos on the child row, or only photos from the most-recent PRD_MO? Suggest **union** so the user sees everything, and deduplicate by FileID.
