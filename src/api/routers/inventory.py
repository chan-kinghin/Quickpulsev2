"""Inventory search endpoints — material-pivot, real-time Kingdee queries."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from src.api.middleware.rate_limit import limiter
from src.api.routers.auth import get_current_user
from src.exceptions import KingdeeConnectionError, QuickPulseError
from src.models.inventory import InventoryDetail, InventorySearchResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("/search", response_model=InventorySearchResponse)
@limiter.limit("20/minute")
async def search_inventory(
    request: Request,
    q: str = Query(..., min_length=2, max_length=50),
    limit: int = Query(20, ge=1, le=50),
    current_user: str = Depends(get_current_user),
):
    """Search materials by code / name / specification (fuzzy)."""
    reader = request.app.state.inventory_reader
    try:
        return await reader.search_materials(q=q, limit=limit)
    except ValueError as exc:
        # sanitize_query rejected the input
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KingdeeConnectionError as exc:
        logger.exception("Kingdee connection error during inventory search q=%s", q)
        raise HTTPException(status_code=502, detail="ERP system unavailable") from exc
    except QuickPulseError as exc:
        logger.exception("Application error during inventory search q=%s", q)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    except Exception as exc:
        logger.exception("Unhandled error during inventory search q=%s", q)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/material/{material_code}", response_model=InventoryDetail)
@limiter.limit("20/minute")
async def get_material_inventory(
    request: Request,
    material_code: str = Path(..., min_length=1, max_length=50, pattern=r"^[A-Za-z0-9\.\-]+$"),
    include_zero: bool = Query(False, description="Include warehouses with zero stock"),
    current_user: str = Depends(get_current_user),
):
    """Get per-warehouse inventory breakdown for one material."""
    reader = request.app.state.inventory_reader
    try:
        return await reader.get_inventory_by_material(
            material_code=material_code,
            include_zero=include_zero,
        )
    except KingdeeConnectionError as exc:
        logger.exception("Kingdee connection error for material %s", material_code)
        raise HTTPException(status_code=502, detail="ERP system unavailable") from exc
    except QuickPulseError as exc:
        logger.exception("Application error for material %s", material_code)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    except Exception as exc:
        logger.exception("Unhandled error for material %s", material_code)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
