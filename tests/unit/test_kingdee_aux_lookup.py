"""Stage 7 of PLAN_aux_match_visibility — verify BD_FLEXSITEMDETAILV
lookup logs a WARNING on failure or sparse response, and returns {} so
callers continue working.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.kingdee.client import KingdeeClient


@pytest.fixture
def client():
    """KingdeeClient with mocked SDK — never touches the network."""
    cfg = MagicMock()
    c = KingdeeClient(cfg)
    return c


@pytest.mark.asyncio
async def test_empty_input_returns_empty_dict_silently(client, caplog):
    with caplog.at_level("WARNING", logger="src.kingdee.client"):
        result = await client.lookup_aux_properties([])
    assert result == {}
    assert not any("aux_lookup" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_exception_logs_warning_and_returns_empty(client, caplog):
    """When the underlying query raises, callers should get {} so the broader
    MTO query keeps working — but a WARNING is emitted so Loki can surface it.
    """
    client.query_all = AsyncMock(side_effect=RuntimeError("Kingdee session expired"))

    with caplog.at_level("WARNING", logger="src.kingdee.client"):
        result = await client.lookup_aux_properties([1001, 1002, 1003])

    assert result == {}
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("aux_lookup_failed" in r.message for r in warnings), (
        f"expected aux_lookup_failed warning, got: {[r.message for r in warnings]}"
    )


@pytest.mark.asyncio
async def test_sparse_response_logs_warning(client, caplog):
    """When >50% of requested IDs return no description, escalate to WARNING.

    This is the "data quality" signal: the lookup didn't fail, but the result
    is too sparse to be useful — likely indicates a Kingdee schema drift or
    a malformed FAuxPropId reference upstream.
    """
    # Request 4, get descriptions for only 1 (75% missing > 50%).
    client.query_all = AsyncMock(return_value=[
        {"FID": 1001, "FF100001": "Blue Large", "FF100002.FName": ""},
    ])

    with caplog.at_level("INFO", logger="src.kingdee.client"):
        result = await client.lookup_aux_properties([1001, 1002, 1003, 1004])

    assert result == {1001: "Blue Large"}
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("aux_lookup_sparse" in r.message for r in warnings), (
        f"expected aux_lookup_sparse warning, got: {[r.message for r in warnings]}"
    )


@pytest.mark.asyncio
async def test_full_response_does_not_warn(client, caplog):
    """Healthy case: all IDs resolved → INFO log only, no WARNING."""
    client.query_all = AsyncMock(return_value=[
        {"FID": 1001, "FF100001": "Blue", "FF100002.FName": ""},
        {"FID": 1002, "FF100001": "Red", "FF100002.FName": ""},
    ])

    with caplog.at_level("INFO", logger="src.kingdee.client"):
        result = await client.lookup_aux_properties([1001, 1002])

    assert result == {1001: "Blue", 1002: "Red"}
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert not any("aux_lookup" in r.message for r in warnings)
