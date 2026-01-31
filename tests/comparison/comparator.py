"""Main comparison engine for QuickPulse vs Kingdee validation.

This module orchestrates the comparison process:
1. Fetch QuickPulse result via MTOQueryHandler
2. Fetch raw Kingdee data via RawKingdeeFetcher
3. Aggregate raw data via RawDataAggregator
4. Compare field by field
5. Return ComparisonResult with discrepancies
"""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from src.kingdee.client import KingdeeClient
from src.query.mto_handler import MTOQueryHandler
from tests.comparison.aggregator import RawDataAggregator
from tests.comparison.field_specs import (
    FIELD_SPECS,
    VALIDATED_FIELDS,
    ComparisonResult,
    FieldValidation,
    MaterialType,
    MaterialValidation,
    get_material_type,
)
from tests.comparison.raw_fetcher import RawKingdeeFetcher


class MTOComparator:
    """Compares QuickPulse output against raw Kingdee data."""

    def __init__(
        self,
        kingdee_client: KingdeeClient,
        mto_handler: MTOQueryHandler,
    ):
        self.kingdee_client = kingdee_client
        self.mto_handler = mto_handler
        self.raw_fetcher = RawKingdeeFetcher(kingdee_client)
        self.aggregator = RawDataAggregator()

    async def compare(self, mto: str) -> ComparisonResult:
        """Compare QuickPulse vs Kingdee data for one MTO.

        Args:
            mto: MTO number to compare

        Returns:
            ComparisonResult with validation details per material
        """
        try:
            # 1. Fetch QuickPulse result
            qp_result = await self.mto_handler.get_status(mto, use_cache=False)

            # 2. Fetch raw Kingdee data
            raw_data = await self.raw_fetcher.fetch_all(mto)

            # 3. Aggregate raw data by material type rules
            aggregated = self.aggregator.aggregate(raw_data)

            # 4. Aggregate QuickPulse by material_code (sum all aux variants)
            qp_aggregated = self._aggregate_quickpulse_by_material(qp_result.children)

            # 5. Compare aggregated QuickPulse vs aggregated Kingdee
            items: list[MaterialValidation] = []

            for material_code, qp_totals in qp_aggregated.items():
                material_type = get_material_type(material_code)
                if material_type is None:
                    continue

                # Find aggregated Kingdee data for this material
                kd_totals = self._aggregate_kingdee_by_material(
                    aggregated, material_code, material_type
                )

                # Build validations comparing totals
                validations = self._validate_totals(
                    qp_totals, kd_totals, material_type
                )

                items.append(
                    MaterialValidation(
                        material_code=material_code,
                        material_name=qp_totals.get("material_name", ""),
                        aux_attributes=None,  # Aggregated, no single aux
                        material_type=material_type,
                        validations=validations,
                    )
                )

            return ComparisonResult(mto=mto, items=items)

        except Exception as e:
            return ComparisonResult(mto=mto, items=[], error=str(e))

    def _aggregate_quickpulse_by_material(
        self,
        children,
    ) -> Dict[str, Dict[str, Decimal]]:
        """Aggregate QuickPulse children by material_code.

        Sums all quantity fields across all aux_attributes variants.
        """
        result: Dict[str, Dict[str, Decimal]] = {}

        for child in children:
            code = child.material_code
            if code not in result:
                result[code] = {
                    "material_name": child.material_name,
                    "required_qty": Decimal(0),
                    "picked_qty": Decimal(0),
                    "unpicked_qty": Decimal(0),
                    "order_qty": Decimal(0),
                    "receipt_qty": Decimal(0),
                    "unreceived_qty": Decimal(0),
                    "sales_outbound_qty": Decimal(0),
                }

            result[code]["required_qty"] += self._get_qp_value(child, "required_qty")
            result[code]["picked_qty"] += self._get_qp_value(child, "picked_qty")
            result[code]["unpicked_qty"] += self._get_qp_value(child, "unpicked_qty")
            result[code]["order_qty"] += self._get_qp_value(child, "order_qty")
            result[code]["receipt_qty"] += self._get_qp_value(child, "receipt_qty")
            result[code]["unreceived_qty"] += self._get_qp_value(child, "unreceived_qty")
            result[code]["sales_outbound_qty"] += self._get_qp_value(child, "sales_outbound_qty")

        return result

    def _aggregate_kingdee_by_material(
        self,
        aggregated,
        material_code: str,
        material_type: MaterialType,
    ) -> Dict[str, Decimal]:
        """Get Kingdee totals for a material, summing all aux variants."""
        from tests.comparison.aggregator import AggregatedMaterial

        # Find all materials matching this code
        matching = [
            mat for (code, aux), mat in aggregated.materials.items()
            if code == material_code
        ]

        if not matching:
            return {
                "required_qty": Decimal(0),
                "picked_qty": Decimal(0),
                "unpicked_qty": Decimal(0),
                "order_qty": Decimal(0),
                "receipt_qty": Decimal(0),
                "unreceived_qty": Decimal(0),
                "sales_outbound_qty": Decimal(0),
            }

        # Sum all variants
        totals = {
            "required_qty": Decimal(0),
            "picked_qty": Decimal(0),
            "order_qty": Decimal(0),
            "receipt_qty": Decimal(0),
            "app_qty": Decimal(0),
            "actual_qty": Decimal(0),
        }

        for mat in matching:
            totals["required_qty"] += mat.required_qty
            totals["picked_qty"] += mat.picked_qty
            totals["order_qty"] += mat.order_qty
            totals["receipt_qty"] += mat.receipt_qty
            totals["app_qty"] += mat.app_qty
            totals["actual_qty"] += mat.actual_qty

        # Calculate unpicked_qty based on material type
        if material_type == MaterialType.SELF_MADE:
            # For 05.xx: unpicked = FAppQty - FActualQty from PRD_PickMtrl
            totals["unpicked_qty"] = totals["app_qty"] - totals["actual_qty"]
        else:
            # For 07.xx, 03.xx: unpicked = required - picked
            totals["unpicked_qty"] = totals["required_qty"] - totals["picked_qty"]

        # Calculate unreceived_qty
        if material_type == MaterialType.PURCHASED:
            # For 03.xx: use PO's built-in FRemainStockInQty
            totals["unreceived_qty"] = sum(mat.remain_stock_in_qty for mat in matching)
        else:
            # For 07.xx, 05.xx: unreceived = order - receipt
            totals["unreceived_qty"] = totals["order_qty"] - totals["receipt_qty"]

        # sales_outbound_qty = picked_qty for finished goods
        if material_type == MaterialType.FINISHED_GOODS:
            totals["sales_outbound_qty"] = totals["picked_qty"]
        else:
            totals["sales_outbound_qty"] = Decimal(0)

        return totals

    def _validate_totals(
        self,
        qp_totals: Dict[str, Decimal],
        kd_totals: Dict[str, Decimal],
        material_type: MaterialType,
    ) -> Dict[str, FieldValidation]:
        """Validate aggregated totals between QuickPulse and Kingdee."""
        validations: Dict[str, FieldValidation] = {}

        for field_name in VALIDATED_FIELDS:
            spec = FIELD_SPECS.get(field_name)
            if not spec or not spec.validate:
                continue

            # Skip sales_outbound_qty for non-finished-goods
            if field_name == "sales_outbound_qty" and material_type != MaterialType.FINISHED_GOODS:
                continue

            qp_value = qp_totals.get(field_name, Decimal(0))
            kd_value = kd_totals.get(field_name, Decimal(0))

            validations[field_name] = FieldValidation.create(
                field_name=field_name,
                qp_value=qp_value,
                kd_value=kd_value,
            )

        return validations

    def _find_aggregated_material(
        self,
        aggregated,
        material_code: str,
        material_type: MaterialType,
    ):
        """Find aggregated material, trying multiple lookup strategies.

        QuickPulse ChildItem often doesn't have aux_prop_id, but raw data
        is keyed by (material_code, aux_prop_id). This method tries:
        1. Exact key (material_code, None) for self-made
        2. Any key starting with material_code (sum all aux variants)
        """
        from tests.comparison.aggregator import AggregatedMaterial

        # For self-made, always use material_code only
        if material_type == MaterialType.SELF_MADE:
            return aggregated.materials.get((material_code, None))

        # For other types, try to find any match by material_code
        # and sum all variants if multiple exist
        matching_materials = [
            mat for (code, aux), mat in aggregated.materials.items()
            if code == material_code
        ]

        if not matching_materials:
            return None

        if len(matching_materials) == 1:
            return matching_materials[0]

        # Sum all variants into a combined AggregatedMaterial
        combined = AggregatedMaterial(
            material_code=material_code,
            aux_prop_id=None,
            material_type=material_type,
        )
        for mat in matching_materials:
            combined.required_qty += mat.required_qty
            combined.order_qty += mat.order_qty
            combined.receipt_qty += mat.receipt_qty
            combined.stock_in_qty += mat.stock_in_qty
            combined.remain_stock_in_qty += mat.remain_stock_in_qty
            combined.picked_qty += mat.picked_qty
            combined.app_qty += mat.app_qty
            combined.actual_qty += mat.actual_qty

        return combined

    def _validate_fields(
        self,
        child,  # ChildItem from QuickPulse
        agg_mat,  # AggregatedMaterial from Kingdee (may be None)
        material_type: MaterialType,
    ) -> dict[str, FieldValidation]:
        """Validate all fields for a single material.

        Args:
            child: QuickPulse ChildItem
            agg_mat: Aggregated raw Kingdee data (may be None if not found)
            material_type: Material type classification

        Returns:
            Dictionary of field name to FieldValidation
        """
        validations: dict[str, FieldValidation] = {}

        for field_name in VALIDATED_FIELDS:
            spec = FIELD_SPECS.get(field_name)
            if not spec or not spec.validate:
                continue

            # Skip sales_outbound_qty for non-finished-goods
            if field_name == "sales_outbound_qty" and material_type != MaterialType.FINISHED_GOODS:
                continue

            # Get QuickPulse value
            qp_value = self._get_qp_value(child, field_name)

            # Get Kingdee aggregated value
            kd_value = self._get_kd_value(agg_mat, field_name)

            validations[field_name] = FieldValidation.create(
                field_name=field_name,
                qp_value=qp_value,
                kd_value=kd_value,
            )

        return validations

    def _get_qp_value(self, child, field_name: str) -> Decimal:
        """Get QuickPulse value for a field.

        Maps QuickPulse ChildItem fields to validation fields.
        """
        # Direct mapping from ChildItem attributes
        mapping = {
            "required_qty": "required_qty",
            "picked_qty": "picked_qty",
            "unpicked_qty": "unpicked_qty",
            "order_qty": "order_qty",
            "receipt_qty": "receipt_qty",
            "unreceived_qty": "unreceived_qty",
            "sales_outbound_qty": "sales_outbound_qty",
        }

        attr_name = mapping.get(field_name, field_name)
        value = getattr(child, attr_name, None)

        if value is None:
            return Decimal(0)

        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(0)

    def _get_kd_value(self, agg_mat, field_name: str) -> Decimal:
        """Get Kingdee aggregated value for a field.

        Maps field names to AggregatedMaterial properties.
        """
        if agg_mat is None:
            return Decimal(0)

        # Direct mapping from AggregatedMaterial
        mapping = {
            "required_qty": "required_qty",
            "picked_qty": "picked_qty",
            "unpicked_qty": "unpicked_qty",  # Property
            "order_qty": "order_qty",
            "receipt_qty": "receipt_qty",
            "unreceived_qty": "unreceived_qty",  # Property
            "sales_outbound_qty": "sales_outbound_qty",  # Property
        }

        attr_name = mapping.get(field_name, field_name)
        value = getattr(agg_mat, attr_name, None)

        if value is None:
            return Decimal(0)

        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(0)


