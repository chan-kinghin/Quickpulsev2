"""Golden-file validation tests.

Validates that golden-file snapshots conform to the expected MTOStatusResponse schema.
"""
import json
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).parent.parent / "golden"


def get_golden_files():
    """Discover all golden JSON files."""
    if not GOLDEN_DIR.exists():
        return []
    return sorted(GOLDEN_DIR.glob("*.json"))


@pytest.mark.parametrize("golden_file", get_golden_files(), ids=lambda f: f.stem)
class TestGoldenFiles:
    def test_valid_json(self, golden_file):
        data = json.loads(golden_file.read_text())
        assert isinstance(data, dict)

    def test_has_required_fields(self, golden_file):
        data = json.loads(golden_file.read_text())
        assert "mto_number" in data
        # Accept both serialized alias and Python field name
        assert "parent_item" in data or "parent" in data
        assert "child_items" in data or "children" in data

    def test_children_is_list(self, golden_file):
        data = json.loads(golden_file.read_text())
        children = data.get("child_items", data.get("children", []))
        assert isinstance(children, list)

    def test_children_have_required_fields(self, golden_file):
        data = json.loads(golden_file.read_text())
        children = data.get("child_items", data.get("children", []))
        for i, child in enumerate(children):
            assert "material_code" in child, f"child[{i}] missing material_code"
            assert "material_type_code" in child, f"child[{i}] missing material_type_code"
            assert "material_type" in child, f"child[{i}] missing material_type"

    def test_children_count_positive(self, golden_file):
        data = json.loads(golden_file.read_text())
        children = data.get("child_items", data.get("children", []))
        assert len(children) > 0, f"Golden file {golden_file.name} has no children"

    def test_quantities_are_numeric(self, golden_file):
        data = json.loads(golden_file.read_text())
        qty_fields = [
            "sales_order_qty",
            "prod_instock_must_qty",
            "prod_instock_real_qty",
            "purchase_order_qty",
            "purchase_stock_in_qty",
            "pick_actual_qty",
        ]
        children = data.get("child_items", data.get("children", []))
        for i, child in enumerate(children):
            for field in qty_fields:
                if field in child and child[field] is not None:
                    # Quantities should be valid numbers
                    float(str(child[field]))

    def test_parent_has_mto_number(self, golden_file):
        data = json.loads(golden_file.read_text())
        parent = data.get("parent_item", data.get("parent", {}))
        assert "mto_number" in parent
        assert parent["mto_number"] == data["mto_number"]

    def test_material_type_code_valid(self, golden_file):
        data = json.loads(golden_file.read_text())
        children = data.get("child_items", data.get("children", []))
        valid_codes = {1, 2, 3}
        for i, child in enumerate(children):
            code = child.get("material_type_code")
            assert code in valid_codes, (
                f"child[{i}] material_type_code={code}, expected one of {valid_codes}"
            )
