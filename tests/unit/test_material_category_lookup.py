"""Unit tests for KingdeeClient.lookup_material_categories.

Backs the routing fix: synthetic / PUR-only rows (not in PPBOM) get their authoritative
BD_MATERIAL.CategoryID so they route via _CATEGORY_TO_TYPE instead of the legacy
material_type fallback. Also guards the injection whitelist on FNumber.

Return shape updated 2026-06-10 (live is_purchase fix): the lookup now also fetches
FIsPurchase and returns {code: (category_name, is_purchase)} so the live path can
populate BOMJoinedRow.is_purchase instead of leaving the dataclass default (False)
to misfire the self-made-packaging branch (AS2603021).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.kingdee.client import KingdeeClient


def _client(query_all_return):
    c = KingdeeClient(MagicMock())
    c.query_all = AsyncMock(return_value=query_all_return)
    return c


@pytest.mark.asyncio
async def test_parses_category_and_is_purchase_by_code():
    c = _client([
        {"FNumber": "03.06.03.001", "FCategoryID.FName": "外销包材", "FIsPurchase": True},
        {"FNumber": "08.12.02.18", "FCategoryID.FName": "委外加工", "FIsPurchase": False},
    ])
    out = await c.lookup_material_categories(["03.06.03.001", "08.12.02.18"])
    assert out == {
        "03.06.03.001": ("外销包材", True),
        "08.12.02.18": ("委外加工", False),
    }


@pytest.mark.asyncio
async def test_field_keys_include_is_purchase():
    c = _client([])
    await c.lookup_material_categories(["03.06.03.001"])
    _, kwargs = c.query_all.call_args
    assert kwargs["field_keys"] == ["FNumber", "FCategoryID.FName", "FIsPurchase"]


@pytest.mark.asyncio
async def test_empty_input_no_query():
    c = _client([])
    assert await c.lookup_material_categories([]) == {}
    c.query_all.assert_not_called()


@pytest.mark.asyncio
async def test_injection_codes_filtered_out():
    """Codes with quotes/parens/etc never reach the FilterString."""
    c = _client([])
    await c.lookup_material_categories(["03.06.03.001", "x'; DROP--", "a) OR (1=1"])
    # query_all is called, but only the safe code is in the IN clause
    _, kwargs = c.query_all.call_args
    fs = kwargs["filter_string"]
    assert "03.06.03.001" in fs
    assert "DROP" not in fs and "OR (1=1" not in fs


@pytest.mark.asyncio
async def test_blank_category_kept_with_empty_string():
    """Blank category no longer drops the code — is_purchase must still flow
    through (the caller filters categories itself; is_purchase is unfiltered)."""
    c = _client([
        {"FNumber": "03.06.03.001", "FCategoryID.FName": "外销包材", "FIsPurchase": True},
        {"FNumber": "05.02.001", "FCategoryID.FName": "   ", "FIsPurchase": True},
        {"FNumber": "05.02.002", "FCategoryID.FName": None, "FIsPurchase": False},
    ])
    out = await c.lookup_material_categories(["03.06.03.001", "05.02.001", "05.02.002"])
    assert out == {
        "03.06.03.001": ("外销包材", True),
        "05.02.001": ("", True),
        "05.02.002": ("", False),
    }


@pytest.mark.asyncio
async def test_multi_org_duplicates_merge_first_nonempty_cat_any_true_purchase():
    """Multi-org BD_MATERIAL duplicates: first non-empty category wins,
    is_purchase is any-true across rows."""
    c = _client([
        {"FNumber": "03.01.012", "FCategoryID.FName": "", "FIsPurchase": False},
        {"FNumber": "03.01.012", "FCategoryID.FName": "主料", "FIsPurchase": True},
        {"FNumber": "03.01.012", "FCategoryID.FName": "辅料", "FIsPurchase": False},
    ])
    out = await c.lookup_material_categories(["03.01.012"])
    assert out == {"03.01.012": ("主料", True)}
