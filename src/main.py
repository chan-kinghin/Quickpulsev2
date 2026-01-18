"""FastAPI application entrypoint for QuickPulse V2."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.middleware.rate_limit import setup_rate_limiting
from src.api.routers import auth, mto, sync
from src.config import Config
from src.database.connection import Database
from src.kingdee.client import KingdeeClient
from src.query.mto_handler import MTOQueryHandler
from src.readers import (
    MaterialPickingReader,
    ProductionBOMReader,
    ProductionOrderReader,
    ProductionReceiptReader,
    PurchaseOrderReader,
    PurchaseReceiptReader,
    SalesDeliveryReader,
    SalesOrderReader,
    SubcontractingOrderReader,
)
from src.sync.progress import SyncProgress
from src.sync.scheduler import SyncScheduler
from src.sync.sync_service import SyncService


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = Config.load()
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    config.reports_dir.mkdir(parents=True, exist_ok=True)

    db = Database(config.db_path)
    await db.connect()

    kingdee_client = KingdeeClient(config.kingdee)

    readers = {
        "production_order": ProductionOrderReader(kingdee_client),
        "production_bom": ProductionBOMReader(kingdee_client),
        "production_receipt": ProductionReceiptReader(kingdee_client),
        "purchase_order": PurchaseOrderReader(kingdee_client),
        "purchase_receipt": PurchaseReceiptReader(kingdee_client),
        "subcontracting_order": SubcontractingOrderReader(kingdee_client),
        "material_picking": MaterialPickingReader(kingdee_client),
        "sales_delivery": SalesDeliveryReader(kingdee_client),
        "sales_order": SalesOrderReader(kingdee_client),
    }

    progress = SyncProgress(config.reports_dir / "sync_status.json")
    sync_service = SyncService(readers=readers, db=db, progress=progress)
    mto_handler = MTOQueryHandler(
        production_order_reader=readers["production_order"],
        production_bom_reader=readers["production_bom"],
        production_receipt_reader=readers["production_receipt"],
        purchase_order_reader=readers["purchase_order"],
        purchase_receipt_reader=readers["purchase_receipt"],
        subcontracting_order_reader=readers["subcontracting_order"],
        material_picking_reader=readers["material_picking"],
        sales_delivery_reader=readers["sales_delivery"],
        sales_order_reader=readers["sales_order"],
    )

    loop = asyncio.get_running_loop()
    scheduler = SyncScheduler(config.sync, sync_service, loop=loop)
    scheduler.start()

    app.state.config = config
    app.state.db = db
    app.state.readers = readers
    app.state.sync_progress = progress
    app.state.sync_service = sync_service
    app.state.mto_handler = mto_handler
    app.state.scheduler = scheduler

    yield

    scheduler.stop()
    await db.close()


app = FastAPI(title="QuickPulse V2", lifespan=lifespan)
setup_rate_limiting(app)

app.mount("/static", StaticFiles(directory="src/frontend/static"), name="static")

app.include_router(auth.router)
app.include_router(sync.router)
app.include_router(mto.router)


@app.get("/")
async def root():
    return FileResponse("src/frontend/index.html")


@app.get("/dashboard.html")
async def dashboard():
    return FileResponse("src/frontend/dashboard.html")


@app.get("/sync.html")
async def sync_page():
    return FileResponse("src/frontend/sync.html")


@app.get("/health")
async def health():
    return {"status": "healthy"}
