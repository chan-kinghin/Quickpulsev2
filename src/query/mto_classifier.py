"""Classify a 计划跟踪号 (MTO number) into business line + order type.

The MTO prefix is a STRUCTURED code, not a fixed "AK":
  - 1st letter = business line:  A=外销, D=内销, W=瑞弧
  - 2nd letter = order type:     S=完整订单, K=备货/半成品单, Y=样品单

The order type is ALWAYS the 2nd letter. Two number formats coexist:
  - export   ``AK2604007``  (no trailing letter)
  - domestic ``DK251003S``  (the trailing literal ``S`` is part of the number,
                             NOT the order type — the order type is still ``K``)

Sub-orders carry a ``-N`` suffix, e.g. ``AS2604001-1``.

Verified against live Kingdee 2026-05-29; see
``docs/MTO_ORDER_TYPE_AND_SKU_READINESS_2026-05-29.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

UNCLASSIFIED = "未分类"

_BUSINESS_LINES = {"A": "外销", "D": "内销", "W": "瑞弧"}
_ORDER_TYPES = {"S": "完整订单", "K": "备货半成品单", "Y": "样品单"}


@dataclass(frozen=True)
class MtoClassification:
    """Parsed view of an MTO number. Pure data, no side effects."""

    raw: str  # original input (un-stripped)
    business_line: str  # uppercased 1st char ('A'/'D'/'W'/...) or '' when unparseable
    business_line_label: str  # 外销/内销/瑞弧/未分类
    order_type: str  # uppercased 2nd char ('S'/'K'/'Y'/...) or ''
    order_type_label: str  # 完整订单/备货半成品单/样品单/未分类
    is_sample: bool  # True iff order_type == 'Y'
    base_number: str  # core digits after the 2 leading letters, sub-order stripped
    sub_order: Optional[str]  # e.g. '-1', or None


def classify_mto(mto_number: Optional[str]) -> MtoClassification:
    """Classify an MTO number. Never raises; unparseable input -> 未分类.

    Args:
        mto_number: e.g. 'AK2604007', 'DS262027S', 'AS2604001-1'. None / empty /
            too-short inputs are tolerated and classified as 未分类.
    """
    raw = mto_number if isinstance(mto_number, str) else ("" if mto_number is None else str(mto_number))
    s = raw.strip()

    if len(s) < 2:
        return MtoClassification(
            raw=raw,
            business_line="",
            business_line_label=UNCLASSIFIED,
            order_type="",
            order_type_label=UNCLASSIFIED,
            is_sample=False,
            base_number="",
            sub_order=None,
        )

    business_line = s[0].upper()
    order_type = s[1].upper()

    # Split off a sub-order suffix like '-1' / '-2A' before extracting the core.
    core = s
    sub_order: Optional[str] = None
    if "-" in s:
        core, _, suffix = s.partition("-")
        sub_order = "-" + suffix

    base_number = core[2:]

    return MtoClassification(
        raw=raw,
        business_line=business_line,
        business_line_label=_BUSINESS_LINES.get(business_line, UNCLASSIFIED),
        order_type=order_type,
        order_type_label=_ORDER_TYPES.get(order_type, UNCLASSIFIED),
        is_sample=(order_type == "Y"),
        base_number=base_number,
        sub_order=sub_order,
    )
