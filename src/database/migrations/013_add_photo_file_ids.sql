-- 013: Add reference photo FileIDs to production orders cache.
-- Source: PRD_MO.TreeEntity.F_QWJI_YSTP1/2/3 — three Fluent-custom photo
-- slots per production-order row. Each value is a 32-char Kingdee FileID
-- (resolved via sdk.attachmentDownLoad). Old rows naturally become NULL;
-- downstream code treats NULL/empty as "no photo".
-- Wave A1 of docs/PLAN_photo_column_2026-05-11.md.
ALTER TABLE cached_production_orders ADD COLUMN photo_file_id_1 TEXT;
ALTER TABLE cached_production_orders ADD COLUMN photo_file_id_2 TEXT;
ALTER TABLE cached_production_orders ADD COLUMN photo_file_id_3 TEXT;
