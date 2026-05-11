-- 012: Add MaterialGroup.FName (BD_MATERIAL 物料分组中文名) to sales orders cache.
-- Mirrors 011 for the 07.xx finished-goods path — _build_aggregated_sales_child
-- reads from SAL_SaleOrder rather than PRD_PPBOM, so the group name must be
-- populated through the sales-order reader / cache layer as well.
-- Phase 1 of docs/PLAN_material_category_display_2026-05-09.md.
ALTER TABLE cached_sales_orders ADD COLUMN material_group_name TEXT DEFAULT '';
