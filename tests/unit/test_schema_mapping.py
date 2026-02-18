"""Tests for Phase 3 schema mapping — comparator, RRF, discovery, report."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.schema_mapping.comparator import (
    MappingSuggestion,
    OntologyComparator,
    ROLE_DESCRIPTIONS,
    SEMANTIC_ROLES,
    exact_match_ranking,
    normalize_chinese_label,
    normalize_field_name,
    normalized_match_ranking,
    reciprocal_rank_fusion,
)
from src.agents.schema_mapping.discovery import FieldInfo, KingdeeFieldDiscovery
from src.agents.schema_mapping.report import MappingReport, _confidence_badge


# ---------------------------------------------------------------------------
# normalize_field_name
# ---------------------------------------------------------------------------


class TestNormalizeFieldName:
    """Tests for Kingdee field name normalization."""

    def test_strips_f_prefix(self):
        assert normalize_field_name("FRealQty") == "real_qty"

    def test_camel_to_snake(self):
        assert normalize_field_name("FStockInQty") == "stock_in_qty"

    def test_actual_qty(self):
        assert normalize_field_name("FActualQty") == "actual_qty"

    def test_must_qty(self):
        assert normalize_field_name("FMustQty") == "must_qty"

    def test_dot_path_replaced(self):
        result = normalize_field_name("FMaterialId.FNumber")
        assert "." not in result

    def test_plain_name_unchanged(self):
        assert normalize_field_name("qty") == "qty"

    def test_already_snake_case(self):
        assert normalize_field_name("real_qty") == "real_qty"


# ---------------------------------------------------------------------------
# normalize_chinese_label
# ---------------------------------------------------------------------------


class TestNormalizeChineseLabel:
    """Tests for Chinese label normalization to English keywords."""

    def test_real_received_qty(self):
        result = normalize_chinese_label("实收数量")
        assert "real_received" in result
        assert "qty" in result

    def test_applied_qty(self):
        result = normalize_chinese_label("申请数量")
        assert "apply" in result

    def test_stock_in_qty(self):
        result = normalize_chinese_label("入库数量")
        assert "stock_in" in result


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


class TestReciprocalRankFusion:
    """Tests for the RRF function."""

    def test_single_ranking(self):
        ranking = [("field_a", 1.0), ("field_b", 0.8), ("field_c", 0.5)]
        result = reciprocal_rank_fusion(ranking)

        # RRF scores: a=1/1=1.0, b=1/2=0.5, c=1/3=0.333
        names = [name for name, _ in result]
        assert names[0] == "field_a"
        assert names[1] == "field_b"
        assert names[2] == "field_c"

    def test_two_rankings_fusion(self):
        ranking1 = [("a", 1.0), ("b", 0.5)]
        ranking2 = [("b", 1.0), ("c", 0.5)]

        result = reciprocal_rank_fusion(ranking1, ranking2)

        # a: 1/1 = 1.0 (only in ranking1)
        # b: 1/2 + 1/1 = 1.5 (in both)
        # c: 1/2 = 0.5 (only in ranking2)
        scores = {name: score for name, score in result}
        assert scores["b"] > scores["a"]
        assert scores["a"] > scores["c"]

    def test_empty_rankings(self):
        result = reciprocal_rank_fusion([], [])
        assert result == []

    def test_three_rankings_all_agree(self):
        # All three rankings agree on the same order
        r1 = [("x", 1.0), ("y", 0.5)]
        r2 = [("x", 0.9), ("y", 0.4)]
        r3 = [("x", 0.8), ("y", 0.3)]

        result = reciprocal_rank_fusion(r1, r2, r3)

        names = [name for name, _ in result]
        assert names[0] == "x"
        assert names[1] == "y"


# ---------------------------------------------------------------------------
# Exact Match Ranking
# ---------------------------------------------------------------------------


class TestExactMatchRanking:
    """Tests for exact_match_ranking signal."""

    def test_current_role_match_gets_1_0(self):
        fields = [
            FieldInfo(name="demand_qty", current_role="demand_field"),
            FieldInfo(name="other_field"),
        ]
        ranking = exact_match_ranking(fields, "demand_field")

        assert len(ranking) == 1
        assert ranking[0][0] == "demand_qty"
        assert ranking[0][1] == 1.0

    def test_name_contains_role_gets_0_5(self):
        fields = [
            FieldInfo(name="some_demand_stuff"),
        ]
        ranking = exact_match_ranking(fields, "demand_field")

        assert len(ranking) == 1
        assert ranking[0][1] == 0.5

    def test_no_match_returns_empty(self):
        fields = [
            FieldInfo(name="unrelated_field"),
        ]
        ranking = exact_match_ranking(fields, "demand_field")
        assert ranking == []


# ---------------------------------------------------------------------------
# Normalized Match Ranking
# ---------------------------------------------------------------------------


class TestNormalizedMatchRanking:
    """Tests for normalized_match_ranking signal."""

    def test_fulfilled_field_matches_real_qty(self):
        fields = [
            FieldInfo(
                name="prod_instock_real_qty",
                provenance_kingdee_field="FRealQty",
                chinese_label="实收数量",
            ),
        ]
        ranking = normalized_match_ranking(fields, "fulfilled_field")

        assert len(ranking) > 0
        assert ranking[0][0] == "prod_instock_real_qty"
        assert ranking[0][1] > 0

    def test_demand_field_matches_order_qty(self):
        fields = [
            FieldInfo(
                name="purchase_order_qty",
                provenance_kingdee_field="FQty",
                chinese_label="订单数量",
            ),
        ]
        ranking = normalized_match_ranking(fields, "demand_field")

        assert len(ranking) > 0
        assert ranking[0][1] > 0

    def test_no_keywords_match_returns_empty(self):
        fields = [
            FieldInfo(name="material_code"),
        ]
        ranking = normalized_match_ranking(fields, "demand_field")
        assert ranking == []

    def test_unknown_role_returns_empty(self):
        fields = [FieldInfo(name="anything")]
        ranking = normalized_match_ranking(fields, "unknown_role")
        assert ranking == []


# ---------------------------------------------------------------------------
# OntologyComparator
# ---------------------------------------------------------------------------


class TestOntologyComparator:
    """Tests for the multi-signal comparator."""

    @pytest.mark.asyncio
    async def test_compare_without_llm(self):
        """Comparator should work without an LLM client (2 signals only)."""
        fields = [
            FieldInfo(
                name="demand_qty",
                current_role="demand_field",
                provenance_kingdee_field="FQty",
                chinese_label="数量",
            ),
            FieldInfo(
                name="fulfilled_qty",
                current_role="fulfilled_field",
                provenance_kingdee_field="FRealQty",
                chinese_label="实收数量",
            ),
        ]

        mock_semantic = MagicMock()
        mock_semantic.demand_field = "demand_qty"
        mock_semantic.fulfilled_field = "fulfilled_qty"
        mock_semantic.picking_field = "picking_qty"

        comparator = OntologyComparator(llm_client=None)
        suggestions = await comparator.compare(fields, mock_semantic, "finished_goods")

        assert isinstance(suggestions, list)
        assert all(isinstance(s, MappingSuggestion) for s in suggestions)
        # Should have suggestions for at least demand_field and fulfilled_field
        roles_found = {s.semantic_role for s in suggestions}
        assert "demand_field" in roles_found
        assert "fulfilled_field" in roles_found

    @pytest.mark.asyncio
    async def test_suggestions_sorted_by_confidence(self):
        """Suggestions should be sorted by confidence descending."""
        fields = [
            FieldInfo(
                name="high_match",
                current_role="demand_field",
                provenance_kingdee_field="FQty",
                chinese_label="订单数量",
            ),
            FieldInfo(
                name="low_match",
                provenance_kingdee_field="FBillNo",
            ),
        ]

        mock_semantic = MagicMock()
        mock_semantic.demand_field = "high_match"
        mock_semantic.fulfilled_field = "something"
        mock_semantic.picking_field = "something_else"

        comparator = OntologyComparator(llm_client=None)
        suggestions = await comparator.compare(fields, mock_semantic, "test_class")

        if len(suggestions) >= 2:
            assert suggestions[0].confidence >= suggestions[1].confidence

    @pytest.mark.asyncio
    async def test_bidirectional_merge_boosts_confidence(self):
        """Fields appearing in both forward and reverse should get boosted."""
        comparator = OntologyComparator(llm_client=None)

        forward = [
            MappingSuggestion(
                kingdee_field="field_a",
                semantic_role="demand_field",
                material_class="test",
                confidence=0.6,
                reasoning="forward match",
                match_signals={"exact": 0.5},
            ),
        ]
        reverse = [
            MappingSuggestion(
                kingdee_field="field_a",
                semantic_role="demand_field",
                material_class="test",
                confidence=0.7,
                reasoning="reverse match",
                match_signals={"normalized": 0.6},
            ),
        ]

        merged = comparator._merge_bidirectional(forward, reverse)

        assert len(merged) == 1
        # Bidirectional match should boost average confidence
        avg = (0.6 + 0.7) / 2
        assert merged[0].confidence >= avg
        assert "双向匹配确认" in merged[0].reasoning

    @pytest.mark.asyncio
    async def test_merge_union_of_fields(self):
        """Merge should include fields from both directions."""
        comparator = OntologyComparator(llm_client=None)

        forward = [
            MappingSuggestion(
                kingdee_field="only_forward",
                semantic_role="demand_field",
                material_class="test",
                confidence=0.5,
                reasoning="fwd",
                match_signals={"exact": 0.5},
            ),
        ]
        reverse = [
            MappingSuggestion(
                kingdee_field="only_reverse",
                semantic_role="demand_field",
                material_class="test",
                confidence=0.4,
                reasoning="rev",
                match_signals={"normalized": 0.4},
            ),
        ]

        merged = comparator._merge_bidirectional(forward, reverse)
        names = {s.kingdee_field for s in merged}
        assert "only_forward" in names
        assert "only_reverse" in names


# ---------------------------------------------------------------------------
# MappingSuggestion
# ---------------------------------------------------------------------------


class TestMappingSuggestion:
    """Tests for MappingSuggestion.to_dict()."""

    def test_to_dict(self):
        s = MappingSuggestion(
            kingdee_field="FRealQty",
            semantic_role="fulfilled_field",
            material_class="finished_goods",
            confidence=0.85,
            reasoning="Strong match",
            match_signals={"exact": 1.0, "normalized": 0.7},
        )
        d = s.to_dict()

        assert d["kingdee_field"] == "FRealQty"
        assert d["confidence"] == 0.85
        assert d["match_signals"]["exact"] == 1.0

    def test_to_dict_rounds_values(self):
        s = MappingSuggestion(
            kingdee_field="f",
            semantic_role="r",
            material_class="c",
            confidence=0.33333,
            reasoning="test",
            match_signals={"x": 0.12345},
        )
        d = s.to_dict()
        assert d["confidence"] == 0.333
        assert d["match_signals"]["x"] == 0.123


# ---------------------------------------------------------------------------
# MappingReport
# ---------------------------------------------------------------------------


class TestMappingReport:
    """Tests for report generation."""

    def test_empty_suggestions(self):
        report = MappingReport()
        result = report.generate_report([])
        assert "No mapping suggestions" in result

    def test_report_contains_summary(self):
        suggestions = [
            MappingSuggestion(
                kingdee_field="FQty",
                semantic_role="demand_field",
                material_class="finished_goods",
                confidence=0.9,
                reasoning="Test",
                match_signals={"exact": 1.0},
            ),
        ]
        report = MappingReport()
        result = report.generate_report(suggestions)

        assert "Summary" in result
        assert "finished_goods" in result
        assert "demand_field" in result
        assert "FQty" in result

    def test_report_with_custom_title(self):
        suggestions = [
            MappingSuggestion(
                kingdee_field="FQty",
                semantic_role="demand_field",
                material_class="test",
                confidence=0.8,
                reasoning="Test",
                match_signals={"exact": 0.8},
            ),
        ]
        report = MappingReport()
        result = report.generate_report(suggestions, title="Custom Report")
        assert "Custom Report" in result

    def test_diff_report_confirmed(self):
        suggestions = [
            MappingSuggestion(
                kingdee_field="demand_qty",
                semantic_role="demand_field",
                material_class="finished_goods",
                confidence=0.9,
                reasoning="Test",
                match_signals={"exact": 1.0},
            ),
        ]
        current_config = {
            "material_classes": [{
                "id": "finished_goods",
                "semantic": {
                    "demand_field": "demand_qty",
                    "fulfilled_field": "fulfilled_qty",
                    "picking_field": "picking_qty",
                },
            }],
        }
        report = MappingReport()
        result = report.generate_diff(suggestions, current_config)

        assert "CONFIRMED" in result

    def test_diff_report_change_suggested(self):
        suggestions = [
            MappingSuggestion(
                kingdee_field="new_field",
                semantic_role="demand_field",
                material_class="finished_goods",
                confidence=0.8,
                reasoning="Test",
                match_signals={"exact": 0.5},
            ),
        ]
        current_config = {
            "material_classes": [{
                "id": "finished_goods",
                "semantic": {
                    "demand_field": "old_field",
                    "fulfilled_field": "f",
                    "picking_field": "p",
                },
            }],
        }
        report = MappingReport()
        result = report.generate_diff(suggestions, current_config)

        assert "CHANGE" in result


# ---------------------------------------------------------------------------
# _confidence_badge
# ---------------------------------------------------------------------------


class TestConfidenceBadge:
    """Tests for the confidence badge helper."""

    def test_high_confidence(self):
        assert _confidence_badge(0.85) == "[HIGH]"

    def test_medium_confidence(self):
        assert _confidence_badge(0.55) == "[MED]"

    def test_low_confidence(self):
        assert _confidence_badge(0.35) == "[LOW]"

    def test_weak_confidence(self):
        assert _confidence_badge(0.1) == "[WEAK]"

    def test_boundary_high(self):
        assert _confidence_badge(0.8) == "[HIGH]"

    def test_boundary_med(self):
        assert _confidence_badge(0.5) == "[MED]"

    def test_boundary_low(self):
        assert _confidence_badge(0.3) == "[LOW]"


# ---------------------------------------------------------------------------
# FieldInfo
# ---------------------------------------------------------------------------


class TestFieldInfo:
    """Tests for FieldInfo.to_dict()."""

    def test_to_dict_minimal(self):
        fi = FieldInfo(name="test_field")
        d = fi.to_dict()
        assert d["name"] == "test_field"
        assert d["data_type"] == "TEXT"

    def test_to_dict_full(self):
        fi = FieldInfo(
            name="real_qty",
            chinese_label="实收数量",
            source_form="PRD_INSTOCK",
            data_type="REAL",
            current_role="fulfilled_field",
            provenance_kingdee_field="FRealQty",
        )
        d = fi.to_dict()

        assert d["chinese_label"] == "实收数量"
        assert d["source_form"] == "PRD_INSTOCK"
        assert d["current_role"] == "fulfilled_field"
        assert d["provenance_kingdee_field"] == "FRealQty"

    def test_to_dict_omits_none_fields(self):
        fi = FieldInfo(name="simple")
        d = fi.to_dict()
        assert "chinese_label" not in d
        assert "source_form" not in d
        assert "current_role" not in d
