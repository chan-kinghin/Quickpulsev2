"""Seed data for the manufacturing knowledge base.

~80 pre-defined entries covering concepts, field mappings, business rules,
query patterns, and table descriptions for the QuickPulse domain.
"""

from __future__ import annotations

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Seed entries: list of dicts matching KnowledgeEntry fields
# ---------------------------------------------------------------------------

SEED_ENTRIES: List[Dict[str, Any]] = [
    # ===================================================================
    # 1. CONCEPTS (~20)
    # ===================================================================
    {
        "concept_id": "mto",
        "category": "concept",
        "title": "MTO (计划跟踪号)",
        "content": "MTO是QuickPulse系统的核心追踪单位，代表一个客户订单从销售到生产到交付的完整生命周期。"
        "格式为AK+年份后两位+序号，例如AK2510034。所有相关单据通过MTO号关联。",
        "tags": "mto,计划跟踪号,AK,追踪,核心概念",
    },
    {
        "concept_id": "bom",
        "category": "concept",
        "title": "BOM (生产用料清单)",
        "content": "BOM记录生产订单需要的所有子项物料及数量。每个子项有物料类型（FMaterialType）："
        "1=自制件，2=外购件，3=委外件。BOM是理解物料需求和领料状态的核心。",
        "tags": "bom,用料清单,物料,子项,需求,PRD_PPBOM",
    },
    {
        "concept_id": "production_order",
        "category": "concept",
        "title": "生产订单 (PRD_MO)",
        "content": "生产订单是生产计划的核心单据，一个MTO号对应一个或多个生产订单。"
        "包含母件（成品/半成品）信息、车间、数量、状态等。生产订单的BOM展开生成子项需求。",
        "tags": "生产订单,PRD_MO,母件,计划,车间",
    },
    {
        "concept_id": "sales_order",
        "category": "concept",
        "title": "销售订单 (SAL_SaleOrder)",
        "content": "销售订单是客户需求的源头，包含客户名称、交货日期、订单数量、BOM简称等。"
        "成品（07.xx.xxx）的需求数量来自销售订单。",
        "tags": "销售订单,SAL_SaleOrder,客户,交期,需求",
    },
    {
        "concept_id": "purchase_order",
        "category": "concept",
        "title": "采购订单 (PUR_PurchaseOrder)",
        "content": "采购订单记录外购件的采购信息。包含订单数量、已入库数量、未入库数量。"
        "外购件（03.xx.xxx）的需求和到货跟踪以采购订单为基准。",
        "tags": "采购订单,PUR_PurchaseOrder,外购,采购,到货",
    },
    {
        "concept_id": "subcontracting_order",
        "category": "concept",
        "title": "委外订单 (SUB_POORDER)",
        "content": "委外订单是委托外部供应商加工的订单。委外件的物料类型为FMaterialType=3。"
        "委外入库通过STK_InStock表的bill_type_number='RKD02_SYS'入库。",
        "tags": "委外订单,SUB_POORDER,委外,外包,加工",
    },
    {
        "concept_id": "production_receipt",
        "category": "concept",
        "title": "生产入库单 (PRD_INSTOCK)",
        "content": "生产入库单记录自制件和成品的完工入库。real_qty是实际入库数量，must_qty是应入库数量。"
        "入库完成率 = SUM(real_qty) / 需求数量。",
        "tags": "生产入库,PRD_INSTOCK,入库,完工,实收",
    },
    {
        "concept_id": "purchase_receipt",
        "category": "concept",
        "title": "采购入库单 (STK_InStock)",
        "content": "采购入库单记录外购件和委外件的入库。通过bill_type_number区分："
        "RKD01_SYS=外购入库，RKD02_SYS=委外入库。查询时必须过滤文档状态B/C/D。",
        "tags": "采购入库,STK_InStock,外购入库,委外入库,RKD01_SYS,RKD02_SYS",
    },
    {
        "concept_id": "picking",
        "category": "concept",
        "title": "生产领料单 (PRD_PickMtrl)",
        "content": "生产领料单记录从仓库领取物料用于生产。app_qty是申请领料数量，"
        "actual_qty是实际领料数量。当actual_qty>需求数量时产生超领。",
        "tags": "生产领料,PRD_PickMtrl,领料,申请,实际,超领",
    },
    {
        "concept_id": "sales_delivery",
        "category": "concept",
        "title": "销售出库单 (SAL_OUTSTOCK)",
        "content": "销售出库单记录成品发货给客户。real_qty是实际出库数量，must_qty是应出库数量。"
        "成品的'领料'数据实际来自销售出库单。",
        "tags": "销售出库,SAL_OUTSTOCK,发货,出库,成品",
    },
    {
        "concept_id": "finished_goods",
        "category": "concept",
        "title": "成品 (物料编码07.xx.xxx)",
        "content": "成品是QuickPulse追踪的最终产品，物料编码以07开头。"
        "需求来自销售订单，入库来自生产入库单，出库来自销售出库单。"
        "成品的语义字段：demand_field=sales_order_qty, fulfilled_field=prod_instock_real_qty。",
        "tags": "成品,07,finished_goods,最终产品,销售",
    },
    {
        "concept_id": "self_made",
        "category": "concept",
        "title": "自制件 (物料编码05.xx.xxx)",
        "content": "自制件在工厂内部生产，物料编码以05开头，FMaterialType=1。"
        "需求来自生产订单，入库来自生产入库单，领料来自生产领料单。"
        "语义字段：demand_field=prod_instock_must_qty, fulfilled_field=prod_instock_real_qty。",
        "tags": "自制件,05,self_made,内部生产,半成品",
    },
    {
        "concept_id": "purchased_material",
        "category": "concept",
        "title": "外购件 (物料编码03.xx.xxx)",
        "content": "外购件从外部供应商采购，物料编码以03开头，FMaterialType=2。"
        "需求来自采购订单，入库来自采购入库单（RKD01_SYS），领料来自生产领料单。"
        "语义字段：demand_field=purchase_order_qty, fulfilled_field=purchase_stock_in_qty。",
        "tags": "外购件,03,purchased,采购,供应商",
    },
    {
        "concept_id": "material_type",
        "category": "concept",
        "title": "物料类型 (FMaterialType)",
        "content": "BOM中的FMaterialType字段决定物料的采购/生产方式："
        "1=自制件（内部生产），2=外购件（外部采购），3=委外件（外包加工）。"
        "物料编码前缀也标识类型：07=成品，05=自制，03=外购。",
        "tags": "物料类型,FMaterialType,自制,外购,委外,分类",
    },
    {
        "concept_id": "fulfillment_rate",
        "category": "concept",
        "title": "入库完成率 (fulfillment_rate)",
        "content": "入库完成率 = 实际入库数量 / 需求数量。100%=已完成，0%=未开始。"
        "不同物料类型的计算字段不同。50%以下为预警状态。"
        "用于快速评估订单的生产进度。",
        "tags": "入库完成率,fulfillment_rate,完成率,进度,百分比",
    },
    {
        "concept_id": "completion_status",
        "category": "concept",
        "title": "完成状态 (completion_status)",
        "content": "完成状态基于入库完成率：completed（已完成，=100%）、"
        "in_progress（进行中，0-100%）、not_started（未开始，=0%）。"
        "用于分类筛选和统计。",
        "tags": "完成状态,completion_status,已完成,进行中,未开始",
    },
    {
        "concept_id": "over_pick",
        "category": "concept",
        "title": "超领 (over-pick)",
        "content": "超领指实际领料数量超过需求数量。BOM中no_picked_qty为负数表示超领。"
        "超领量 = 实际领料 - 需求数量。前端以红色高亮显示超领项。"
        "超领可能是正常调整或异常消耗。",
        "tags": "超领,over_pick,超出,红色,异常,领料过多",
    },
    {
        "concept_id": "aux_attributes",
        "category": "concept",
        "title": "辅助属性 (FAuxPropId)",
        "content": "辅助属性用于区分同一物料的不同变体，如颜色、尺寸等。"
        "匹配入库和领料数据时需要按辅助属性分组。aux_prop_id=0表示无辅助属性。"
        "成品和自制件的入库匹配需要考虑辅助属性。",
        "tags": "辅助属性,FAuxPropId,变体,颜色,尺寸,分组匹配",
    },
    {
        "concept_id": "document_status",
        "category": "concept",
        "title": "金蝶单据状态 (FDocumentStatus)",
        "content": "金蝶单据状态码：A=创建（草稿），B=已审核，C=已确认，D=重新审核。"
        "有效单据状态为B、C、D。查询时必须排除A状态，过滤条件："
        "FDocumentStatus IN ('B', 'C', 'D')。",
        "tags": "单据状态,FDocumentStatus,审核,确认,草稿,过滤",
    },

    # ===================================================================
    # 2. FIELD MAPPINGS (~20)
    # ===================================================================
    {
        "concept_id": "field_fqty",
        "category": "field",
        "title": "FQty — 需求/订单数量",
        "content": "FQty是几乎所有源单的订单数量字段。在SAL_SaleOrder中是销售数量，"
        "在PRD_MO中是生产数量，在PUR_PurchaseOrder中是采购数量。"
        "缓存表中映射为qty或order_qty。",
        "tags": "FQty,数量,订单数量,需求,qty,order_qty",
    },
    {
        "concept_id": "field_frealqty",
        "category": "field",
        "title": "FRealQty — 实收/实发数量",
        "content": "FRealQty是入库单和出库单中的实际收发数量。"
        "PRD_INSTOCK.FRealQty = 生产实际入库数量；"
        "STK_InStock.FRealQty = 采购实际入库数量；"
        "SAL_OUTSTOCK.FRealQty = 销售实际出库数量。缓存表中映射为real_qty。",
        "tags": "FRealQty,实收,实发,入库数量,出库数量,real_qty",
    },
    {
        "concept_id": "field_fmustqty",
        "category": "field",
        "title": "FMustQty — 应收/应发数量",
        "content": "FMustQty是入库单和出库单中的应收/应发数量。"
        "表示计划中应该完成的数量，与FRealQty对比可计算完成率。"
        "缓存表中映射为must_qty。",
        "tags": "FMustQty,应收,应发,计划数量,must_qty",
    },
    {
        "concept_id": "field_fappqty",
        "category": "field",
        "title": "FAppQty — 申请领料数量",
        "content": "PRD_PickMtrl.FAppQty是领料单中的申请领料数量。"
        "与FActualQty（实际领料）对比可看出领料差异。"
        "缓存表中映射为app_qty。",
        "tags": "FAppQty,申请领料,领料申请,app_qty",
    },
    {
        "concept_id": "field_factualqty",
        "category": "field",
        "title": "FActualQty — 实际领料数量",
        "content": "PRD_PickMtrl.FActualQty是领料单中的实际领料数量。"
        "当FActualQty > 需求数量时，产生超领。"
        "缓存表中映射为actual_qty。",
        "tags": "FActualQty,实际领料,actual_qty,超领",
    },
    {
        "concept_id": "field_fstockinqty",
        "category": "field",
        "title": "FStockInQty — 累计入库数量",
        "content": "PUR_PurchaseOrder.FStockInQty是采购订单中的累计入库数量。"
        "与FQty（订单数量）对比可计算外购件的入库完成率。"
        "缓存表中映射为stock_in_qty。",
        "tags": "FStockInQty,累计入库,stock_in_qty,采购入库",
    },
    {
        "concept_id": "field_fremainstockinqty",
        "category": "field",
        "title": "FRemainStockInQty — 未入库数量",
        "content": "PUR_PurchaseOrder.FRemainStockInQty是采购订单中的未入库数量。"
        "= 订单数量 - 已入库数量。缓存表中映射为remain_stock_in_qty。",
        "tags": "FRemainStockInQty,未入库,remain_stock_in_qty,剩余",
    },
    {
        "concept_id": "field_fnopickedqty",
        "category": "field",
        "title": "FNoPickedQty — 未领料数量",
        "content": "PRD_PPBOM.FNoPickedQty是BOM中的未领料数量。"
        "负值表示超领。= 需求数量 - 已领料数量。"
        "缓存表中映射为no_picked_qty。",
        "tags": "FNoPickedQty,未领料,no_picked_qty,超领检测",
    },
    {
        "concept_id": "field_fmtono_variants",
        "category": "field",
        "title": "MTO字段名变体 (大小写敏感)",
        "content": "不同金蝶表单中MTO字段名不同且大小写敏感："
        "SAL_SaleOrder用FMtoNo，PRD_MO用FMTONo，PUR_PurchaseOrder用FMtoNo，"
        "PRD_INSTOCK用FMtoNo，STK_InStock用FMtoNo，PRD_PickMtrl用FMTONO，"
        "SAL_OUTSTOCK用FMTONO，PRD_PPBOM用FMTONO。",
        "tags": "FMtoNo,FMTONo,FMTONO,大小写,字段名,MTO字段",
    },
    {
        "concept_id": "field_fbillno",
        "category": "field",
        "title": "FBillNo — 单据编号",
        "content": "FBillNo是所有金蝶单据的编号字段。每个单据有唯一的FBillNo。"
        "用于关联不同单据，如生产订单的FBillNo与BOM的mo_bill_no对应。"
        "缓存表中映射为bill_no或mo_bill_no。",
        "tags": "FBillNo,单据编号,bill_no,mo_bill_no,关联",
    },
    {
        "concept_id": "field_fmaterialtype",
        "category": "field",
        "title": "FMaterialType — BOM物料类型",
        "content": "PRD_PPBOM.FMaterialType是BOM中标记子项物料类型的字段。"
        "1=自制件（内部生产），2=外购件（外部采购），3=委外件（外包加工）。"
        "缓存表中映射为material_type。",
        "tags": "FMaterialType,物料类型,1自制,2外购,3委外,material_type",
    },
    {
        "concept_id": "field_fmaterialid",
        "category": "field",
        "title": "FMaterialId — 物料信息",
        "content": "FMaterialId是金蝶中物料的复合字段：FMaterialId.FNumber=物料编码，"
        "FMaterialId.FName=物料名称，FMaterialId.FSpecification=规格型号。"
        "缓存表中分别映射为material_code, material_name, specification。",
        "tags": "FMaterialId,物料编码,物料名称,规格,material_code,material_name",
    },
    {
        "concept_id": "field_fbilltypeid",
        "category": "field",
        "title": "FBillTypeID — 单据类型",
        "content": "STK_InStock.FBillTypeID.FNumber用于区分入库类型：RKD01_SYS=外购入库，"
        "RKD02_SYS=委外入库。查询采购入库时需要添加此过滤条件。"
        "缓存表中映射为bill_type_number。",
        "tags": "FBillTypeID,单据类型,RKD01_SYS,RKD02_SYS,bill_type_number",
    },
    {
        "concept_id": "field_customer_delivery",
        "category": "field",
        "title": "客户与交期字段",
        "content": "SAL_SaleOrder中：FSalerId.FName=客户名称（映射为customer_name），"
        "FDeliveryDate=交货日期（映射为delivery_date）。"
        "这两个字段在cached_sales_orders表中可查询。",
        "tags": "客户,交期,FSalerId,FDeliveryDate,customer_name,delivery_date",
    },
    {
        "concept_id": "field_workshop",
        "category": "field",
        "title": "FWorkShopId — 车间",
        "content": "PRD_MO.FWorkShopId.FName是生产订单的生产车间名称。"
        "缓存表中映射为workshop。可用于按车间分组统计生产数据。",
        "tags": "车间,FWorkShopId,workshop,生产,分组",
    },
    {
        "concept_id": "field_need_picked",
        "category": "field",
        "title": "BOM需求与领料字段",
        "content": "cached_production_bom表中：need_qty=BOM需求数量（FNeedQty），"
        "picked_qty=已领料数量（FPickedQty），no_picked_qty=未领料数量（FNoPickedQty）。"
        "no_picked_qty为负数表示超领。",
        "tags": "need_qty,picked_qty,no_picked_qty,BOM,需求,领料",
    },
    {
        "concept_id": "field_bom_short_name",
        "category": "field",
        "title": "BOM简称 (bom_short_name)",
        "content": "cached_sales_orders.bom_short_name是销售订单关联的BOM简称。"
        "用于标识产品配置或版本。在前端显示为额外信息列。",
        "tags": "bom_short_name,BOM简称,产品配置,销售订单",
    },
    {
        "concept_id": "field_synced_at",
        "category": "field",
        "title": "synced_at — 同步时间",
        "content": "所有缓存表都有synced_at字段，记录数据从金蝶同步到本地的时间。"
        "可用于判断数据的新鲜度。定时同步在07:00、12:00、16:00、18:00执行。",
        "tags": "synced_at,同步时间,新鲜度,定时同步",
    },
    {
        "concept_id": "field_raw_data",
        "category": "field",
        "title": "raw_data — 原始JSON",
        "content": "大部分缓存表有raw_data字段，保存金蝶返回的原始JSON数据。"
        "可用于调试或查看未映射的字段。格式为JSON文本。",
        "tags": "raw_data,原始数据,JSON,调试",
    },

    # ===================================================================
    # 3. BUSINESS RULES (~15)
    # ===================================================================
    {
        "concept_id": "rule_doc_status_filter",
        "category": "rule",
        "title": "单据状态过滤规则",
        "content": "所有入库单查询必须过滤单据状态：FDocumentStatus IN ('B', 'C', 'D')。"
        "A状态是草稿/创建中的单据，数据不可靠，必须排除。"
        "这是系统中最重要的数据过滤规则之一。",
        "tags": "过滤,FDocumentStatus,B,C,D,规则,入库单",
    },
    {
        "concept_id": "rule_over_pick_detection",
        "category": "rule",
        "title": "超领检测规则",
        "content": "超领检测：当BOM的no_picked_qty < 0时表示超领。"
        "超领量 = |no_picked_qty|（取绝对值）。"
        "前端用红色高亮显示超领项，提醒管理者注意异常消耗。",
        "tags": "超领,检测,no_picked_qty,负数,红色,规则",
    },
    {
        "concept_id": "rule_mto_format",
        "category": "rule",
        "title": "MTO编号格式规则",
        "content": "MTO编号格式：AK + 年份后两位 + 序号。例如AK2510034表示2025年第10034个MTO。"
        "查询时MTO号区分大小写，必须完全匹配。AK是固定前缀。",
        "tags": "MTO,格式,AK,编号规则,大小写",
    },
    {
        "concept_id": "rule_material_code_prefix",
        "category": "rule",
        "title": "物料编码前缀规则",
        "content": "物料编码前缀决定物料类型：07.xx.xxx=成品，05.xx.xxx=自制件，03.xx.xxx=外购件。"
        "前缀匹配使用正则：成品^07\\.，自制^05\\.，外购^03\\.。"
        "这决定了不同的数据来源和查询路径。",
        "tags": "物料编码,前缀,07,05,03,正则,分类规则",
    },
    {
        "concept_id": "rule_receipt_type_mapping",
        "category": "rule",
        "title": "入库类型映射规则",
        "content": "入库类型通过bill_type_number区分："
        "RKD01_SYS = 外购入库（对应FMaterialType=2）；"
        "RKD02_SYS = 委外入库（对应FMaterialType=3）。"
        "查询特定类型入库时需要加此条件。",
        "tags": "入库类型,RKD01_SYS,RKD02_SYS,映射,bill_type_number",
    },
    {
        "concept_id": "rule_variant_matching",
        "category": "rule",
        "title": "变体匹配规则",
        "content": "匹配入库和领料数据时，成品和自制件需要按 (material_code, aux_prop_id) 分组。"
        "外购件按 (material_code) 分组（不区分辅助属性）。"
        "错误的分组会导致数量计算错误。",
        "tags": "变体匹配,aux_prop_id,分组,material_code,规则",
    },
    {
        "concept_id": "rule_sync_schedule",
        "category": "rule",
        "title": "数据同步规则",
        "content": "QuickPulse从金蝶定时同步数据，默认同步时间：07:00、12:00、16:00、18:00。"
        "同步范围为最近365天的数据。同步期间系统仍可查询（使用旧数据）。"
        "同步历史记录在sync_history表中。",
        "tags": "同步,定时,schedule,365天,sync_history",
    },
    {
        "concept_id": "rule_fulfillment_calculation",
        "category": "rule",
        "title": "入库完成率计算规则",
        "content": "不同物料类型的入库完成率计算方式不同："
        "成品 = prod_instock_real_qty / sales_order_qty；"
        "自制件 = prod_instock_real_qty / prod_instock_must_qty；"
        "外购件 = purchase_stock_in_qty / purchase_order_qty。",
        "tags": "入库完成率,计算,成品,自制,外购,公式",
    },
    {
        "concept_id": "rule_bom_mo_link",
        "category": "rule",
        "title": "BOM与生产订单关联规则",
        "content": "BOM通过mo_bill_no与生产订单的bill_no关联。"
        "即 cached_production_bom.mo_bill_no = cached_production_orders.bill_no。"
        "一个生产订单可以有多个BOM子项。",
        "tags": "BOM,生产订单,关联,mo_bill_no,bill_no,JOIN",
    },
    {
        "concept_id": "rule_mto_as_join_key",
        "category": "rule",
        "title": "MTO号作为关联键",
        "content": "mto_number是所有缓存表的关联键，可用于跨表JOIN查询。"
        "所有表都有mto_number字段和对应的索引。"
        "例如：JOIN cached_purchase_orders ON mto_number 来关联采购数据。",
        "tags": "mto_number,关联键,JOIN,跨表,索引",
    },
    {
        "concept_id": "rule_qty_aggregation",
        "category": "rule",
        "title": "数量聚合规则",
        "content": "同一MTO下同一物料可能有多条入库/领料记录，需要SUM聚合。"
        "例如：SUM(real_qty) AS total_receipt 来计算总入库数量。"
        "聚合时注意按material_code（和aux_prop_id）分组。",
        "tags": "聚合,SUM,数量,分组,GROUP BY,multiple records",
    },
    {
        "concept_id": "rule_cache_tables_only",
        "category": "rule",
        "title": "只允许查询缓存表",
        "content": "SQL查询只允许访问以cached_开头的缓存表和sync_history表。"
        "共10个可查询表。不允许查询系统表或其他应用表。"
        "SQL中不允许INSERT/UPDATE/DELETE等写操作。",
        "tags": "缓存表,cached_,安全,白名单,只读,SQL限制",
    },
    {
        "concept_id": "rule_limit_required",
        "category": "rule",
        "title": "SQL查询LIMIT规则",
        "content": "所有SQL查询必须包含LIMIT子句，默认LIMIT 100。"
        "这是为了保护系统性能，避免大量数据返回。"
        "系统会自动添加LIMIT如果查询中没有。",
        "tags": "LIMIT,限制,性能,100,自动添加",
    },
    {
        "concept_id": "rule_semantic_layer",
        "category": "rule",
        "title": "语义层配置规则",
        "content": "每种物料类型在mto_config.json中有semantic配置块，定义3个语义角色："
        "demand_field（需求字段）、fulfilled_field（已完成字段）、picking_field（领料字段）。"
        "MetricEngine根据这些配置计算fulfillment_rate、completion_status、over_pick_amount。",
        "tags": "语义层,semantic,demand_field,fulfilled_field,picking_field,MetricEngine",
    },

    # ===================================================================
    # 4. QUERY PATTERNS (~15)
    # ===================================================================
    {
        "concept_id": "query_mto_status",
        "category": "query_pattern",
        "title": "查询MTO的所有物料状态",
        "content": "查询某个MTO所有BOM子项的物料状态："
        "SELECT b.material_code, b.material_name, b.material_type, "
        "b.need_qty, b.picked_qty, b.no_picked_qty "
        "FROM cached_production_bom b "
        "WHERE b.mto_number = 'AK2510034' LIMIT 100;",
        "tags": "MTO,物料状态,BOM,查询,全部子项",
    },
    {
        "concept_id": "query_unfulfilled_orders",
        "category": "query_pattern",
        "title": "查询未完成入库的采购订单",
        "content": "查找外购件中还有未入库数量的订单："
        "SELECT bill_no, mto_number, material_code, material_name, "
        "order_qty, stock_in_qty, remain_stock_in_qty "
        "FROM cached_purchase_orders "
        "WHERE remain_stock_in_qty > 0 ORDER BY remain_stock_in_qty DESC LIMIT 100;",
        "tags": "未完成,入库,采购订单,remain_stock_in_qty,查询",
    },
    {
        "concept_id": "query_over_pick_items",
        "category": "query_pattern",
        "title": "查询超领物料",
        "content": "查找BOM中超领的物料项："
        "SELECT mto_number, material_code, material_name, "
        "need_qty, picked_qty, no_picked_qty "
        "FROM cached_production_bom "
        "WHERE no_picked_qty < 0 ORDER BY no_picked_qty ASC LIMIT 100;",
        "tags": "超领,no_picked_qty,负数,查询,异常",
    },
    {
        "concept_id": "query_receipt_summary",
        "category": "query_pattern",
        "title": "查询某MTO的入库汇总",
        "content": "汇总某MTO的生产入库数据："
        "SELECT material_code, SUM(real_qty) AS total_real, SUM(must_qty) AS total_must "
        "FROM cached_production_receipts "
        "WHERE mto_number = 'AK2510034' "
        "GROUP BY material_code LIMIT 100;",
        "tags": "入库汇总,SUM,分组,生产入库,材料,查询",
    },
    {
        "concept_id": "query_picking_summary",
        "category": "query_pattern",
        "title": "查询某MTO的领料汇总",
        "content": "汇总某MTO的领料数据："
        "SELECT material_code, SUM(app_qty) AS total_app, SUM(actual_qty) AS total_actual "
        "FROM cached_material_picking "
        "WHERE mto_number = 'AK2510034' "
        "GROUP BY material_code LIMIT 100;",
        "tags": "领料汇总,SUM,分组,领料,查询",
    },
    {
        "concept_id": "query_customer_orders",
        "category": "query_pattern",
        "title": "查询某客户的所有订单",
        "content": "按客户名查询销售订单："
        "SELECT bill_no, mto_number, material_name, qty, delivery_date, customer_name "
        "FROM cached_sales_orders "
        "WHERE customer_name LIKE '%客户名%' ORDER BY delivery_date LIMIT 100;",
        "tags": "客户,订单,customer_name,LIKE,查询",
    },
    {
        "concept_id": "query_delivery_upcoming",
        "category": "query_pattern",
        "title": "查询即将到期的订单",
        "content": "查找交期临近的销售订单："
        "SELECT bill_no, mto_number, material_name, qty, delivery_date, customer_name "
        "FROM cached_sales_orders "
        "WHERE delivery_date <= date('now', '+7 days') AND delivery_date >= date('now') "
        "ORDER BY delivery_date LIMIT 100;",
        "tags": "交期,即将到期,delivery_date,日期,紧急,查询",
    },
    {
        "concept_id": "query_production_by_workshop",
        "category": "query_pattern",
        "title": "按车间统计生产订单",
        "content": "按车间分组统计生产订单数量："
        "SELECT workshop, COUNT(*) AS order_count, SUM(qty) AS total_qty "
        "FROM cached_production_orders "
        "GROUP BY workshop ORDER BY order_count DESC LIMIT 100;",
        "tags": "车间,统计,GROUP BY,COUNT,生产订单,查询",
    },
    {
        "concept_id": "query_sync_history",
        "category": "query_pattern",
        "title": "查看最近同步记录",
        "content": "查看数据同步历史："
        "SELECT started_at, finished_at, status, days_back, records_synced, error_message "
        "FROM sync_history ORDER BY started_at DESC LIMIT 10;",
        "tags": "同步记录,sync_history,历史,状态,查询",
    },
    {
        "concept_id": "query_purchase_receipt_by_type",
        "category": "query_pattern",
        "title": "按类型查询采购入库",
        "content": "区分外购入库和委外入库："
        "SELECT bill_type_number, mto_number, material_code, "
        "SUM(real_qty) AS total_real "
        "FROM cached_purchase_receipts "
        "WHERE mto_number = 'AK2510034' "
        "GROUP BY bill_type_number, material_code LIMIT 100;",
        "tags": "采购入库,类型,RKD01_SYS,RKD02_SYS,分组,查询",
    },
    {
        "concept_id": "query_material_search",
        "category": "query_pattern",
        "title": "按物料编码或名称搜索",
        "content": "在生产订单中搜索物料："
        "SELECT DISTINCT mto_number, bill_no, material_code, material_name, specification "
        "FROM cached_production_orders "
        "WHERE material_code LIKE '%搜索词%' OR material_name LIKE '%搜索词%' LIMIT 100;",
        "tags": "搜索,物料,LIKE,模糊查询,material_code,material_name",
    },
    {
        "concept_id": "query_cross_table_join",
        "category": "query_pattern",
        "title": "跨表关联查询示例",
        "content": "关联生产订单和BOM查询完整信息："
        "SELECT o.mto_number, o.bill_no, o.material_name AS parent_material, "
        "b.material_code AS child_code, b.material_name AS child_name, b.need_qty "
        "FROM cached_production_orders o "
        "JOIN cached_production_bom b ON o.bill_no = b.mo_bill_no "
        "WHERE o.mto_number = 'AK2510034' LIMIT 100;",
        "tags": "JOIN,跨表,关联,生产订单,BOM,查询",
    },
    {
        "concept_id": "query_mto_count_by_month",
        "category": "query_pattern",
        "title": "按月统计MTO数量",
        "content": "统计每月的MTO数量趋势："
        "SELECT substr(create_date, 1, 7) AS month, "
        "COUNT(DISTINCT mto_number) AS mto_count "
        "FROM cached_production_orders "
        "GROUP BY substr(create_date, 1, 7) ORDER BY month DESC LIMIT 12;",
        "tags": "统计,月度,趋势,COUNT,DISTINCT,mto_number",
    },
    {
        "concept_id": "query_subcontracting_status",
        "category": "query_pattern",
        "title": "查询委外订单状态",
        "content": "查看委外订单的完成情况："
        "SELECT mto_number, material_code, order_qty, stock_in_qty, no_stock_in_qty "
        "FROM cached_subcontracting_orders "
        "WHERE no_stock_in_qty > 0 ORDER BY no_stock_in_qty DESC LIMIT 100;",
        "tags": "委外,状态,未完成,no_stock_in_qty,查询",
    },
    {
        "concept_id": "query_sales_delivery_summary",
        "category": "query_pattern",
        "title": "查询销售出库汇总",
        "content": "汇总某MTO的成品出库情况："
        "SELECT material_code, SUM(real_qty) AS total_delivered, "
        "SUM(must_qty) AS total_planned "
        "FROM cached_sales_delivery "
        "WHERE mto_number = 'AK2510034' "
        "GROUP BY material_code LIMIT 100;",
        "tags": "销售出库,汇总,成品,发货,查询",
    },

    # ===================================================================
    # 5. TABLE DESCRIPTIONS (~10)
    # ===================================================================
    {
        "concept_id": "table_production_orders",
        "category": "table",
        "title": "cached_production_orders — 生产订单缓存表",
        "content": "生产订单缓存表，存储从金蝶PRD_MO同步的生产订单数据。"
        "关键字段：mto_number, bill_no, workshop, material_code, material_name, "
        "specification, aux_attributes, aux_prop_id, qty, status, create_date。"
        "主要索引在mto_number和material_code上。",
        "tags": "cached_production_orders,生产订单,表,结构,PRD_MO",
    },
    {
        "concept_id": "table_production_bom",
        "category": "table",
        "title": "cached_production_bom — BOM缓存表",
        "content": "生产用料清单缓存表，存储从金蝶PRD_PPBOM同步的BOM数据。"
        "关键字段：mo_bill_no, mto_number, material_code, material_name, specification, "
        "aux_attributes, aux_prop_id, material_type, need_qty, picked_qty, no_picked_qty。"
        "通过mo_bill_no与生产订单关联。",
        "tags": "cached_production_bom,BOM,用料清单,表,结构,PRD_PPBOM",
    },
    {
        "concept_id": "table_purchase_orders",
        "category": "table",
        "title": "cached_purchase_orders — 采购订单缓存表",
        "content": "采购订单缓存表，存储从金蝶PUR_PurchaseOrder同步的采购数据。"
        "关键字段：bill_no, mto_number, material_code, material_name, specification, "
        "aux_attributes, aux_prop_id, order_qty, stock_in_qty, remain_stock_in_qty。",
        "tags": "cached_purchase_orders,采购订单,表,结构,PUR_PurchaseOrder",
    },
    {
        "concept_id": "table_subcontracting_orders",
        "category": "table",
        "title": "cached_subcontracting_orders — 委外订单缓存表",
        "content": "委外订单缓存表，存储从金蝶SUB_POORDER同步的委外数据。"
        "关键字段：bill_no, mto_number, material_code, order_qty, stock_in_qty, no_stock_in_qty。"
        "委外件的入库通过cached_purchase_receipts（RKD02_SYS）追踪。",
        "tags": "cached_subcontracting_orders,委外订单,表,结构,SUB_POORDER",
    },
    {
        "concept_id": "table_production_receipts",
        "category": "table",
        "title": "cached_production_receipts — 生产入库缓存表",
        "content": "生产入库单缓存表，存储从金蝶PRD_INSTOCK同步的入库数据。"
        "关键字段：bill_no, mto_number, material_code, real_qty, must_qty, aux_prop_id。"
        "同一物料可能有多条入库记录，需要SUM聚合。",
        "tags": "cached_production_receipts,生产入库,表,结构,PRD_INSTOCK",
    },
    {
        "concept_id": "table_purchase_receipts",
        "category": "table",
        "title": "cached_purchase_receipts — 采购入库缓存表",
        "content": "采购入库单缓存表，存储从金蝶STK_InStock同步的入库数据。"
        "关键字段：bill_no, mto_number, material_code, real_qty, must_qty, bill_type_number。"
        "bill_type_number区分外购入库（RKD01_SYS）和委外入库（RKD02_SYS）。",
        "tags": "cached_purchase_receipts,采购入库,表,结构,STK_InStock",
    },
    {
        "concept_id": "table_material_picking",
        "category": "table",
        "title": "cached_material_picking — 领料缓存表",
        "content": "生产领料单缓存表，存储从金蝶PRD_PickMtrl同步的领料数据。"
        "关键字段：mto_number, material_code, app_qty, actual_qty, ppbom_bill_no, aux_prop_id。"
        "actual_qty > need_qty时产生超领。",
        "tags": "cached_material_picking,领料,表,结构,PRD_PickMtrl",
    },
    {
        "concept_id": "table_sales_delivery",
        "category": "table",
        "title": "cached_sales_delivery — 销售出库缓存表",
        "content": "销售出库单缓存表，存储从金蝶SAL_OUTSTOCK同步的出库数据。"
        "关键字段：bill_no, mto_number, material_code, real_qty, must_qty, aux_prop_id。"
        "成品的出库/发货数据来自此表。",
        "tags": "cached_sales_delivery,销售出库,表,结构,SAL_OUTSTOCK",
    },
    {
        "concept_id": "table_sales_orders",
        "category": "table",
        "title": "cached_sales_orders — 销售订单缓存表",
        "content": "销售订单缓存表，存储从金蝶SAL_SaleOrder同步的销售数据。"
        "关键字段：bill_no, mto_number, material_code, material_name, specification, "
        "aux_attributes, aux_prop_id, customer_name, delivery_date, qty, bom_short_name。"
        "成品的需求数量和客户交期来自此表。",
        "tags": "cached_sales_orders,销售订单,表,结构,SAL_SaleOrder",
    },
    {
        "concept_id": "table_sync_history",
        "category": "table",
        "title": "sync_history — 同步历史表",
        "content": "数据同步历史记录表，记录每次从金蝶同步数据的结果。"
        "关键字段：started_at, finished_at, status, days_back, records_synced, error_message。"
        "可用于查看同步是否成功、同步了多少条记录。",
        "tags": "sync_history,同步历史,表,结构,状态,记录",
    },
]
