"""Unit tests for src/readers/inventory.py."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.kingdee.client import KingdeeClient
from src.readers.inventory import InventoryReader, sanitize_query


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_client() -> KingdeeClient:
    """Return a KingdeeClient whose SDK is replaced by AsyncMocks."""
    cfg = MagicMock()
    client = KingdeeClient(cfg)
    client.query = AsyncMock(return_value=[])
    client.query_all = AsyncMock(return_value=[])
    return client


def make_reader(client: Optional[KingdeeClient] = None) -> InventoryReader:
    return InventoryReader(client or make_client())


# ---------------------------------------------------------------------------
# sanitize_query — accept cases
# ---------------------------------------------------------------------------

def test_sanitize_accepts_chinese():
    assert sanitize_query("潜水镜") == "潜水镜"


def test_sanitize_accepts_code():
    assert sanitize_query("07.01.001") == "07.01.001"


def test_sanitize_accepts_spec():
    assert sanitize_query("GT38-BLK") == "GT38-BLK"


def test_sanitize_strips_whitespace():
    assert sanitize_query("  GT38  ") == "GT38"


# ---------------------------------------------------------------------------
# sanitize_query — reject cases
# ---------------------------------------------------------------------------

def test_sanitize_rejects_too_short():
    with pytest.raises(ValueError):
        sanitize_query("a")


def test_sanitize_rejects_quote():
    with pytest.raises(ValueError):
        sanitize_query("a';DROP")


def test_sanitize_rejects_semicolon():
    with pytest.raises(ValueError):
        sanitize_query("ab;cd")


def test_sanitize_rejects_parens():
    with pytest.raises(ValueError):
        sanitize_query("ab(cd)")


# ---------------------------------------------------------------------------
# search_materials
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_returns_material_match_list():
    client = make_client()
    client.query = AsyncMock(return_value=[
        {"FNumber": "07.01.001", "FName": "潜水镜", "FSpecification": "GT38-BLK", "FErpClsID": "9"},
        {"FNumber": "07.01.002", "FName": "潜水镜Pro", "FSpecification": "GT40-RED", "FErpClsID": "9"},
    ])
    reader = make_reader(client)
    resp = await reader.search_materials("潜水镜")
    assert len(resp.items) == 2
    assert resp.total == 2
    assert resp.items[0].material_code == "07.01.001"
    assert resp.items[1].material_name == "潜水镜Pro"


@pytest.mark.asyncio
async def test_search_filter_includes_forbidden_clause():
    client = make_client()
    reader = make_reader(client)
    await reader.search_materials("GT38")
    call_kwargs = client.query.call_args
    filter_string = call_kwargs.kwargs.get("filter_string") or call_kwargs[1].get("filter_string") or call_kwargs[0][2]
    assert "FForbidStatus = 'A'" in filter_string


@pytest.mark.asyncio
async def test_search_filter_uses_or_across_three_fields():
    client = make_client()
    reader = make_reader(client)
    await reader.search_materials("GT38")
    call_kwargs = client.query.call_args
    # Retrieve filter_string however it was passed (positional or keyword)
    args = call_kwargs[0]
    kwargs = call_kwargs[1]
    filter_string = kwargs.get("filter_string", args[2] if len(args) > 2 else "")
    assert "FNumber like" in filter_string
    assert "FName like" in filter_string
    assert "FSpecification like" in filter_string
    # Must use OR to join the three LIKE conditions
    assert " or " in filter_string.lower()


@pytest.mark.asyncio
async def test_search_caps_at_fifty_even_if_limit_higher():
    client = make_client()
    reader = make_reader(client)
    await reader.search_materials("GT38", limit=200)
    call_kwargs = client.query.call_args
    args = call_kwargs[0]
    kwargs = call_kwargs[1]
    limit_passed = kwargs.get("limit", args[3] if len(args) > 3 else None)
    assert limit_passed <= 50


@pytest.mark.asyncio
async def test_search_resolves_erp_class_label():
    client = make_client()
    client.query = AsyncMock(return_value=[
        {"FNumber": "07.01.001", "FName": "潜水镜", "FSpecification": "", "FErpClsID": "9"},
    ])
    reader = make_reader(client)
    resp = await reader.search_materials("潜水镜")
    assert resp.items[0].erp_class == "9"
    assert resp.items[0].erp_class_label == "成品"


@pytest.mark.asyncio
async def test_search_handles_empty_kingdee_response():
    client = make_client()
    client.query = AsyncMock(return_value=[])
    reader = make_reader(client)
    resp = await reader.search_materials("不存在的物料xx")
    assert resp.items == []
    assert resp.total == 0


# ---------------------------------------------------------------------------
# get_inventory_by_material
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_inventory_returns_warehouse_rows():
    client = make_client()

    def query_side_effect(form_id, field_keys, filter_string="", limit=2000, start_row=0, **kwargs):
        if form_id == "BD_MATERIAL":
            return [{"FNumber": "07.01.001", "FName": "潜水镜", "FSpecification": "GT38", "FErpClsID": "9"}]
        return []

    client.query = AsyncMock(side_effect=query_side_effect)
    client.query_all = AsyncMock(return_value=[
        {"FMaterialId.FNumber": "07.01.001", "FStockId.FNumber": "WH01", "FStockId.FName": "外销成品仓",
         "FAuxPropId": 0, "FLot.FNumber": "", "FBaseQty": "100", "FStockOrgId.FName": "福伦特"},
        {"FMaterialId.FNumber": "07.01.001", "FStockId.FNumber": "WH02", "FStockId.FName": "备货仓",
         "FAuxPropId": 0, "FLot.FNumber": "L001", "FBaseQty": "50", "FStockOrgId.FName": "福伦特"},
        {"FMaterialId.FNumber": "07.01.001", "FStockId.FNumber": "WH01", "FStockId.FName": "外销成品仓",
         "FAuxPropId": 0, "FLot.FNumber": "L002", "FBaseQty": "30", "FStockOrgId.FName": "福伦特"},
    ])
    reader = make_reader(client)
    detail = await reader.get_inventory_by_material("07.01.001")
    assert len(detail.rows) == 3
    assert detail.warehouse_count == 2
    assert detail.total_qty == Decimal("180")


@pytest.mark.asyncio
async def test_inventory_default_filters_zero():
    client = make_client()
    client.query = AsyncMock(return_value=[
        {"FNumber": "07.01.001", "FName": "潜水镜", "FSpecification": "", "FErpClsID": "9"},
    ])
    client.query_all = AsyncMock(return_value=[])
    reader = make_reader(client)
    await reader.get_inventory_by_material("07.01.001", include_zero=False)
    call_kwargs = client.query_all.call_args
    args = call_kwargs[0]
    kwargs = call_kwargs[1]
    filter_string = kwargs.get("filter_string", args[2] if len(args) > 2 else "")
    assert "FBaseQty <> 0" in filter_string


@pytest.mark.asyncio
async def test_inventory_include_zero_drops_filter():
    client = make_client()
    client.query = AsyncMock(return_value=[
        {"FNumber": "07.01.001", "FName": "潜水镜", "FSpecification": "", "FErpClsID": "9"},
    ])
    client.query_all = AsyncMock(return_value=[])
    reader = make_reader(client)
    await reader.get_inventory_by_material("07.01.001", include_zero=True)
    call_kwargs = client.query_all.call_args
    args = call_kwargs[0]
    kwargs = call_kwargs[1]
    filter_string = kwargs.get("filter_string", args[2] if len(args) > 2 else "")
    assert "FBaseQty <> 0" not in filter_string


@pytest.mark.asyncio
async def test_inventory_404_material_returns_empty_detail():
    client = make_client()
    # BD_MATERIAL returns nothing
    client.query = AsyncMock(return_value=[])
    reader = make_reader(client)
    detail = await reader.get_inventory_by_material("99.99.999")
    assert detail.material_code == "99.99.999"
    assert detail.rows == []
    assert detail.warehouse_count == 0
    assert detail.total_qty == Decimal(0)
    # Must NOT raise
    assert detail.material_name == ""


@pytest.mark.asyncio
async def test_inventory_sorts_rows_by_qty_desc():
    client = make_client()
    client.query = AsyncMock(return_value=[
        {"FNumber": "07.01.001", "FName": "潜水镜", "FSpecification": "", "FErpClsID": "9"},
    ])
    client.query_all = AsyncMock(return_value=[
        {"FMaterialId.FNumber": "07.01.001", "FStockId.FNumber": "WH01", "FStockId.FName": "A仓",
         "FAuxPropId": 0, "FLot.FNumber": "", "FBaseQty": "10", "FStockOrgId.FName": ""},
        {"FMaterialId.FNumber": "07.01.001", "FStockId.FNumber": "WH02", "FStockId.FName": "B仓",
         "FAuxPropId": 0, "FLot.FNumber": "", "FBaseQty": "50", "FStockOrgId.FName": ""},
        {"FMaterialId.FNumber": "07.01.001", "FStockId.FNumber": "WH03", "FStockId.FName": "C仓",
         "FAuxPropId": 0, "FLot.FNumber": "", "FBaseQty": "30", "FStockOrgId.FName": ""},
    ])
    reader = make_reader(client)
    detail = await reader.get_inventory_by_material("07.01.001")
    qtys = [row.base_qty for row in detail.rows]
    assert qtys == [Decimal("50"), Decimal("30"), Decimal("10")]


@pytest.mark.asyncio
async def test_inventory_aux_id_zero_no_lookup():
    client = make_client()
    client.query = AsyncMock(return_value=[
        {"FNumber": "07.01.001", "FName": "潜水镜", "FSpecification": "", "FErpClsID": "9"},
    ])
    client.query_all = AsyncMock(return_value=[
        {"FMaterialId.FNumber": "07.01.001", "FStockId.FNumber": "WH01", "FStockId.FName": "成品仓",
         "FAuxPropId": 0, "FLot.FNumber": "", "FBaseQty": "100", "FStockOrgId.FName": ""},
    ])
    reader = make_reader(client)
    await reader.get_inventory_by_material("07.01.001")
    # query called once for BD_MATERIAL; query_all called once for STK_Inventory.
    # BD_FLEXSITEMDETAILV must NOT be called because all aux_ids are 0.
    for call in client.query.call_args_list:
        form_id = call[1].get("form_id") or (call[0][0] if call[0] else "")
        assert form_id != "BD_FLEXSITEMDETAILV", (
            "BD_FLEXSITEMDETAILV should not be queried when all aux_ids are 0"
        )


@pytest.mark.asyncio
async def test_inventory_decimal_precision_preserved():
    client = make_client()
    client.query = AsyncMock(return_value=[
        {"FNumber": "07.01.001", "FName": "潜水镜", "FSpecification": "", "FErpClsID": "9"},
    ])
    client.query_all = AsyncMock(return_value=[
        {"FMaterialId.FNumber": "07.01.001", "FStockId.FNumber": "WH01", "FStockId.FName": "成品仓",
         "FAuxPropId": 0, "FLot.FNumber": "", "FBaseQty": "123.456", "FStockOrgId.FName": ""},
    ])
    reader = make_reader(client)
    detail = await reader.get_inventory_by_material("07.01.001")
    assert detail.rows[0].base_qty == Decimal("123.456")


# ---------------------------------------------------------------------------
# _resolve_aux_descriptions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aux_batches_by_200():
    client = make_client()
    client.query = AsyncMock(return_value=[])
    reader = make_reader(client)
    # 450 unique aux_ids
    aux_ids = set(range(1, 451))
    await reader._resolve_aux_descriptions(aux_ids)
    assert client.query.call_count == 3  # 200 + 200 + 50


@pytest.mark.asyncio
async def test_aux_prefers_ff100001_over_color():
    """When FF100001 (spec) is present, use it — do NOT concat with color."""
    client = make_client()
    client.query = AsyncMock(return_value=[
        {"FID": 1001, "FF100001": "GT38", "FF100002.FName": "黑色"},
    ])
    reader = make_reader(client)
    result = await reader._resolve_aux_descriptions({1001})
    assert result[1001] == "GT38"
    # Must NOT be "GT38 / 黑色" or "GT38黑色"
    assert "黑色" not in result[1001]


@pytest.mark.asyncio
async def test_aux_falls_back_to_color_when_spec_empty():
    client = make_client()
    client.query = AsyncMock(return_value=[
        {"FID": 1002, "FF100001": "", "FF100002.FName": "红色"},
    ])
    reader = make_reader(client)
    result = await reader._resolve_aux_descriptions({1002})
    assert result[1002] == "红色"


@pytest.mark.asyncio
async def test_aux_empty_set_returns_empty_dict():
    client = make_client()
    reader = make_reader(client)
    result = await reader._resolve_aux_descriptions(set())
    assert result == {}
    client.query.assert_not_called()
    client.query_all.assert_not_called()
