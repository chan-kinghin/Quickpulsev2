-- 015: Add Kingdee 存货类别 name to BOM cache for correct routing.
--
-- Background: the dashboard's 物料类型 chip (自制 / 包材 / 委外) is currently
-- routed off `material_type`, which is sourced from PPBOM.FMaterialType.
-- That field is essentially always 1 in this Fluent tenant (88,175 / 88,225
-- rows in local cache = 99.94%), so 包材 and 委外 chips never have data.
--
-- The real routing signal is `BD_MATERIAL.MaterialBase.CategoryID` (Kingdee
-- 存货类别 system enum). Sample mapping (verified 2026-05-22 probe):
--   外销包材   → 包材
--   委外加工   → 委外
--   半成品 / 主料 / 辅料 → 自制
--   包装成品   → 成品 (already handled separately)
--
-- We pull the localized name via PPBOM field chain `FMaterialId.FCategoryId`,
-- which returns the name directly. The numeric `CHLBxx_SYS` code is NOT
-- exposed via that chain, but the localized name is stable (lcid=2052 is
-- locked for this tenant) and the value set is small (~6 known categories).
--
-- See docs/PLAN_fix_baocai_routing_2026-05-22.md for the full plan.

ALTER TABLE cached_production_bom ADD COLUMN category_name TEXT DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_bom_category ON cached_production_bom(category_name);
