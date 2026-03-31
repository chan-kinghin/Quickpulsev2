"""Admin API endpoints for usage analytics."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Query, Request

from src.api.middleware.rate_limit import limiter
from src.api.routers.auth import get_current_user
from src.utils.geoip import lookup_ip_display

_geoip_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="geoip")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/usage/summary")
@limiter.limit("30/minute")
async def usage_summary(
    request: Request,
    hours: int = Query(default=24, ge=1, le=720),
    current_user: str = Depends(get_current_user),
):
    db = request.app.state.db
    time_param = f"-{hours} hours"

    rows = await db.execute_read(
        """
        WITH filtered AS (
            SELECT ip_address, path, response_time_ms
            FROM access_logs
            WHERE timestamp >= datetime('now', ?, 'localtime')
        ),
        top_ep AS (
            SELECT path, COUNT(*) AS cnt
            FROM filtered
            GROUP BY path
            ORDER BY cnt DESC
            LIMIT 1
        ),
        top_ip AS (
            SELECT ip_address, COUNT(*) AS cnt
            FROM filtered
            GROUP BY ip_address
            ORDER BY cnt DESC
            LIMIT 1
        )
        SELECT
            (SELECT COUNT(*) FROM filtered) AS total_requests,
            (SELECT COUNT(DISTINCT ip_address) FROM filtered) AS unique_ips,
            (SELECT AVG(response_time_ms) FROM filtered) AS avg_response_time_ms,
            (SELECT path FROM top_ep) AS top_endpoint,
            (SELECT ip_address FROM top_ip) AS top_ip
        """,
        [time_param],
    )

    row = rows[0] if rows else None
    total_requests = row[0] if row else 0
    unique_ips = row[1] if row else 0
    avg_response_time_ms = round(row[2], 2) if row and row[2] is not None else 0.0
    top_endpoint = row[3] if row else None
    top_location = (
        lookup_ip_display(row[4]) if row and row[4] else "未知"
    )

    return {
        "total_requests": total_requests,
        "unique_ips": unique_ips,
        "avg_response_time_ms": avg_response_time_ms,
        "top_endpoint": top_endpoint,
        "top_location": top_location,
        "period_hours": hours,
    }


@router.get("/usage/by-ip")
@limiter.limit("30/minute")
async def usage_by_ip(
    request: Request,
    hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=50, ge=1, le=500),
    current_user: str = Depends(get_current_user),
):
    db = request.app.state.db
    time_param = f"-{hours} hours"

    rows = await db.execute_read(
        """
        WITH per_ip_path AS (
            SELECT ip_address, path, COUNT(*) AS cnt,
                   MAX(timestamp) AS max_ts
            FROM access_logs
            WHERE timestamp >= datetime('now', ?, 'localtime')
            GROUP BY ip_address, path
        ),
        ranked AS (
            SELECT ip_address, path, cnt, max_ts,
                   ROW_NUMBER() OVER (
                       PARTITION BY ip_address ORDER BY cnt DESC
                   ) AS rn
            FROM per_ip_path
        )
        SELECT
            ip_address,
            SUM(cnt) AS request_count,
            MAX(max_ts) AS last_seen,
            MIN(CASE WHEN rn = 1 THEN path END) AS top_endpoint
        FROM ranked
        GROUP BY ip_address
        ORDER BY request_count DESC
        LIMIT ?
        """,
        [time_param, limit],
    )

    loop = asyncio.get_running_loop()
    locations = await asyncio.gather(*(
        loop.run_in_executor(_geoip_executor, lookup_ip_display, row[0])
        for row in rows
    ))

    return [
        {
            "ip_address": row[0],
            "request_count": row[1],
            "last_seen": row[2],
            "top_endpoint": row[3],
            "location": loc,
        }
        for row, loc in zip(rows, locations)
    ]


@router.get("/usage/timeline")
@limiter.limit("30/minute")
async def usage_timeline(
    request: Request,
    hours: int = Query(default=24, ge=1, le=720),
    bucket: str = Query(default="hour", regex="^(hour|day)$"),
    current_user: str = Depends(get_current_user),
):
    db = request.app.state.db
    time_param = f"-{hours} hours"

    if bucket == "hour":
        bucket_expr = "strftime('%Y-%m-%d %H:00', timestamp)"
    else:
        bucket_expr = "strftime('%Y-%m-%d', timestamp)"

    rows = await db.execute_read(
        f"""
        SELECT
            {bucket_expr} AS bucket_start,
            COUNT(*) AS request_count
        FROM access_logs
        WHERE timestamp >= datetime('now', ?, 'localtime')
        GROUP BY bucket_start
        ORDER BY bucket_start ASC
        """,
        [time_param],
    )

    return [
        {"bucket_start": row[0], "request_count": row[1]}
        for row in rows
    ]


@router.get("/usage/recent")
@limiter.limit("30/minute")
async def usage_recent(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: str = Depends(get_current_user),
):
    db = request.app.state.db

    # Get total count
    count_rows = await db.execute_read(
        "SELECT COUNT(*) FROM access_logs"
    )
    total = count_rows[0][0] if count_rows else 0

    # Get paginated items
    rows = await db.execute_read(
        """
        SELECT timestamp, ip_address, method, path, status_code, response_time_ms
        FROM access_logs
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
        """,
        [limit, offset],
    )

    items = [
        {
            "timestamp": row[0],
            "ip_address": row[1],
            "method": row[2],
            "path": row[3],
            "status_code": row[4],
            "response_time_ms": row[5],
            "location": lookup_ip_display(row[1]),
        }
        for row in rows
    ]

    return {"items": items, "total": total}
