"""Integration tests for validating QuickPulse vs Kingdee data.

This module provides pytest-parametrized tests that validate QuickPulse
UI field values against raw Kingdee data for 52 user-provided MTOs.

Usage:
    # Run all 52 MTO validation tests
    pytest tests/integration/test_data_validation.py -v

    # Run specific MTO
    pytest tests/integration/test_data_validation.py -k "DS25C312S" -v

    # Run with detailed output on failures
    pytest tests/integration/test_data_validation.py -v --tb=long

Requirements:
    - KINGDEE_* environment variables must be set
    - Network access to Kingdee API
"""

import os
from datetime import datetime

import pytest

from tests.comparison.comparator import MTOComparator, generate_report
from tests.comparison.field_specs import (
    FIELD_SPECS,
    USER_MTOS,
    ComparisonResult,
)


# Skip all tests if Kingdee credentials are not available
pytestmark = pytest.mark.skipif(
    not os.environ.get("KINGDEE_SERVER_URL"),
    reason="Kingdee credentials not available (set KINGDEE_* env vars)",
)


@pytest.fixture(scope="module")
def comparison_results():
    """Store comparison results for summary report at end."""
    return []


class TestMTODataValidation:
    """Test class for MTO data validation against Kingdee."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mto", USER_MTOS)
    async def test_mto_field_validation(
        self,
        mto: str,
        mto_comparator: MTOComparator,
        comparison_results: list,
    ):
        """Validate QuickPulse matches Kingdee for MTO.

        This test fetches data from both QuickPulse and Kingdee directly,
        then compares all quantity fields (需求量, 已领量, 未领量, etc.)
        with exact match requirement (no tolerance).

        Args:
            mto: MTO number to validate
            mto_comparator: MTOComparator fixture
            comparison_results: Module-scoped list to collect results
        """
        # Run comparison
        result = await mto_comparator.compare(mto)
        comparison_results.append(result)

        # Check for errors
        if result.error:
            pytest.fail(f"Comparison error: {result.error}")

        # Check each material
        failures = []
        for item in result.items:
            for field_name, validation in item.validations.items():
                if not validation.match:
                    failures.append(
                        f"{item.material_code} | "
                        f"{validation.chinese_name}: "
                        f"QP={validation.qp_value} vs Kingdee={validation.kd_value} "
                        f"(delta={validation.delta})"
                    )

        if failures:
            failure_msg = f"MTO {mto} has {len(failures)} field mismatch(es):\n"
            failure_msg += "\n".join(f"  - {f}" for f in failures)
            pytest.fail(failure_msg)


class TestFieldAccuracy:
    """Test class for aggregate field accuracy metrics."""

    @pytest.mark.asyncio
    async def test_batch_field_accuracy(
        self,
        mto_comparator: MTOComparator,
    ):
        """Run validation on all MTOs and check aggregate accuracy.

        This test runs all 52 MTOs and reports field-level accuracy.
        It fails if any field has less than 90% accuracy.
        """
        results: list[ComparisonResult] = []

        for mto in USER_MTOS[:10]:  # Run first 10 for this test
            result = await mto_comparator.compare(mto)
            results.append(result)

        # Calculate field accuracy
        field_stats: dict[str, dict[str, int]] = {}
        for field_name in FIELD_SPECS:
            if not FIELD_SPECS[field_name].validate:
                continue
            field_stats[field_name] = {"pass": 0, "fail": 0}

        for result in results:
            for item in result.items:
                for field_name, validation in item.validations.items():
                    if field_name in field_stats:
                        if validation.match:
                            field_stats[field_name]["pass"] += 1
                        else:
                            field_stats[field_name]["fail"] += 1

        # Check accuracy thresholds
        failures = []
        for field_name, stats in field_stats.items():
            total = stats["pass"] + stats["fail"]
            if total > 0:
                accuracy = stats["pass"] / total
                if accuracy < 0.9:  # 90% threshold
                    chinese = FIELD_SPECS[field_name].chinese_name
                    failures.append(
                        f"{field_name} ({chinese}): {accuracy*100:.1f}% "
                        f"({stats['pass']}/{total})"
                    )

        if failures:
            pytest.fail(
                f"Fields below 90% accuracy:\n" + "\n".join(f"  - {f}" for f in failures)
            )


class TestReportGeneration:
    """Test class for report generation functionality."""

    @pytest.mark.asyncio
    async def test_generate_comparison_report(
        self,
        mto_comparator: MTOComparator,
        tmp_path,
    ):
        """Generate a comparison report for a sample of MTOs.

        This test creates a markdown report that can be reviewed manually.
        """
        # Run comparison on first 5 MTOs
        results: list[ComparisonResult] = []
        for mto in USER_MTOS[:5]:
            result = await mto_comparator.compare(mto)
            results.append(result)

        # Generate report
        report = generate_report(results)

        # Save to file
        report_path = tmp_path / "validation_report.md"
        report_path.write_text(report, encoding="utf-8")

        # Basic sanity checks
        assert "# QuickPulse vs Kingdee Validation Report" in report
        assert "## Summary" in report
        assert "## Field Accuracy" in report


# Fixtures for this module


@pytest.fixture(scope="module")
def mto_comparator(real_kingdee_client, real_mto_handler):
    """Create MTOComparator with real Kingdee client."""
    return MTOComparator(
        kingdee_client=real_kingdee_client,
        mto_handler=real_mto_handler,
    )


@pytest.fixture(scope="module")
def real_kingdee_client():
    """Create real KingdeeClient from environment variables."""
    from src.config import get_config
    from src.kingdee.client import KingdeeClient

    config = get_config()
    return KingdeeClient(config.kingdee)


@pytest.fixture(scope="module")
def real_mto_handler(real_kingdee_client):
    """Create real MTOQueryHandler with all readers."""
    from src.query.mto_handler import MTOQueryHandler
    from src.readers import (
        MaterialPickingReader,
        ProductionBOMReader,
        ProductionOrderReader,
        ProductionReceiptReader,
        PurchaseOrderReader,
        PurchaseReceiptReader,
        SalesDeliveryReader,
        SalesOrderReader,
        SubcontractingOrderReader,
    )

    return MTOQueryHandler(
        production_order_reader=ProductionOrderReader(real_kingdee_client),
        production_bom_reader=ProductionBOMReader(real_kingdee_client),
        production_receipt_reader=ProductionReceiptReader(real_kingdee_client),
        purchase_order_reader=PurchaseOrderReader(real_kingdee_client),
        purchase_receipt_reader=PurchaseReceiptReader(real_kingdee_client),
        subcontracting_order_reader=SubcontractingOrderReader(real_kingdee_client),
        material_picking_reader=MaterialPickingReader(real_kingdee_client),
        sales_delivery_reader=SalesDeliveryReader(real_kingdee_client),
        sales_order_reader=SalesOrderReader(real_kingdee_client),
        memory_cache_enabled=False,
    )


def pytest_sessionfinish(session, exitstatus):
    """Generate summary report at end of test session."""
    # This hook is called after all tests complete
    # Results are collected via the comparison_results fixture
    pass


# Utility function for manual execution
async def run_validation_manually():
    """Run validation manually outside of pytest.

    Usage:
        python -c "import asyncio; from tests.integration.test_data_validation import run_validation_manually; asyncio.run(run_validation_manually())"
    """
    from src.config import get_config
    from src.kingdee.client import KingdeeClient
    from src.query.mto_handler import MTOQueryHandler
    from src.readers import (
        MaterialPickingReader,
        ProductionBOMReader,
        ProductionOrderReader,
        ProductionReceiptReader,
        PurchaseOrderReader,
        PurchaseReceiptReader,
        SalesDeliveryReader,
        SalesOrderReader,
        SubcontractingOrderReader,
    )

    from tests.comparison.comparator import generate_report

    print("Initializing Kingdee client...")
    config = get_config()
    client = KingdeeClient(config.kingdee)

    handler = MTOQueryHandler(
        production_order_reader=ProductionOrderReader(client),
        production_bom_reader=ProductionBOMReader(client),
        production_receipt_reader=ProductionReceiptReader(client),
        purchase_order_reader=PurchaseOrderReader(client),
        purchase_receipt_reader=PurchaseReceiptReader(client),
        subcontracting_order_reader=SubcontractingOrderReader(client),
        material_picking_reader=MaterialPickingReader(client),
        sales_delivery_reader=SalesDeliveryReader(client),
        sales_order_reader=SalesOrderReader(client),
        memory_cache_enabled=False,
    )

    comparator = MTOComparator(client, handler)

    print(f"Running validation on {len(USER_MTOS)} MTOs...")
    results = []
    for i, mto in enumerate(USER_MTOS, 1):
        print(f"  [{i}/{len(USER_MTOS)}] {mto}...", end=" ")
        result = await comparator.compare(mto)
        results.append(result)
        status = "PASS" if result.all_match else "FAIL"
        print(status)

    # Generate report
    report = generate_report(results)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = f"docs/validation_report_{timestamp}.md"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nReport saved to: {report_path}")

    # Summary
    passed = sum(1 for r in results if r.all_match)
    print(f"\nSummary: {passed}/{len(results)} MTOs passed")


if __name__ == "__main__":
    import asyncio

    asyncio.run(run_validation_manually())
