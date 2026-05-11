"""Photo download endpoint — wraps Kingdee's AttachmentDownLoad service.

Streams the binary content of a Kingdee BOS attachment back to the browser
with an immutable cache header. FileIDs are content-addressed GUIDs that
never get re-issued, so we can cache for one year safely.
"""

import asyncio
import base64
import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import Response

from src.api.routers.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/photo", tags=["photo"])

# Kingdee FileIDs are 32-char hex GUIDs (no dashes). Validate before passing
# arbitrary user input to the upstream SDK.
_FILE_ID_RE = re.compile(r"^[a-f0-9]{32}$")

# Cache for one year; FileIDs are content-addressed.
_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"


def _detect_mime(data: bytes) -> str:
    """Sniff the image MIME from magic bytes; fall back to octet-stream."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return "application/octet-stream"


def _parse_response(raw) -> dict:
    """Coerce the SDK return value into a dict and unwrap the Result envelope.

    The SDK may return a JSON string, a dict, or (rarely) a list-wrapped
    response — normalize all three.
    """
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if not isinstance(raw, dict):
        raise ValueError(f"unexpected SDK response type: {type(raw).__name__}")
    return raw.get("Result", raw)


async def _download_all_chunks(sdk, file_id: str) -> bytes:
    """Loop AttachmentDownLoad until IsLast=true, accumulating decoded bytes.

    Single-chunk files (<= ~4 MB) come back in one call; larger files require
    successive calls with the StartIndex returned by the previous response.
    """
    loop = asyncio.get_running_loop()
    parts: list[bytes] = []
    start_index = 0

    while True:
        params = {"FileID": file_id, "StartIndex": start_index}
        raw = await loop.run_in_executor(None, lambda p=params: sdk.attachmentDownLoad(p))
        result = _parse_response(raw)

        status = result.get("ResponseStatus") or {}
        if status and not status.get("IsSuccess", True):
            errors = status.get("Errors") or []
            msg = errors[0].get("Message", "unknown") if errors else "unknown"
            raise HTTPException(status_code=404, detail=f"Kingdee attachment error: {msg}")

        file_part = result.get("FilePart")
        if file_part is None:
            raise HTTPException(status_code=404, detail="Kingdee returned no file content")

        parts.append(base64.b64decode(file_part))

        if result.get("IsLast", True):
            break

        next_start = result.get("StartIndex")
        if next_start is None or next_start <= start_index:
            # Defensive: avoid an infinite loop if the server stops advancing.
            logger.warning(
                "AttachmentDownLoad did not advance StartIndex (%s -> %s) for %s",
                start_index, next_start, file_id,
            )
            break
        start_index = next_start

    return b"".join(parts)


@router.get("/{file_id}")
async def get_photo(
    request: Request,
    file_id: str = Path(..., min_length=32, max_length=32),
    current_user: str = Depends(get_current_user),
):
    """Stream a Kingdee attachment's bytes with a 1-year immutable cache."""
    if not _FILE_ID_RE.match(file_id):
        raise HTTPException(status_code=400, detail="FileID must be a 32-char hex GUID")

    # KingdeeClient isn't exposed on app.state directly; reach it via any reader
    # (they all share the same client instance constructed in lifespan()).
    try:
        kingdee_client = request.app.state.readers["production_order"].client
    except (AttributeError, KeyError) as exc:
        logger.exception("Kingdee client not available for photo download")
        raise HTTPException(status_code=502, detail="upstream Kingdee error") from exc

    try:
        sdk = await kingdee_client._get_sdk()
        data = await _download_all_chunks(sdk, file_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("AttachmentDownLoad failed for FileID=%s", file_id)
        raise HTTPException(status_code=502, detail="upstream Kingdee error") from exc

    content_type = _detect_mime(data)
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": _IMMUTABLE_CACHE,
            "Content-Length": str(len(data)),
        },
    )
