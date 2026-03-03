"""Admin API endpoints for usage analytics."""

import logging

from fastapi import APIRouter, Depends, Query, Request

from src.api.middleware.rate_limit import limiter
from src.api.routers.auth import get_current_user

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
        SELECT
            COUNT(*) AS total_requests,
            COUNT(DISTINCT ip_address) AS unique_ips,
            AVG(response_time_ms) AS avg_response_time_ms
        FROM access_logs
        WHERE timestamp >= datetime('now', ?, 'localtime')
        """,
        [time_param],
    )

    row = rows[0] if rows else None
    total_requests = row[0] if row else 0
    unique_ips = row[1] if row else 0
    avg_response_time_ms = round(row[2], 2) if row and row[2] is not None else 0.0

    # Find top endpoint
    top_rows = await db.execute_read(
        """
        SELECT path, COUNT(*) AS cnt
        FROM access_logs
        WHERE timestamp >= datetime('now', ?, 'localtime')
        GROUP BY path
        ORDER BY cnt DESC
        LIMIT 1
        """,
        [time_param],
    )
    top_endpoint = top_rows[0][0] if top_rows else None

    return {
        "total_requests": total_requests,
        "unique_ips": unique_ips,
        "avg_response_time_ms": avg_response_time_ms,
        "top_endpoint": top_endpoint,
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
        SELECT
            ip_address,
            COUNT(*) AS request_count,
            MAX(timestamp) AS last_seen,
            (
                SELECT path
                FROM access_logs AS sub
                WHERE sub.ip_address = main.ip_address
                  AND sub.timestamp >= datetime('now', ?, 'localtime')
                GROUP BY path
                ORDER BY COUNT(*) DESC
                LIMIT 1
            ) AS top_endpoint
        FROM access_logs AS main
        WHERE timestamp >= datetime('now', ?, 'localtime')
        GROUP BY ip_address
        ORDER BY request_count DESC
        LIMIT ?
        """,
        [time_param, time_param, limit],
    )

    return [
        {
            "ip_address": row[0],
            "request_count": row[1],
            "last_seen": row[2],
            "top_endpoint": row[3],
        }
        for row in rows
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
        }
        for row in rows
    ]

    return {"items": items, "total": total}
