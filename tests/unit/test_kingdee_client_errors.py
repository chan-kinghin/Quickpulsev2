"""Unit tests for KingdeeClient.query error handling.

Guards bug-patterns Pattern 12: a missing/invalid Kingdee field key ("字段不存在")
must FAIL LOUD (raise KingdeeQueryError), not be swallowed into [] — otherwise sync
records status="success" while writing zero rows, freezing a cache table silently.

A missing/disabled FORM ("业务对象不存在" / MsgCode 4) is a different, recoverable
case: returning [] is acceptable there.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.exceptions import KingdeeQueryError
from src.kingdee.client import KingdeeClient


def _client_returning(sdk_response):
    """Build a KingdeeClient whose SDK returns the given raw response."""
    client = KingdeeClient(MagicMock())
    fake_sdk = MagicMock()
    fake_sdk.ExecuteBillQuery.return_value = sdk_response
    client._get_sdk = AsyncMock(return_value=fake_sdk)
    return client


def _double_wrapped_error(message: str, msg_code: int = 1):
    """Kingdee's common double-list-wrapped error envelope."""
    return [
        [
            {
                "Result": {
                    "ResponseStatus": {
                        "IsSuccess": False,
                        "Errors": [{"Message": message}],
                    },
                    "MsgCode": msg_code,
                }
            }
        ]
    ]


@pytest.mark.asyncio
async def test_invalid_field_key_raises_not_swallowed():
    """'字段不存在' is a config bug → must raise, never return []."""
    client = _client_returning(_double_wrapped_error("FBogusField 字段不存在"))

    with pytest.raises(KingdeeQueryError) as exc:
        await client.query("PRD_MO", ["FBogusField"])

    assert "PRD_MO" in str(exc.value)


@pytest.mark.asyncio
async def test_missing_form_returns_empty():
    """'业务对象不存在' (absent/disabled form) is recoverable → return []."""
    client = _client_returning(_double_wrapped_error("业务对象不存在"))

    result = await client.query("SOME_OPTIONAL_FORM", ["FId"])

    assert result == []


@pytest.mark.asyncio
async def test_msgcode_4_returns_empty():
    """MsgCode 4 (form not found) → return []."""
    client = _client_returning(_double_wrapped_error("form not found", msg_code=4))

    result = await client.query("SOME_FORM", ["FId"])

    assert result == []
