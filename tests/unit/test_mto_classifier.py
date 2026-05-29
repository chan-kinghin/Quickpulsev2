"""Tests for MTO-number prefix classification (business line + order type)."""

from src.query.mto_classifier import UNCLASSIFIED, classify_mto


class TestExportOrders:
    """A 系列 = 外销 (e.g. MARES)."""

    def test_complete_order_AS(self):
        c = classify_mto("AS2604007")
        assert c.business_line == "A"
        assert c.business_line_label == "外销"
        assert c.order_type == "S"
        assert c.order_type_label == "完整订单"
        assert c.is_sample is False
        assert c.base_number == "2604007"
        assert c.sub_order is None

    def test_stockprep_order_AK(self):
        c = classify_mto("AK2604007")
        assert c.business_line_label == "外销"
        assert c.order_type_label == "备货半成品单"
        assert c.is_sample is False

    def test_sample_order_AY(self):
        c = classify_mto("AY2604007")
        assert c.business_line_label == "外销"
        assert c.order_type_label == "样品单"
        assert c.is_sample is True


class TestDomesticOrders:
    """D 系列 = 内销;尾缀字母 S 是号码的一部分,订单类型仍取第 2 个字母。"""

    def test_complete_order_DS_trailing_S(self):
        c = classify_mto("DS262027S")
        assert c.business_line_label == "内销"
        assert c.order_type == "S"
        assert c.order_type_label == "完整订单"
        assert c.base_number == "262027S"  # trailing S kept — it's part of the number

    def test_stockprep_order_DK_trailing_S(self):
        c = classify_mto("DK251003S")
        assert c.business_line_label == "内销"
        assert c.order_type_label == "备货半成品单"
        assert c.is_sample is False

    def test_domestic_sample_DY(self):
        c = classify_mto("DY2601010")
        assert c.business_line_label == "内销"
        assert c.is_sample is True


class TestOtherBusinessLines:
    def test_ruihu_WS(self):
        c = classify_mto("WS2510004")
        assert c.business_line_label == "瑞弧"
        assert c.order_type_label == "完整订单"


class TestSubOrders:
    def test_sub_order_suffix(self):
        c = classify_mto("AS2604001-1")
        assert c.order_type_label == "完整订单"
        assert c.base_number == "2604001"
        assert c.sub_order == "-1"

    def test_sub_order_multichar(self):
        c = classify_mto("AS2510071-2A")
        assert c.sub_order == "-2A"
        assert c.base_number == "2510071"


class TestRobustness:
    def test_leading_trailing_whitespace(self):
        c = classify_mto("  AK2604007  ")
        assert c.business_line_label == "外销"
        assert c.order_type_label == "备货半成品单"
        assert c.base_number == "2604007"

    def test_lowercase_is_normalized(self):
        c = classify_mto("as2604007")
        assert c.business_line_label == "外销"
        assert c.order_type_label == "完整订单"

    def test_empty_string(self):
        c = classify_mto("")
        assert c.business_line_label == UNCLASSIFIED
        assert c.order_type_label == UNCLASSIFIED
        assert c.is_sample is False

    def test_none(self):
        c = classify_mto(None)
        assert c.business_line_label == UNCLASSIFIED
        assert c.order_type_label == UNCLASSIFIED
        assert c.is_sample is False

    def test_too_short(self):
        c = classify_mto("A")
        assert c.order_type_label == UNCLASSIFIED

    def test_unknown_prefix(self):
        c = classify_mto("ZZ123")
        assert c.business_line_label == UNCLASSIFIED
        assert c.order_type_label == UNCLASSIFIED
        assert c.is_sample is False
        assert c.base_number == "123"
