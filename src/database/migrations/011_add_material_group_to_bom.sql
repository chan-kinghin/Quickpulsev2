-- 011: Add MaterialGroup.FName (BD_MATERIAL 物料分组中文名) to BOM cache.
-- Source: PRD_PPBOM FieldKeys "FMaterialId.FMaterialGroup" — single-chain
-- returns the localised group name directly (e.g. "硅胶防水袋"). Empty
-- string for materials with no group assignment.
-- Phase 1 of docs/PLAN_material_category_display_2026-05-09.md.
ALTER TABLE cached_production_bom ADD COLUMN material_group_name TEXT DEFAULT '';