async def run_batch_comparison(
    kingdee_client: KingdeeClient,
    mto_handler: MTOQueryHandler,
    mtos: list[str],
) -> list[ComparisonResult]:
    """Run comparison on a batch of MTOs.

    Args:
        kingdee_client: Kingdee API client
        mto_handler: QuickPulse MTO handler
        mtos: List of MTO numbers to compare

    Returns:
        List of ComparisonResults
    """
    comparator = MTOComparator(kingdee_client, mto_handler)
    results = []

    for mto in mtos:
        result = await comparator.compare(mto)
        results.append(result)

    return results


def generate_report(results: list[ComparisonResult]) -> str:
    """Generate a markdown report from comparison results.

    Args:
        results: List of ComparisonResults

    Returns:
        Markdown formatted report string
    """
    lines = []
    lines.append("# QuickPulse vs Kingdee Validation Report")
    lines.append("")

    # Summary
    total_mtos = len(results)
    passed_mtos = sum(1 for r in results if r.all_match and not r.error)
    failed_mtos = sum(1 for r in results if not r.all_match or r.error)
    error_mtos = sum(1 for r in results if r.error)

    lines.append("## Summary")
    lines.append(f"- **MTOs Tested**: {total_mtos}")
    lines.append(f"- **Passed**: {passed_mtos}")
    lines.append(f"- **Failed**: {failed_mtos}")
    if error_mtos:
        lines.append(f"- **Errors**: {error_mtos}")
    lines.append("")

    # Field accuracy
    field_stats: dict[str, dict[str, int]] = {}
    for field_name in VALIDATED_FIELDS:
        field_stats[field_name] = {"pass": 0, "fail": 0}

    for result in results:
        for item in result.items:
            for field_name, validation in item.validations.items():
                if validation.match:
                    field_stats[field_name]["pass"] += 1
                else:
                    field_stats[field_name]["fail"] += 1

    lines.append("## Field Accuracy")
    lines.append("")
    lines.append("| Field | Chinese | Pass | Fail | Accuracy |")
    lines.append("|-------|---------|------|------|----------|")

    for field_name in VALIDATED_FIELDS:
        spec = FIELD_SPECS.get(field_name)
        chinese = spec.chinese_name if spec else field_name
        stats = field_stats[field_name]
        total = stats["pass"] + stats["fail"]
        if total > 0:
            accuracy = f"{100 * stats['pass'] / total:.1f}%"
        else:
            accuracy = "N/A"
        lines.append(f"| {field_name} | {chinese} | {stats['pass']} | {stats['fail']} | {accuracy} |")

    lines.append("")

    # Failed MTOs
    failed_results = [r for r in results if not r.all_match or r.error]
    if failed_results:
        lines.append("## Failed MTOs")
        lines.append("")

        for result in failed_results:
            lines.append(f"### MTO: {result.mto}")

            if result.error:
                lines.append(f"**Error**: {result.error}")
                lines.append("")
                continue

            lines.append("")
            lines.append("| 物料编码 | 字段 | QuickPulse | Kingdee | Delta |")
            lines.append("|---------|------|------------|---------|-------|")

            for item in result.failed_items:
                for v in item.failed_fields:
                    lines.append(
                        f"| {item.material_code} | {v.chinese_name} | "
                        f"{v.qp_value} | {v.kd_value} | {v.delta} |"
                    )

            lines.append("")

    return "\n".join(lines)
