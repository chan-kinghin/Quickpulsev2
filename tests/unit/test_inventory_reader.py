"""Unit tests for src/readers/inventory.py."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.kingdee.client import KingdeeClient
from src.readers.inventory import InventoryReader, sanitize_query, tokenize


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
async def test_search_dedupes_duplicate_material_codes():
    # Kingdee BD_MATERIAL returns one row per (material × org); we must collapse
    # to one row per material_code or the frontend x-for :key collides and renders nothing.
    client = make_client()
    client.query = AsyncMock(return_value=[
        {"FNumber": "06.04.080", "FName": "未包装呼吸管", "FSpecification": "SN9810", "FErpClsID": "9"},
        {"FNumber": "06.04.080", "FName": "未包装呼吸管", "FSpecification": "SN9810", "FErpClsID": "9"},
        {"FNumber": "06.04.080", "FName": "未包装呼吸管", "FSpecification": "SN9810", "FErpClsID": "9"},
        {"FNumber": "07.17.046", "FName": "潜水镜+呼吸管+蛙鞋", "FSpecification": "M5J+SN9810+F1J", "FErpClsID": "9"},
        {"FNumber": "07.17.046", "FName": "潜水镜+呼吸管+蛙鞋", "FSpecification": "M5J+SN9810+F1J", "FErpClsID": "9"},
    ])
    reader = make_reader(client)
    resp = await reader.search_materials("SN9810")
    codes = [i.material_code for i in resp.items]
    assert len(codes) == len(set(codes)), f"Duplicate codes in response: {codes}"
    assert resp.total == len(resp.items)
    assert resp.total == 2


def _find_call(client, form_id: str):
    """Return the kwargs of the client.query call for a given form_id, or None."""
    for call in client.query.call_args_list:
        kw = call.kwargs
        if kw.get("form_id") == form_id:
            return kw
    return None


@pytest.mark.asyncio
async def test_search_filter_includes_forbidden_clause():
    client = make_client()
    reader = make_reader(client)
    await reader.search_materials("GT38")
    kw = _find_call(client, "BD_MATERIAL")
    assert kw is not None, "BD_MATERIAL should be queried"
    assert "FForbidStatus = 'A'" in kw["filter_string"]


@pytest.mark.asyncio
async def test_search_filter_uses_or_across_three_fields():
    client = make_client()
    reader = make_reader(client)
    await reader.search_materials("GT38")
    kw = _find_call(client, "BD_MATERIAL")
    assert kw is not None
    filter_string = kw["filter_string"]
    assert "FNumber like" in filter_string
    assert "FName like" in filter_string
    assert "FSpecification like" in filter_string
    assert " or " in filter_string.lower()


@pytest.mark.asyncio
async def test_search_caps_at_fifty_even_if_limit_higher():
    # The candidate fetch uses a broad limit (500) so intersection doesn't truncate early.
    # The cap of 50 is enforced when slicing the final intersection result, not at query time.
    # This test verifies the response never returns more than 50 items.
    client = make_client()
    all_mat_rows = [
        {"FNumber": f"07.01.{i:03d}", "FName": f"物料{i}", "FSpecification": "", "FErpClsID": "9"}
        for i in range(60)
    ]

    async def fake_query(*, form_id, filter_string="", limit=2000, **kw):
        if form_id == "BD_MATERIAL":
            if "FNumber IN" in filter_string:
                # metadata fetch: only return rows whose code is requested
                requested = {c.strip("'") for c in filter_string.split("IN (")[1].split(")")[0].split(",")}
                return [r for r in all_mat_rows if r["FNumber"] in requested]
            return [{"FNumber": r["FNumber"]} for r in all_mat_rows]  # candidate fetch (code only)
        return []  # BD_FLEXSITEMDETAILV, STK_Inventory

    client.query = AsyncMock(side_effect=fake_query)
    reader = make_reader(client)
    resp = await reader.search_materials("GT38", limit=200)
    assert resp.total <= 50
    assert len(resp.items) <= 50


@pytest.mark.asyncio
async def test_search_aux_path_queries_flexsitem():
    # Demo feature: aux discovery — search should also query BD_FLEXSITEMDETAILV in parallel.
    client = make_client()
    reader = make_reader(client)
    await reader.search_materials("黑色")
    kw = _find_call(client, "BD_FLEXSITEMDETAILV")
    assert kw is not None, "BD_FLEXSITEMDETAILV should be queried for aux discovery"
    assert "FF100001 like" in kw["filter_string"]
    assert "FF100002.FName like" in kw["filter_string"]


@pytest.mark.asyncio
async def test_search_aux_discovers_extra_materials():
    # When BD_MATERIAL returns 0 hits but aux returns matching colors,
    # reverse-lookup via STK_Inventory should find materials.
    client = make_client()

    async def fake_query(*, form_id, **kw):
        if form_id == "BD_MATERIAL":
            # First call (initial search) returns nothing — no name/code/spec match for "黑色"
            # Second call (extras fetch) returns the discovered material
            if "FNumber IN" in kw.get("filter_string", ""):
                return [{"FNumber": "05.02.01.35", "FName": "鼻梁", "FSpecification": "NBLT-GT38", "FErpClsID": "2"}]
            return []
        if form_id == "BD_FLEXSITEMDETAILV":
            return [{"FID": 105814, "FF100001": "B", "FF100002.FName": "黑色"}]
        if form_id == "STK_Inventory":
            return [{"FMaterialId.FNumber": "05.02.01.35"}]
        return []

    client.query = AsyncMock(side_effect=fake_query)
    reader = make_reader(client)
    resp = await reader.search_materials("黑色")

    assert resp.total == 1
    assert resp.items[0].material_code == "05.02.01.35"
    assert resp.items[0].material_name == "鼻梁"


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


# ---------------------------------------------------------------------------
# tokenize
# ---------------------------------------------------------------------------

def test_tokenize_splits_ascii_space():
    assert tokenize("K66 盒子") == ["K66", "盒子"]


def test_tokenize_splits_cjk_space():
    # CJK fullwidth space U+3000
    assert tokenize("K66　盒子") == ["K66", "盒子"]


def test_tokenize_single_token_no_split():
    assert tokenize("黑色网袋") == ["黑色网袋"]


def test_tokenize_caps_at_four():
    with pytest.raises(ValueError, match="Too many search tokens"):
        tokenize("a b c d e")


# ---------------------------------------------------------------------------
# multi-token intersection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multi_token_intersection():
    """Two tokens; final result is the intersection of their candidate sets."""
    client = make_client()

    # token "网袋": BD_MATERIAL returns codes A and B; aux returns nothing
    # token "黑色": BD_MATERIAL returns nothing; aux → STK_Inventory returns codes B and C
    async def fake_query(*, form_id, filter_string="", **kw):
        if form_id == "BD_MATERIAL":
            if "网袋" in filter_string and "FNumber IN" not in filter_string:
                return [{"FNumber": "A"}, {"FNumber": "B"}]
            if "黑色" in filter_string and "FNumber IN" not in filter_string:
                return []
            # metadata fetch for final set (intersection = {"B"})
            if "FNumber IN" in filter_string:
                return [{"FNumber": "B", "FName": "黑色网袋", "FSpecification": "", "FErpClsID": "1"}]
            return []
        if form_id == "BD_FLEXSITEMDETAILV":
            if "黑色" in filter_string:
                return [{"FID": 999, "FF100001": "", "FF100002.FName": "黑色"}]
            return []
        if form_id == "STK_Inventory":
            return [{"FMaterialId.FNumber": "B"}, {"FMaterialId.FNumber": "C"}]
        return []

    client.query = AsyncMock(side_effect=fake_query)
    reader = make_reader(client)
    resp = await reader.search_materials("网袋 黑色")

    codes = [i.material_code for i in resp.items]
    assert codes == ["B"], f"Expected intersection {{B}}, got {codes}"
    assert resp.total == 1


@pytest.mark.asyncio
async def test_erp_class_filter_in_kingdee_filter():
    """erp_classes=["1","9"] must produce FErpClsID IN ('1','9') in BD_MATERIAL filter."""
    client = make_client()
    reader = make_reader(client)
    await reader.search_materials("GT38", erp_classes=["1", "9"])
    bd_calls = [
        call.kwargs
        for call in client.query.call_args_list
        if call.kwargs.get("form_id") == "BD_MATERIAL"
        and "FNumber IN" not in call.kwargs.get("filter_string", "")
    ]
    assert bd_calls, "BD_MATERIAL should have been queried"
    assert any("FErpClsID IN ('1','9')" in c["filter_string"] for c in bd_calls)


@pytest.mark.asyncio
async def test_erp_class_invalid_raises():
    client = make_client()
    reader = make_reader(client)
    with pytest.raises(ValueError, match="Invalid erp_class values"):
        await reader.search_materials("GT38", erp_classes=["7"])


@pytest.mark.asyncio
async def test_multi_token_empty_intersection():
    """When token candidate sets are disjoint, response is total=0 with empty items."""
    client = make_client()

    async def fake_query(*, form_id, filter_string="", **kw):
        if form_id == "BD_MATERIAL" and "FNumber IN" not in filter_string:
            if "网袋" in filter_string:
                return [{"FNumber": "MAT_NET"}]
            if "蛙鞋" in filter_string:
                return [{"FNumber": "MAT_FIN"}]
            return []
        # aux and STK_Inventory return nothing
        return []

    client.query = AsyncMock(side_effect=fake_query)
    reader = make_reader(client)
    resp = await reader.search_materials("网袋 蛙鞋")
    # intersection of {"MAT_NET"} and {"MAT_FIN"} is empty
    assert resp.total == 0
    assert resp.items == []


# ---------------------------------------------------------------------------
# Customer lookup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_customer_lookup_returns_material_codes():
    """_customer_lookup runs a SQL LIKE on cached_sales_orders.customer_name."""
    db = AsyncMock()
    db.execute_read = AsyncMock(return_value=[("07.01.001",), ("07.01.002",)])
    reader = InventoryReader(make_client(), db=db)
    codes = await reader._customer_lookup("巴西")
    assert codes == {"07.01.001", "07.01.002"}
    sql, params = db.execute_read.call_args[0]
    assert "cached_sales_orders" in sql
    assert "customer_name LIKE" in sql
    assert params == ["%巴西%"]


@pytest.mark.asyncio
async def test_customer_lookup_sql_runs_against_real_sqlite():
    """Regression: ESCAPE clause must be a single character.

    The first v3 deploy shipped with ESCAPE '\\\\' (Python source) which SQLite
    rejects with 'ESCAPE expression must be a single character'. AsyncMock
    tests didn't catch this because they never parsed the SQL — only an actual
    sqlite engine does. This test forces the SQL through a real in-memory DB.
    """
    import aiosqlite

    class RealDb:
        def __init__(self, conn):
            self.conn = conn

        async def execute_read(self, query, params=None):
            async with self.conn.execute(query, params or []) as cur:
                return await cur.fetchall()

    async with aiosqlite.connect(":memory:") as conn:
        await conn.execute(
            "CREATE TABLE cached_sales_orders ("
            "  bill_no TEXT, material_code TEXT, customer_name TEXT)"
        )
        await conn.executemany(
            "INSERT INTO cached_sales_orders VALUES (?, ?, ?)",
            [
                ("S1", "07.01.001", "巴西KS"),
                ("S2", "07.01.002", "巴西MULTISPORT"),
                ("S3", "07.99.099", "美国Acme"),
            ],
        )
        await conn.commit()

        reader = InventoryReader(make_client(), db=RealDb(conn))
        codes = await reader._customer_lookup("巴西")
        assert codes == {"07.01.001", "07.01.002"}

        # Wildcards in user input must be matched literally, not as wildcards
        codes_pct = await reader._customer_lookup("巴%")
        assert codes_pct == set(), "% in input must be escaped to literal"


@pytest.mark.asyncio
async def test_customer_lookup_disabled_when_no_db():
    """When db is None, _customer_lookup returns empty set without querying."""
    reader = InventoryReader(make_client(), db=None)
    assert await reader._customer_lookup("巴西") == set()


@pytest.mark.asyncio
async def test_customer_lookup_escapes_sql_wildcards():
    """User input '%' and '_' must be escaped to be matched literally."""
    db = AsyncMock()
    db.execute_read = AsyncMock(return_value=[])
    reader = InventoryReader(make_client(), db=db)
    await reader._customer_lookup("test%user")
    params = db.execute_read.call_args[0][1]
    # Wildcard inside the user term should be escaped
    assert "test\\%user" in params[0]


@pytest.mark.asyncio
async def test_matched_via_includes_customer_when_path_contributes():
    """When customer lookup is the only source, matched_via should be ['customer']."""
    db = AsyncMock()
    db.execute_read = AsyncMock(return_value=[("07.99.001",)])

    async def fake_query(*, form_id, filter_string="", **kw):
        if form_id == "BD_MATERIAL":
            if "FNumber IN" in filter_string:
                # metadata fetch
                return [{"FNumber": "07.99.001", "FName": "测试", "FSpecification": "", "FErpClsID": "9"}]
            return []  # candidate fetch — empty
        return []

    client = make_client()
    client.query = AsyncMock(side_effect=fake_query)
    reader = InventoryReader(client, db=db)
    resp = await reader.search_materials("巴西")
    assert resp.total == 1
    assert resp.items[0].matched_via == ["customer"]


@pytest.mark.asyncio
async def test_matched_via_combines_sources():
    """Material matching via both name AND customer should have both labels."""
    db = AsyncMock()
    db.execute_read = AsyncMock(return_value=[("07.99.001",)])

    async def fake_query(*, form_id, filter_string="", **kw):
        if form_id == "BD_MATERIAL":
            if "FNumber IN" in filter_string:
                return [{"FNumber": "07.99.001", "FName": "MARES vest", "FSpecification": "", "FErpClsID": "9"}]
            return [{"FNumber": "07.99.001"}]  # candidate fetch hits
        return []

    client = make_client()
    client.query = AsyncMock(side_effect=fake_query)
    reader = InventoryReader(client, db=db)
    resp = await reader.search_materials("MARES")
    assert set(resp.items[0].matched_via) == {"name", "customer"}


# ---------------------------------------------------------------------------
# Typo retry (_insert_dash_variant + search_materials retry path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_typo_retry_inserts_dash():
    """When zero hits, retry with dash-injected variant: K66 → K-66."""
    db = AsyncMock()
    db.execute_read = AsyncMock(return_value=[])

    call_log = []

    async def fake_query(*, form_id, filter_string="", **kw):
        call_log.append((form_id, filter_string))
        if form_id == "BD_MATERIAL":
            if "FNumber IN" in filter_string:
                return [{"FNumber": "05.05.17.02", "FName": "盒子", "FSpecification": "K-66盒子", "FErpClsID": "1"}]
            # candidate fetch: only "K-66" variant returns hits, "K66" returns empty
            if "%K-66%" in filter_string:
                return [{"FNumber": "05.05.17.02"}]
            return []
        return []

    client = make_client()
    client.query = AsyncMock(side_effect=fake_query)
    reader = InventoryReader(client, db=db)
    resp = await reader.search_materials("K66")

    assert resp.total == 1
    # Verify the variant query was made
    assert any("%K-66%" in fs for _, fs in call_log), f"K-66 variant not attempted: {call_log}"


@pytest.mark.asyncio
async def test_typo_retry_skipped_when_no_letter_digit_boundary():
    """Tokens like '盒子' or 'K-66' should not trigger dash injection."""
    db = AsyncMock()
    db.execute_read = AsyncMock(return_value=[])

    call_log = []

    async def fake_query(*, form_id, filter_string="", **kw):
        call_log.append(filter_string)
        return []

    client = make_client()
    client.query = AsyncMock(side_effect=fake_query)
    reader = InventoryReader(client, db=db)
    await reader.search_materials("盒子")

    # No filter_string should contain a dash injected into "盒子"
    assert not any("-子" in fs or "盒-" in fs for fs in call_log)


@pytest.mark.asyncio
async def test_typo_retry_not_fired_when_first_pass_has_hits():
    """Retry must NOT run when first pass already yields results."""
    db = AsyncMock()
    db.execute_read = AsyncMock(return_value=[])

    call_log = []

    async def fake_query(*, form_id, filter_string="", **kw):
        call_log.append((form_id, filter_string))
        if form_id == "BD_MATERIAL":
            if "FNumber IN" in filter_string:
                return [{"FNumber": "05.05.001", "FName": "盒子", "FSpecification": "K66标准", "FErpClsID": "1"}]
            # K66 candidate fetch hits on first pass
            if "%K66%" in filter_string:
                return [{"FNumber": "05.05.001"}]
            return []
        return []

    client = make_client()
    client.query = AsyncMock(side_effect=fake_query)
    reader = InventoryReader(client, db=db)
    resp = await reader.search_materials("K66")

    assert resp.total == 1
    # K-66 variant should NOT have been queried since first pass had hits
    assert not any("%K-66%" in fs for _, fs in call_log), (
        "Retry should not fire when first pass has results"
    )
