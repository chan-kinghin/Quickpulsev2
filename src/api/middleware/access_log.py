"""Access logging middleware — records every non-static request to SQLite."""

import asyncio
import logging
import time
from typing import Optional

from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


def _get_client_ip(request: Request) -> str:
    """Extract client IP from X-Forwarded-For header or request.client."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First entry is the real client IP
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


async def _write_log(
    db,
    ip_address: str,
    method: str,
    path: str,
    status_code: int,
    response_time_ms: float,
    user_agent: Optional[str],
) -> None:
    """Insert a single access log row. Silently swallows errors."""
    try:
        await db.execute_write(
            """
            INSERT INTO access_logs (ip_address, method, path, status_code, response_time_ms, user_agent)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [ip_address, method, path, status_code, round(response_time_ms, 2), user_agent],
        )
    except Exception:
        logger.debug("Failed to write access log", exc_info=True)


def setup_access_logging(app) -> None:
    """Register the access-logging middleware on *app*."""

    @app.middleware("http")
    async def access_log_middleware(request: Request, call_next) -> Response:
        # Skip static assets — they would flood the table
        if request.url.path.startswith("/static/"):
            return await call_next(request)

        start = time.time()
        response = await call_next(request)
        elapsed_ms = (time.time() - start) * 1000

        # Fire-and-forget: log in background so the response is never delayed
        db = getattr(request.app.state, "db", None)
        if db is not None:
            try:
                asyncio.create_task(
                    _write_log(
                        db,
                        ip_address=_get_client_ip(request),
                        method=request.method,
                        path=request.url.path,
                        status_code=response.status_code,
                        response_time_ms=elapsed_ms,
                        user_agent=request.headers.get("user-agent"),
                    )
                )
            except Exception:
                # create_task can fail if the event loop is shutting down
                pass

        return response
