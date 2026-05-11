"""Tests for src/api/routers/photo.py"""

import base64
import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.routers.photo import router
from src.api.routers.auth import create_access_token


# A 1x1 transparent PNG — magic bytes + minimal IHDR/IDAT/IEND for MIME sniff.
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Valid 32-char hex FileID (matches Kingdee GUID format).
_VALID_FILE_ID = "8978cffd01404da595bdc8be907fbcce"


def _build_app(sdk_factory=None):
    """Create a minimal FastAPI app with the photo router mounted.

    sdk_factory: optional callable that returns a mock SDK object. When None,
    a default SDK that returns the tiny PNG in one chunk is wired up.
    """
    app = FastAPI()
    app.include_router(router)

    if sdk_factory is None:
        sdk_factory = _default_sdk

    mock_client = MagicMock()
    mock_client._get_sdk = AsyncMock(return_value=sdk_factory())

    mock_reader = MagicMock()
    mock_reader.client = mock_client

    app.state.readers = {"production_order": mock_reader}
    return app, mock_client


def _auth_header():
    token = create_access_token(data={"sub": "tester"})
    return {"Authorization": f"Bearer {token}"}


def _build_kingdee_response(file_part_bytes: bytes, is_last: bool = True, start_index: int = 0):
    """Format a Kingdee AttachmentDownLoad-shaped JSON string."""
    return json.dumps({
        "Result": {
            "ResponseStatus": {"IsSuccess": True, "MsgCode": 0, "Errors": []},
            "FilePart": base64.b64encode(file_part_bytes).decode("ascii"),
            "FileName": "test.png",
            "FileSize": len(file_part_bytes),
            "StartIndex": start_index + len(file_part_bytes) if not is_last else 4194304,
            "IsLast": is_last,
        }
    })


def _default_sdk():
    sdk = MagicMock()
    sdk.attachmentDownLoad = MagicMock(return_value=_build_kingdee_response(_TINY_PNG))
    return sdk


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestPhotoDownload:
    @pytest.mark.asyncio
    async def test_returns_decoded_bytes(self):
        app, _ = _build_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/photo/{_VALID_FILE_ID}", headers=_auth_header())

        assert resp.status_code == 200
        assert resp.content == _TINY_PNG

    @pytest.mark.asyncio
    async def test_sets_immutable_cache_and_png_content_type(self):
        app, _ = _build_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/photo/{_VALID_FILE_ID}", headers=_auth_header())

        assert resp.status_code == 200
        assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert resp.headers["content-type"] == "image/png"
        assert resp.headers["content-length"] == str(len(_TINY_PNG))


# ---------------------------------------------------------------------------
# Validation / auth
# ---------------------------------------------------------------------------

class TestPhotoValidation:
    @pytest.mark.asyncio
    async def test_malformed_file_id_returns_400(self):
        app, _ = _build_app()
        # 32 chars, but contains uppercase + non-hex chars — passes Path
        # length check, fails the regex.
        bad_id = "NOTAHEXGUID" + "X" * 21  # 32 chars total
        assert len(bad_id) == 32
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/photo/{bad_id}", headers=_auth_header())

        assert resp.status_code == 400
        assert "hex GUID" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_too_short_file_id_rejected_by_path_constraint(self):
        app, _ = _build_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/photo/not-a-guid", headers=_auth_header())

        # FastAPI Path(min_length=32) → 422; if a future change loosens that,
        # the regex 400 is also acceptable.
        assert resp.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_missing_auth_returns_401(self):
        app, _ = _build_app()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/photo/{_VALID_FILE_ID}")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Upstream errors
# ---------------------------------------------------------------------------

class TestPhotoUpstreamErrors:
    @pytest.mark.asyncio
    async def test_kingdee_failure_returns_404(self):
        def _sdk_factory():
            sdk = MagicMock()
            sdk.attachmentDownLoad = MagicMock(return_value=json.dumps({
                "Result": {
                    "ResponseStatus": {
                        "IsSuccess": False,
                        "Errors": [{"Message": "FileID not found"}],
                    }
                }
            }))
            return sdk

        app, _ = _build_app(sdk_factory=_sdk_factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/photo/{_VALID_FILE_ID}", headers=_auth_header())

        assert resp.status_code == 404
        assert "FileID not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_sdk_exception_returns_502(self):
        def _sdk_factory():
            sdk = MagicMock()
            sdk.attachmentDownLoad = MagicMock(side_effect=RuntimeError("connection refused"))
            return sdk

        app, _ = _build_app(sdk_factory=_sdk_factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/photo/{_VALID_FILE_ID}", headers=_auth_header())

        assert resp.status_code == 502
        assert resp.json()["detail"] == "upstream Kingdee error"


# ---------------------------------------------------------------------------
# Multi-chunk loop
# ---------------------------------------------------------------------------

class TestPhotoMultiChunk:
    @pytest.mark.asyncio
    async def test_concatenates_two_chunks(self):
        first_chunk = b"\x89PNG\r\n\x1a\n" + b"FIRST_HALF"
        second_chunk = b"SECOND_HALF"

        responses = [
            _build_kingdee_response(first_chunk, is_last=False, start_index=0),
            _build_kingdee_response(second_chunk, is_last=True, start_index=len(first_chunk)),
        ]

        def _sdk_factory():
            sdk = MagicMock()
            sdk.attachmentDownLoad = MagicMock(side_effect=responses)
            return sdk

        app, client_mock = _build_app(sdk_factory=_sdk_factory)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/api/photo/{_VALID_FILE_ID}", headers=_auth_header())

        assert resp.status_code == 200
        assert resp.content == first_chunk + second_chunk
        # PNG magic still detected at the front of the concatenated bytes.
        assert resp.headers["content-type"] == "image/png"
