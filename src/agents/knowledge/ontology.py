"""Manufacturing domain ontology — core concepts for the QuickPulse knowledge base.

Defines ~20 domain concepts covering MTO tracking, material types, production
documents, receipts, picking, delivery, and semantic metrics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DomainConcept:
    """A single concept in the manufacturing domain ontology.

    Attributes:
        id: Unique identifier (e.g., "mto", "bom", "receipt").
        name_zh: Chinese name.
        name_en: English name.
        description: Detailed Chinese description.
        category: One of "process", "document", "field", "metric", "rule".
        related_concepts: IDs of related concepts.
        kingdee_forms: Related Kingdee form IDs.
        example: Optional usage example.
    """

    id: str
    name_zh: str
    name_en: str
    description: str
    category: str  # "process" | "document" | "field" | "metric" | "rule"
    related_concepts: List[str] = field(default_factory=list)
    kingdee_forms: List[str] = field(default_factory=list)
    example: Optional[str] = None


# ---------------------------------------------------------------------------
# Core manufacturing concepts (~20)
# ---------------------------------------------------------------------------

DOMAIN_CONCEPTS: List[DomainConcept] = [
    # --- Process concepts ---
    DomainConcept(
        id="mto",
        name_zh="计划跟踪号",
        name_en="MTO Number",
        description="MTO（Make-To-Order）是QuickPulse系统的核心追踪单位。"
        "每个MTO号代表一个客户订单的生产追踪流水，格式为AK+年份后两位+序号（如AK2510034）。"
        "系统通过MTO号关联销售订单、生产订单、BOM、采购、入库、领料、出库等所有单据。",
        category="process",
        related_concepts=["production_order", "sales_order", "bom"],
        kingdee_forms=["PRD_MO", "SAL_SaleOrder", "PUR_PurchaseOrder"],
        example="查询 MTO AK2510034 的所有物料状态",
    ),
    DomainConcept(
        id="production_order",
        name_zh="生产订单",
        name_en="Production Order",
        description="生产订单（PRD_MO）是生产计划的核心单据，记录需要生产的成品或半成品信息。"
        "每个生产订单关联一个MTO号，包含物料编码、规格、数量、车间、状态等信息。"
        "生产订单的子项通过BOM（生产用料清单）展开。",
        category="document",
        related_concepts=["mto", "bom", "production_receipt"],
        kingdee_forms=["PRD_MO"],
    ),
    DomainConcept(
        id="bom",
        name_zh="生产用料清单",
        name_en="Production BOM",
        description="BOM（Bill of Materials，PRD_PPBOM）记录生产订单需要的所有子项物料。"
        "每个子项有物料类型（FMaterialType）：1=自制件、2=外购件、3=委外件。"
        "BOM中的need_qty是需求数量，picked_qty是已领料数量，no_picked_qty是未领料数量。",
        category="document",
        related_concepts=["production_order", "material_type", "picking"],
        kingdee_forms=["PRD_PPBOM"],
    ),
    DomainConcept(
        id="sales_order",
        name_zh="销售订单",
        name_en="Sales Order",
        description="销售订单（SAL_SaleOrder）是客户需求的源头，包含客户名称、交期、数量等。"
        "成品（07.xx.xxx）的需求数量来源于销售订单。"
        "销售订单通过MTO号与生产订单关联。",
        category="document",
        related_concepts=["mto", "finished_goods", "sales_delivery"],
        kingdee_forms=["SAL_SaleOrder"],
    ),
    DomainConcept(
        id="purchase_order",
        name_zh="采购订单",
        name_en="Purchase Order",
        description="采购订单（PUR_PurchaseOrder）是外购件的采购单据。"
        "包含订单数量（order_qty）、已入库数量（stock_in_qty）、未入库数量（remain_stock_in_qty）。"
        "外购件（03.xx.xxx）的需求数量来源于采购订单。",
        category="document",
        related_concepts=["mto", "purchased_material", "purchase_receipt"],
        kingdee_forms=["PUR_PurchaseOrder"],
    ),
    DomainConcept(
        id="subcontracting_order",
        name_zh="委外订单",
        name_en="Subcontracting Order",
        description="委外订单（SUB_POORDER）是委外加工的订单单据。"
        "委外件（FMaterialType=3）通过委外订单下发给外部供应商加工。"
        "包含订单数量、已入库数量、未入库数量。",
        category="document",
        related_concepts=["mto", "material_type"],
        kingdee_forms=["SUB_POORDER"],
    ),

    # --- Receipt / delivery documents ---
    DomainConcept(
        id="production_receipt",
        name_zh="生产入库单",
        name_en="Production Receipt",
        description="生产入库单（PRD_INSTOCK）记录自制件和成品的入库情况。"
        "real_qty是实际入库数量，must_qty是应入库数量。"
        "入库完成率 = real_qty / must_qty。",
        category="document",
        related_concepts=["production_order", "fulfillment_rate"],
        kingdee_forms=["PRD_INSTOCK"],
    ),
    DomainConcept(
        id="purchase_receipt",
        name_zh="采购入库单",
        name_en="Purchase Receipt",
        description="采购入库单（STK_InStock）记录外购件和委外件的入库。"
        "通过bill_type_number区分：RKD01_SYS=外购入库，RKD02_SYS=委外入库。"
        "文档状态必须是B（已审核）、C（已确认）或D（重新审核）才有效。",
        category="document",
        related_concepts=["purchase_order", "document_status"],
        kingdee_forms=["STK_InStock"],
    ),
    DomainConcept(
        id="picking",
        name_zh="生产领料",
        name_en="Material Picking",
        description="生产领料单（PRD_PickMtrl）记录从仓库领取物料用于生产的情况。"
        "app_qty是申请领料数量，actual_qty是实际领料数量。"
        "当actual_qty > 需求数量时，产生超领（over-pick）。",
        category="document",
        related_concepts=["bom", "over_pick"],
        kingdee_forms=["PRD_PickMtrl"],
    ),
    DomainConcept(
        id="sales_delivery",
        name_zh="销售出库",
        name_en="Sales Delivery",
        description="销售出库单（SAL_OUTSTOCK）记录成品发货给客户的情况。"
        "real_qty是实际出库数量，must_qty是应出库数量。"
        "成品的领料数据来自销售出库单。",
        category="document",
        related_concepts=["sales_order", "finished_goods"],
        kingdee_forms=["SAL_OUTSTOCK"],
    ),

    # --- Material types ---
    DomainConcept(
        id="finished_goods",
        name_zh="成品",
        name_en="Finished Goods",
        description="成品的物料编码以07开头（如07.xx.xxx），FMaterialType=1。"
        "成品的需求数量来自销售订单，入库数据来自生产入库单，领料/发货数据来自销售出库单。"
        "成品是QuickPulse追踪的最终产品。",
        category="process",
        related_concepts=["material_type", "sales_order", "production_receipt"],
        kingdee_forms=["SAL_SaleOrder", "PRD_INSTOCK", "SAL_OUTSTOCK"],
    ),
    DomainConcept(
        id="self_made",
        name_zh="自制件",
        name_en="Self-Made Parts",
        description="自制件的物料编码以05开头（如05.xx.xxx），FMaterialType=1。"
        "自制件的需求数量来自生产订单，入库数据来自生产入库单，领料数据来自生产领料单。"
        "自制件在工厂内部生产。",
        category="process",
        related_concepts=["material_type", "production_order", "picking"],
        kingdee_forms=["PRD_MO", "PRD_INSTOCK", "PRD_PickMtrl"],
    ),
    DomainConcept(
        id="purchased_material",
        name_zh="外购件",
        name_en="Purchased Material",
        description="外购件的物料编码以03开头（如03.xx.xxx），FMaterialType=2。"
        "外购件的需求数量来自采购订单，入库数据来自采购入库单（RKD01_SYS），领料数据来自生产领料单。"
        "外购件从外部供应商采购。",
        category="process",
        related_concepts=["material_type", "purchase_order", "purchase_receipt"],
        kingdee_forms=["PUR_PurchaseOrder", "STK_InStock", "PRD_PickMtrl"],
    ),
    DomainConcept(
        id="material_type",
        name_zh="物料类型",
        name_en="Material Type",
        description="物料类型决定了物料的采购/生产方式和数据来源。"
        "BOM中的FMaterialType字段：1=自制件（内部生产），2=外购件（外部采购），3=委外件（外包加工）。"
        "物料编码前缀也标识类型：07=成品，05=自制，03=外购。",
        category="process",
        related_concepts=["finished_goods", "self_made", "purchased_material"],
        kingdee_forms=["PRD_PPBOM"],
    ),

    # --- Metrics ---
    DomainConcept(
        id="fulfillment_rate",
        name_zh="入库完成率",
        name_en="Fulfillment Rate",
        description="入库完成率 = 实际入库数量 / 需求数量。"
        "100% 表示已完成，0% 表示未开始，50% 以下为预警状态。"
        "不同物料类型的需求和入库字段来源不同。",
        category="metric",
        related_concepts=["completion_status", "production_receipt"],
        kingdee_forms=[],
    ),
    DomainConcept(
        id="completion_status",
        name_zh="完成状态",
        name_en="Completion Status",
        description="完成状态根据入库完成率计算：completed（已完成，100%）、"
        "in_progress（进行中，0-100%）、not_started（未开始，0%）。"
        "用于快速判断物料的生产进度。",
        category="metric",
        related_concepts=["fulfillment_rate"],
        kingdee_forms=[],
    ),
    DomainConcept(
        id="over_pick",
        name_zh="超领",
        name_en="Over-Pick",
        description="超领是指实际领料数量超过需求数量的情况。"
        "当BOM中的no_picked_qty为负数时，表示发生了超领。"
        "超领量 = 实际领料 - 需求数量。超领在前端以红色高亮显示。",
        category="metric",
        related_concepts=["picking", "bom"],
        kingdee_forms=["PRD_PickMtrl"],
    ),

    # --- Rules ---
    DomainConcept(
        id="document_status",
        name_zh="单据状态",
        name_en="Document Status",
        description="金蝶单据状态码：A=创建（草稿），B=已审核，C=已确认，D=重新审核。"
        "查询时只应包含B、C、D状态的单据，排除A（草稿）状态。"
        "过滤条件：FDocumentStatus IN ('B', 'C', 'D')。",
        category="rule",
        related_concepts=["production_receipt", "purchase_receipt"],
        kingdee_forms=["PRD_INSTOCK", "STK_InStock"],
    ),
    DomainConcept(
        id="mto_format",
        name_zh="MTO编号格式",
        name_en="MTO Number Format",
        description="MTO编号格式为AK+年份后两位+序号，例如AK2510034。"
        "AK是固定前缀，25是2025年，10034是序号。"
        "查询时MTO号区分大小写。",
        category="rule",
        related_concepts=["mto"],
        kingdee_forms=[],
    ),
    DomainConcept(
        id="aux_attributes",
        name_zh="辅助属性",
        name_en="Auxiliary Attributes",
        description="辅助属性（FAuxPropId）用于区分同一物料的不同变体（如颜色、尺寸）。"
        "在匹配入库、领料数据时，需要按辅助属性分组匹配，避免不同变体的数据混淆。"
        "aux_prop_id为0表示无辅助属性。",
        category="field",
        related_concepts=["bom", "production_receipt"],
        kingdee_forms=["PRD_PPBOM", "PRD_INSTOCK", "STK_InStock"],
    ),
]


def get_concept(concept_id: str) -> Optional[DomainConcept]:
    """Look up a domain concept by ID."""
    for concept in DOMAIN_CONCEPTS:
        if concept.id == concept_id:
            return concept
    return None


def get_concepts_by_category(category: str) -> List[DomainConcept]:
    """Return all concepts in a given category."""
    return [c for c in DOMAIN_CONCEPTS if c.category == category]
