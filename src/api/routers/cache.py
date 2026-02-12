"""Cache management API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from src.api.middleware.rate_limit import limiter
from src.api.routers.auth import get_current_user

router = APIRouter(prefix="/api/cache", tags=["cache"])


@router.get("/stats")
async def get_cache_stats(
    api_request: Request,
    current_user: str = Depends(get_current_user),
):
    """Get cache statistics for monitoring.

    Returns hit rates, sizes, and configuration for both memory and SQLite caches.
    Also includes query frequency statistics for smart cache warming.
    """
    mto_handler = api_request.app.state.mto_handler
    stats = mto_handler.get_cache_stats()
    stats["query_stats"] = mto_handler.get_query_stats()
    return stats


@router.post("/clear")
@limiter.limit("10/minute")
async def clear_memory_cache(
    request: Request,
    current_user: str = Depends(get_current_user),
):
    """Clear the in-memory cache.

    Use this after manual data updates in Kingdee to force fresh data.
    Does not affect the SQLite cache.
    """
    mto_handler = request.app.state.mto_handler
    cleared = mto_handler.clear_memory_cache()
    return {"status": "cleared", "entries_cleared": cleared}


@router.post("/reset-stats")
async def reset_cache_stats(
    api_request: Request,
    current_user: str = Depends(get_current_user),
):
    """Reset cache statistics counters.

    Use this to start fresh measurements after configuration changes.
    """
    mto_handler = api_request.app.state.mto_handler
    mto_handler.reset_stats()
    return {"status": "stats_reset"}


@router.delete("/{mto_number}")
async def invalidate_mto(
    mto_number: str,
    api_request: Request,
    current_user: str = Depends(get_current_user),
):
    """Invalidate a specific MTO from memory cache.

    Use this when you know a specific MTO was updated in Kingdee.
    """
    mto_handler = api_request.app.state.mto_handler
    removed = mto_handler.invalidate_mto(mto_number)
    return {"status": "invalidated" if removed else "not_found", "mto_number": mto_number}


@router.post("/warm")
@limiter.limit("5/minute")
async def warm_cache(
    request: Request,
    count: int = Query(100, ge=1, le=500, description="Number of MTOs to warm"),
    use_hot: bool = Query(False, description="Use hot MTOs from query history instead of recent synced"),
    current_user: str = Depends(get_current_user),
):
    """Warm the memory cache with MTOs.

    Two warming strategies:
    - use_hot=false (default): Load recently synced MTOs from SQLite
    - use_hot=true: Load most frequently queried MTOs from query history
    """
    mto_handler = request.app.state.mto_handler
    db = request.app.state.db

    if use_hot:
        # Use hot MTOs from query history
        mto_list = mto_handler.get_hot_mtos(count)
        source = "query_history"
    else:
        # Use recently synced MTOs from SQLite
        recent_mtos = await db.execute_read(
            """
            SELECT DISTINCT mto_number
            FROM cached_production_orders
            ORDER BY synced_at DESC
            LIMIT ?
            """,
            [count],
        )
        mto_list = [row[0] for row in recent_mtos if row[0]]
        source = "recent_synced"

    if not mto_list:
        return {"status": "no_mtos_found", "source": source, "warmed": 0, "failed": 0}

    result = await mto_handler.warm_cache(mto_list)
    result["source"] = source
    result["requested"] = count
    return result


@router.get("/hot-mtos")
async def get_hot_mtos(
    api_request: Request,
    top_n: int = Query(20, ge=1, le=100, description="Number of hot MTOs to return"),
    current_user: str = Depends(get_current_user),
):
    """Get the most frequently queried MTOs.

    Use this to understand query patterns and configure cache warming.
    """
    mto_handler = api_request.app.state.mto_handler
    hot_mtos = mto_handler.get_hot_mtos(top_n)
    query_stats = mto_handler.get_query_stats()
    return {
        "hot_mtos": hot_mtos,
        "total_unique_mtos": query_stats["total_unique_mtos"],
        "total_queries": query_stats["total_queries"],
    }
