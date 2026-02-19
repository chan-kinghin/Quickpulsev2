"""MTO query endpoints."""

import csv
import logging
from typing import List
from io import StringIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response

from src.api.middleware.rate_limit import limiter
from src.api.routers.auth import get_current_user
from src.exceptions import KingdeeConnectionError, QuickPulseError
from src.models.mto_status import MTOSummary, MTOStatusResponse, MTORelatedOrdersResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["mto"])


@router.get("/mto/{mto_number}", response_model=MTOStatusResponse)
@limiter.limit("30/minute")
async def get_mto_status(
    request: Request,
    mto_number: str = Path(..., min_length=2, max_length=50, pattern=r"^[A-Za-z0-9\-]+$"),
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
    except KingdeeConnectionError as exc:
        logger.exception("Kingdee connection error for MTO %s", mto_number)
        raise HTTPException(status_code=502, detail="ERP system unavailable") from exc
    except QuickPulseError as exc:
        logger.exception("Application error for MTO %s", mto_number)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    except Exception as exc:
        logger.exception("Unhandled error for MTO %s", mto_number)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/mto/{mto_number}/related-orders", response_model=MTORelatedOrdersResponse)
@limiter.limit("30/minute")
async def get_mto_related_orders(
    request: Request,
    mto_number: str = Path(..., min_length=2, max_length=50, pattern=r"^[A-Za-z0-9\-]+$"),
    current_user: str = Depends(get_current_user),
):
    """Get all related order bill numbers for a given MTO number."""
    handler = request.app.state.mto_handler
    try:
        return await handler.get_related_orders(mto_number)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KingdeeConnectionError as exc:
        logger.exception("Kingdee connection error for related orders %s", mto_number)
        raise HTTPException(status_code=502, detail="ERP system unavailable") from exc
    except QuickPulseError as exc:
        logger.exception("Application error for related orders %s", mto_number)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    except Exception as exc:
        logger.exception("Unhandled error for related orders %s", mto_number)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/search", response_model=List[MTOSummary])
@limiter.limit("60/minute")
async def search_mto(
    request: Request,
    response: Response,
    q: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: str = Depends(get_current_user),
):
    db = request.app.state.db
    # Escape SQL LIKE wildcards so % and _ in user input are treated literally
    escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like_value = f"%{escaped_q}%"
    count_rows = await db.execute_read(
        """
        SELECT COUNT(*)
        FROM cached_production_orders
        WHERE mto_number LIKE ? ESCAPE '\\' OR material_name LIKE ? ESCAPE '\\'
        """,
        [like_value, like_value],
    )
    total = count_rows[0][0] if count_rows else 0
    rows = await db.execute_read(
        """
        SELECT mto_number, material_name, qty
        FROM cached_production_orders
        WHERE mto_number LIKE ? ESCAPE '\\' OR material_name LIKE ? ESCAPE '\\'
        ORDER BY synced_at DESC
        LIMIT ? OFFSET ?
        """,
        [like_value, like_value, limit, offset],
    )
    results = [
        MTOSummary(
            mto_number=row[0],
            material_name=row[1] or "",
            order_qty=row[2] or 0,
            status="cached",
        )
        for row in rows
    ]
    response.headers["X-Total-Count"] = str(total)
    return results


@router.get("/export/mto/{mto_number}")
@limiter.limit("20/minute")
async def export_mto_excel(
    request: Request,
    mto_number: str = Path(..., min_length=2, max_length=50, pattern=r"^[A-Za-z0-9\-]+$"),
    use_cache: bool = Query(False, description="Use cached data (default: false for exports)"),
    current_user: str = Depends(get_current_user),
):
    """Export MTO status to CSV. Uses live data by default for accuracy."""
    handler = request.app.state.mto_handler
    try:
        status = await handler.get_status(mto_number, use_cache=use_cache)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KingdeeConnectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except QuickPulseError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(exc)}") from exc

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "物料编码",
            "物料名称",
            "规格型号",
            "BOM简称",
            "辅助属性",
            "物料类型",
            "销售订单.数量",
            "生产入库单.应收数量",
            "采购订单.数量",
            "生产领料单.实发数量",
            "生产入库单.实收数量",
            "采购订单.累计入库数量",
        ]
    )

    for child in status.children:
        writer.writerow(
            [
                child.material_code,
                child.material_name,
                child.specification,
                child.bom_short_name,
                child.aux_attributes,
                child.material_type_name,
                child.sales_order_qty,
                child.prod_instock_must_qty,
                child.purchase_order_qty,
                child.pick_actual_qty,
                child.prod_instock_real_qty,
                child.purchase_stock_in_qty,
            ]
        )

    filename = f"MTO_{mto_number}.csv"
    # RFC 5987 encoding for non-ASCII filename compatibility
    filename_encoded = quote(filename, safe='')
    return Response(
        content=output.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{filename_encoded}"
        },
    )
