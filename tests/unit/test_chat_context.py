"""Tests for chat context builders."""

import pytest

from src.chat.context import build_mto_context, build_sql_result_context


class TestBuildMtoContext:
    """Tests for build_mto_context()."""

    def test_basic_mto_context(self):
        data = {
            "parent_item": {
                "mto_number": "AK2510034",
                "customer_name": "Test Inc",
                "delivery_date": "2025-03-01",
                "material_name": "产品A",
            },
            "child_items": [
                {
                    "material_code": "05.01.001",
                    "material_name": "零件1",
                    "material_type_code": 1,
                    "prod_instock_must_qty": 100,
                    "prod_instock_real_qty": 50,
                },
                {
                    "material_code": "03.01.001",
                    "material_name": "物料2",
                    "material_type_code": 2,
                    "purchase_order_qty": 200,
                    "purchase_stock_in_qty": 200,
                },
            ],
        }
        result = build_mto_context(data)
        assert "AK2510034" in result
        assert "Test Inc" in result
        assert "零件1" in result
        assert "物料2" in result

    def test_empty_data(self):
        result = build_mto_context({})
        assert "MTO:" in result

    def test_no_children(self):
        data = {
            "parent_item": {"mto_number": "AK2510034"},
            "child_items": [],
        }
        result = build_mto_context(data)
        assert "AK2510034" in result

    def test_truncation_over_max_items(self):
        children = [
            {
                "material_code": f"05.01.{i:03d}",
                "material_name": f"Part{i}",
                "material_type_code": 1,
            }
            for i in range(30)
        ]
        data = {
            "parent_item": {"mto_number": "AK2510034"},
            "child_items": children,
        }
        result = build_mto_context(data)
        assert "其他" in result  # Should mention truncated items

    def test_metrics_included(self):
        data = {
            "parent_item": {"mto_number": "AK2510034"},
            "child_items": [
                {
                    "material_code": "05.01.001",
                    "material_name": "零件",
                    "material_type_code": 1,
                    "metrics": {
                        "fulfillment_rate": {
                            "label": "完成率",
                            "value": "0.75",
                        }
                    },
                }
            ],
        }
        result = build_mto_context(data)
        assert "完成率" in result


class TestBuildSqlResultContext:
    """Tests for build_sql_result_context()."""

    def test_basic_table(self):
        rows = [(1, "AK2510034", 100), (2, "AK2510035", 200)]
        cols = ["id", "mto_number", "qty"]
        result = build_sql_result_context(rows, cols)
        assert "id" in result
        assert "AK2510034" in result
        assert "---" in result  # Separator

    def test_empty_rows(self):
        result = build_sql_result_context([], ["col1"])
        assert "无结果" in result

    def test_truncation(self):
        rows = [(i,) for i in range(100)]
        cols = ["id"]
        result = build_sql_result_context(rows, cols)
        assert "共 100 行" in result
        assert "前 50 行" in result

    def test_none_values(self):
        rows = [(1, None, "test")]
        cols = ["a", "b", "c"]
        result = build_sql_result_context(rows, cols)
        assert "| 1 |  | test |" in result
