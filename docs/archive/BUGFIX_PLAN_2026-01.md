# QuickPulse V2 Dashboard Bug Fixes

## Status: In Progress

| Issue | Status | Notes |
|-------|--------|-------|
| JWT token expires too quickly | ⬜ Pending | Change 30min → 24hr |
| SQLite ON CONFLICT constraint errors | ⬜ Pending | Add aux_prop_id to indexes |
| Wrong Kingdee form ID for subcontracting | ⬜ Pending | SUB_POORDER → SUB_SUBREQORDER |

> **Update this table** as fixes are applied. Mark ✅ when complete.

---

## Design Spec

### Problem
Three issues affecting QuickPulse V2 dashboard stability:
1. JWT token expires too quickly (30 minutes), causing frequent re-logins
2. SQLite sync errors due to constraint mismatches
3. Wrong Kingdee form ID for subcontracting orders

### Solution
Apply targeted fixes to each issue as detailed below.

### Files to Modify
| File | Change |
|------|--------|
| `src/api/routers/auth.py` | Line 17: Change 30 → 1440 |
| `src/database/migrations/001_add_unique_constraints.sql` | Add aux_prop_id to 2 indexes |
| `src/readers/factory.py` | Line 293: SUB_POORDER → SUB_SUBREQORDER |

---

## Issue 1: Extend JWT Token Expiration

### Problem
Tokens expire after 30 minutes, causing frequent re-logins.

### Solution
Change `ACCESS_TOKEN_EXPIRE_MINUTES` from 30 to 1440 (24 hours).

### File to Modify
- `src/api/routers/auth.py` (line 17)

### Change
```python
# Before
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# After
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours
```

---

## Issue 2: Fix SQLite ON CONFLICT Constraint Errors

### Problem
Sync service fails with "ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint" because:
- `cached_production_receipts`: Unique index is `(mto_number, material_code)` but upsert uses `(mto_number, material_code, aux_prop_id)`
- `cached_sales_delivery`: Same mismatch

### Solution
Update the migration file to include `aux_prop_id` in the unique constraints to match the sync_service.py upsert statements.

### Files to Modify
- `src/database/migrations/001_add_unique_constraints.sql`

### Changes
```sql
-- Before (line 19-20)
CREATE UNIQUE INDEX IF NOT EXISTS idx_prdr_unique
ON cached_production_receipts(mto_number, material_code);

-- After
DROP INDEX IF EXISTS idx_prdr_unique;
CREATE UNIQUE INDEX IF NOT EXISTS idx_prdr_unique
ON cached_production_receipts(mto_number, material_code, aux_prop_id);

-- Before (line 31-32)
CREATE UNIQUE INDEX IF NOT EXISTS idx_sald_unique
ON cached_sales_delivery(mto_number, material_code);

-- After
DROP INDEX IF EXISTS idx_sald_unique;
CREATE UNIQUE INDEX IF NOT EXISTS idx_sald_unique
ON cached_sales_delivery(mto_number, material_code, aux_prop_id);
```

### Post-fix Action
After deploying, recreate the database or run migration to apply new indexes:
```bash
docker exec quickpulse-v2 rm -f /app/data/quickpulse.db
docker restart quickpulse-v2
```

---

## Issue 3: Fix Subcontracting Order Form ID

### Problem
Code uses `SUB_POORDER` but the correct Kingdee form ID is `SUB_SUBREQORDER`.

**Verified via API test:**
- `SUB_POORDER`: Returns error "业务对象不存在"
- `SUB_SUBREQORDER`: Returns valid data `[["SUB00000001"]]`

### Solution
Change form ID from `SUB_POORDER` to `SUB_SUBREQORDER`.

### Files to Modify
1. `src/readers/factory.py` (line 293)

### Changes
```python
# Before (line 293)
SUBCONTRACTING_ORDER_CONFIG = ReaderConfig(
    form_id="SUB_POORDER",

# After
SUBCONTRACTING_ORDER_CONFIG = ReaderConfig(
    form_id="SUB_SUBREQORDER",
```

### Note
The field mappings (FBillNo, FMtoNo, FQty, etc.) should be verified against SUB_SUBREQORDER schema, but basic fields like FBillNo work.

---

## Test Cases

### Unit Tests
- [ ] Test JWT token creation with 1440 minute expiration
- [ ] Test sync_service upsert with aux_prop_id in unique constraint
- [ ] Test SUB_SUBREQORDER form ID returns valid data

### Integration Tests
- [ ] Full sync cycle completes without constraint errors
- [ ] Subcontracting order queries return expected data

### Manual Verification
1. **Token expiration**: Login, wait 30+ minutes, verify queries still work
2. **SQLite sync**: Trigger sync via API or wait for scheduled sync, check logs for errors:
   ```bash
   docker logs quickpulse-v2 2>&1 | grep -i "conflict\|error"
   ```
3. **SUB_SUBREQORDER**: Check logs no longer show "SUB_POORDER" errors:
   ```bash
   docker logs quickpulse-v2 2>&1 | grep "SUB_POORDER"
   ```

---

## Acceptance Criteria

- [ ] Users stay logged in for 24 hours without re-authentication
- [ ] Sync completes without "ON CONFLICT" errors in logs
- [ ] Subcontracting order queries return data (no "业务对象不存在" errors)

---

## Deployment Steps

1. Make code changes locally
2. Rebuild and push Docker image:
   ```bash
   docker build -t dev-quickpulse .
   docker save dev-quickpulse | ssh ubuntu@175.27.161.234 'docker load'
   ```
3. On server, recreate database and restart:
   ```bash
   ssh ubuntu@175.27.161.234
   docker exec quickpulse-v2 rm -f /app/data/quickpulse.db
   docker restart quickpulse-v2
   ```
