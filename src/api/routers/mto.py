"""MTO query endpoints."""

import csv
from typing import List
from io import StringIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from src.api.middleware.rate_limit import limiter
from src.api.routers.auth import get_current_user
from src.models.mto_status import MTOSummary, MTOStatusResponse, MTORelatedOrdersResponse

router = APIRouter(prefix="/api", tags=["mto"])


@router.get("/mto/{mto_number}", response_model=MTOStatusResponse)
@limiter.limit("30/minute")
async def get_mto_status(
    request: Request,
    mto_number: str,
    use_cache: bool = Query(True, description="Use cached data if available and fresh"),
    current_user: str = Depends(get_current_user),
):
    """Get MTO status with optional cache-first strategy.

    - use_cache=true (default): Returns cached data if fresh (<1 hour), much faster
    - use_cache=false: Always fetch real-time data from Kingdee API
    """
    handler = request.app.state.mto_handler
    try:
        return await handler.get_status(mto_number, use_cache=use_cache)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        import traceback
        error_detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail) from exc


@router.get("/mto/{mto_number}/related-orders", response_model=MTORelatedOrdersResponse)
@limiter.limit("30/minute")
async def get_mto_related_orders(
    request: Request,
    mto_number: str,
    current_user: str = Depends(get_current_user),
):
    """Get all related order bill numbers for a given MTO number."""
    handler = request.app.state.mto_handler
    try:
        return await handler.get_related_orders(mto_number)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        import traceback
        error_detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        raise HTTPException(status_code=500, detail=error_detail) from exc


@router.get("/search")
@limiter.limit("60/minute")
async def search_mto(
    request: Request,
    q: str = Query(..., min_length=2),
    current_user: str = Depends(get_current_user),
) -> List[MTOSummary]:
    db = request.app.state.db
    like_value = f"%{q}%"
    rows = await db.execute(
        """
        SELECT mto_number, material_name, qty
        FROM cached_production_orders
        WHERE mto_number LIKE ? OR material_name LIKE ?
        ORDER BY synced_at DESC
        LIMIT 20
        """,
        [like_value, like_value],
    )
    return [
        MTOSummary(
            mto_number=row[0],
            material_name=row[1] or "",
            order_qty=row[2] or 0,
            status="cached",
        )
        for row in rows
    ]


@router.get("/export/mto/{mto_number}")
@limiter.limit("20/minute")
async def export_mto_excel(
    request: Request,
    mto_number: str,
    use_cache: bool = Query(False, description="Use cached data (default: false for exports)"),
    current_user: str = Depends(get_current_user),
):
    """Export MTO status to CSV. Uses live data by default for accuracy."""
    handler = request.app.state.mto_handler
    try:
        status = await handler.get_status(mto_number, use_cache=use_cache)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "物料编码",
            "物料名称",
            "规格型号",
            "物料类型",
            "需求量",
            "已领量",
            "未领量",
            "订单数量",
            "入库量",
            "未入库量",
            "销售出库",
            "即时库存",
        ]
    )

    for child in status.children:
        writer.writerow(
            [
                child.material_code,
                child.material_name,
                child.specification,
                child.material_type_name,
                child.required_qty,
                child.picked_qty,
                child.unpicked_qty,
                child.order_qty,
                child.receipt_qty,
                child.unreceived_qty,
                child.delivered_qty,
                child.inventory_qty,
            ]
        )

    filename = f"MTO_{mto_number}.csv"
    # RFC 5987 encoding for non-ASCII filename compatibility
    filename_encoded = quote(filename, safe='')
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{filename_encoded}"
        },
    )
