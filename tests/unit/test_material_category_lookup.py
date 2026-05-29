"""Unit tests for KingdeeClient.lookup_material_categories.

Backs the routing fix: synthetic / PUR-only rows (not in PPBOM) get their authoritative
BD_MATERIAL.CategoryID so they route via _CATEGORY_TO_TYPE instead of the legacy
material_type fallback. Also guards the injection whitelist on FNumber.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.kingdee.client import KingdeeClient


def _client(query_all_return):
    c = KingdeeClient(MagicMock())
    c.query_all = AsyncMock(return_value=query_all_return)
    return c


@pytest.mark.asyncio
async def test_parses_category_by_code():
    c = _client([
        {"FNumber": "03.06.03.001", "FCategoryID.FName": "外销包材"},
        {"FNumber": "08.12.02.18", "FCategoryID.FName": "委外加工"},
    ])
    out = await c.lookup_material_categories(["03.06.03.001", "08.12.02.18"])
    assert out == {"03.06.03.001": "外销包材", "08.12.02.18": "委外加工"}


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
async def test_blank_category_skipped():
    c = _client([
        {"FNumber": "03.06.03.001", "FCategoryID.FName": "外销包材"},
        {"FNumber": "05.02.001", "FCategoryID.FName": "   "},
        {"FNumber": "05.02.002", "FCategoryID.FName": None},
    ])
    out = await c.lookup_material_categories(["03.06.03.001", "05.02.001", "05.02.002"])
    assert out == {"03.06.03.001": "外销包材"}
