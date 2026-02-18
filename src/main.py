"""FastAPI application entrypoint for QuickPulse V2."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from src.logging_config import setup_logging

# Configure logging before anything else
setup_logging(log_level="INFO")
logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.api.middleware.rate_limit import setup_rate_limiting
from src.exceptions import KingdeeConnectionError, QuickPulseError

# Map HTTP status codes to machine-readable error codes for consistent API responses.
_STATUS_ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "erp_unavailable",
    503: "service_unavailable",
}
from src.api.routers import agent_chat, auth, cache, chat, mto, sync
from src.chat.client import LLMClient
from src.config import Config
from src.database.connection import Database
from src.kingdee.client import KingdeeClient
from src.mto_config import MTOConfig
from src.query.cache_reader import CacheReader
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
    sync_service = SyncService(
        readers=readers,
        db=db,
        progress=progress,
        parallel_chunks=config.sync.performance.parallel_chunks,
    )

    # Note: mto_handler callback will be registered after creation below

    # Initialize cache reader with configured TTL
    cache_ttl = config.sync.query_cache.ttl_minutes
    cache_reader = CacheReader(db, ttl_minutes=cache_ttl) if config.sync.query_cache.enabled else None

    # Load MTO configuration for material class routing
    mto_config = MTOConfig("config/mto_config.json")
    logger.info("Loaded MTO config with %d material classes", len(mto_config.material_classes))

    # Build semantic metric engine from config
    metric_engine = mto_config.build_metric_engine()

    # Initialize MTO handler with memory cache configuration
    memory_cfg = config.sync.memory_cache
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
        cache_reader=cache_reader,
        mto_config=mto_config,
        metric_engine=metric_engine,
        memory_cache_enabled=memory_cfg.enabled,
        memory_cache_size=memory_cfg.max_size,
        memory_cache_ttl=memory_cfg.ttl_seconds,
    )

    # Register callback to clear memory cache after sync completes
    sync_service.add_post_sync_callback(mto_handler.clear_memory_cache)

    # Warm cache on startup with recently synced MTOs
    if memory_cfg.enabled and memory_cfg.warm_on_startup:
        try:
            recent_mtos = await db.execute_read(
                """
                SELECT DISTINCT mto_number
                FROM cached_production_orders
                ORDER BY synced_at DESC
                LIMIT ?
                """,
                [memory_cfg.warm_count],
            )
            if recent_mtos:
                mto_list = [row[0] for row in recent_mtos if row[0]]
                warm_result = await mto_handler.warm_cache(mto_list)
                logger.info(
                    "Startup cache warming: %d MTOs warmed, %d failed",
                    warm_result.get("warmed", 0),
                    warm_result.get("failed", 0),
                )
        except Exception as exc:
            logger.warning("Startup cache warming failed: %s", exc)

    # Initialize LLM chat providers (optional — graceful degradation)
    chat_providers = {}
    if config.deepseek.is_available():
        chat_providers["deepseek"] = LLMClient(config.deepseek)
        logger.info("DeepSeek chat enabled (model=%s)", config.deepseek.model)
    if config.qwen.is_available():
        chat_providers["qwen"] = LLMClient(config.qwen)
        logger.info("Qwen chat enabled (model=%s)", config.qwen.model)
    if not chat_providers:
        logger.info("No LLM chat providers configured")

    # Set active provider: first available, or None
    active_provider = next(iter(chat_providers), None)
    chat_client = chat_providers.get(active_provider) if active_provider else None

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
    app.state.chat_client = chat_client
    app.state.chat_providers = chat_providers
    app.state.active_chat_provider = active_provider
    app.state.mto_config = mto_config

    yield

    scheduler.stop()
    for client in chat_providers.values():
        await client.close()
    await db.close()


app = FastAPI(title="QuickPulse V2", lifespan=lifespan)
setup_rate_limiting(app)

cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
if cors_origins:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in cors_origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def add_api_version_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["X-API-Version"] = "1"
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Enrich all HTTPException responses with a consistent error_code field."""
    error_code = _STATUS_ERROR_CODES.get(exc.status_code, "internal_error")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": error_code},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(KingdeeConnectionError)
async def kingdee_connection_handler(request: Request, exc: KingdeeConnectionError):
    logger.error("Kingdee connection error: %s", exc)
    return JSONResponse(
        status_code=502,
        content={"detail": "ERP system unavailable", "error_code": "erp_unavailable"},
    )


@app.exception_handler(QuickPulseError)
async def quickpulse_error_handler(request: Request, exc: QuickPulseError):
    logger.error("Application error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_code": "internal_error"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_code": "internal_error"},
    )


app.mount("/static", StaticFiles(directory="src/frontend/static"), name="static")

app.include_router(auth.router)
app.include_router(sync.router)
app.include_router(mto.router)
app.include_router(cache.router)
app.include_router(chat.router)
app.include_router(agent_chat.router)


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
