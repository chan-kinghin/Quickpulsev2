-- 016: Add BD_MATERIAL.MaterialBase.IsPurchase to BOM cache for fine-grained
-- packaging routing.
--
-- Background: migration 015 added `category_name` (Kingdee 存货类别), and the
-- handler routes `CHLB03_SYS / 外销包材` → 包材. That's too coarse — the
-- "外销包材" category in this Fluent tenant lumps together:
--   * Fluent's SELF-MADE plastic parts (吸塑/跟型件): IsPurchase=False
--   * Truly PURCHASED packaging (外箱/内盒/隔板/纸卡/彩盒): IsPurchase=True
--
-- Users see this directly: AS2603021 had 13 distinct 外销包材 BOM codes,
-- 10 self-made and 3 purchased. Without IsPurchase, all 13 land in the 包材
-- chip — the colleague flagged "these aren't 包材, they're self-made".
--
-- Source: PRD_PPBOM field chain FMaterialId.FIsPurchase (verified 2026-05-22).
-- See docs/PLAN_fix_baocai_routing_2026-05-22.md (revision 2).

ALTER TABLE cached_production_bom ADD COLUMN is_purchase INTEGER DEFAULT 0;
