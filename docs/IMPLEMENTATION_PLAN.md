# QuickPulse V2 Implementation Plan

## 1. Project Overview

### Objective
Build a web dashboard that displays **产品状态明细表** (Product Status Detail Sheet) when searching by **计划跟踪号** (MTO Number).

### Target Display Structure

When user searches by MTO Number (e.g., `AK2510034`), display a hierarchical view:

#### Parent Item (父项) - From Production Order (PRD_MO)
| Column | API Field | Description |
|--------|-----------|-------------|
| 生产订单编号 | FBillNo | Production Order Number |
| 生产车间 | FWorkShopID | Workshop |
| 计划跟踪号 | FMTONo | MTO Number (search key) |
| 父项物料编码 | FMaterialId.FNumber | Parent Material Code |
| 父项物料名称 | FMaterialId.FName | Parent Material Name |
| 父项规格型号 | FMaterialId.FSpecification | Parent Spec |
| 父项辅助属性 | FAuxPropId | Color/Spec (物料规格+产品颜色) |
| 订单数量 | FQty | Order Quantity |

#### Child Items (子项) - From Production BOM (PRD_PPBOM)
| Column | API Field | Source | Notes |
|--------|-----------|--------|-------|
| 子项物料编码 | FMaterialID.FNumber | PRD_PPBOM | |
| 子项物料名称 | FMaterialID.FName | PRD_PPBOM | |
| 子项规格型号 | FMaterialID.FSpecification | PRD_PPBOM | |
| 子项辅助属性 | FAuxPropId | PRD_PPBOM | 产品颜色 |
| **物料类型** | FMaterialType | PRD_PPBOM | 1=自制, 2=外购, 3=委外 |
| 需求数量 | FNeedQty | PRD_PPBOM | BOM requirement |
| 已领数量 | FPickedQty | PRD_PPBOM | |
| 未领数量 | FNoPickedQty | PRD_PPBOM | negative = 超领 |
| **订单数量** | FQty | PUR_PurchaseOrder / SUB_POORDER | 外购/委外 only |
| **入库数量** | FRealQty | *See below* | Source by type |
| **未入库数量** | FRemainStockInQty / FNoStockInQty | PUR/SUB Order | Or calculated |
| 销售出库 | FRealQty | SAL_OUTSTOCK | |
| 即时库存 | F_QWJI_JSKC | Custom field | Real-time |

#### 入库数量 Source by Material Type
| Material Type | Chinese | 入库数量 Source |
|--------------|---------|-----------------|
| 1 (自制) | 生产入库 | PRD_INSTOCK `FEntity_FRealQty` |
| 2 (外购) | 采购入库 | STK_InStock `FInStockEntry_FRealQty` (FBillTypeID=RKD01_SYS) |
| 3 (委外) | 委外入库 | STK_InStock `FInStockEntry_FRealQty` (FBillTypeID=RKD02_SYS) |

---

## 2. Architecture

### Two-Layer Data Architecture

```
Layer 1 (Cache)     → SQLite snapshot cache    → <100ms queries
Layer 2 (Real-time) → Direct API calls         → 1-5s queries
```

### Data Flow (MTO Tracing)

```
User Input: 计划跟踪号 (MTO Number)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 1: Query PRD_MO (生产订单) - Parent Item Info          │
│   FilterString: FMTONo='AK2510034'                         │
│   Get: FBillNo, FMaterialId, FQty (订单数量), FWorkShopID  │
└─────────────────────────────────────────────────────────────┘
         │
         ▼ FMOBillNO (from PRD_MO.FBillNo)
┌─────────────────────────────────────────────────────────────┐
│ Step 2: Query PRD_PPBOM (生产用料清单) - Child Items        │
│   FilterString: FMOBillNO='MO251203242'                    │
│   Get: Child materials, FMaterialType, FNeedQty,           │
│        FPickedQty, FNoPickedQty                            │
│   NOTE: FMaterialType determines receipt source!           │
└─────────────────────────────────────────────────────────────┘
         │
         ▼ Parallel queries based on material type
┌─────────────────────────────────────────────────────────────┐
│ Step 3a: PRD_INSTOCK (生产入库) - 自制品 (FMaterialType=1)  │
│   Filter: FEntity_FMtoNo='AK2510034'                       │
│   Get: FRealQty for self-made items                        │
├─────────────────────────────────────────────────────────────┤
│ Step 3b: PUR_PurchaseOrder - 外购物料 Order Info            │
│   Filter: FPOOrderEntry_FMtoNo='AK2510034'                 │
│   Get: 采购数量(FQty), 累计入库(FStockInQty),              │
│        剩余入库(FRemainStockInQty)                         │
├─────────────────────────────────────────────────────────────┤
│ Step 3c: STK_InStock (采购入库) - 外购物料 Receipts         │
│   Filter: FInStockEntry_FMtoNo='AK2510034'                 │
│          AND FBillTypeID.FNumber='RKD01_SYS'               │
│   Get: FRealQty for purchased items                        │
├─────────────────────────────────────────────────────────────┤
│ Step 3d: SUB_POORDER - 委外加工 Order Info                  │
│   Filter: FTreeEntity_FMtoNo='AK2510034'                   │
│   Get: 委外数量(FQty), 入库数量(FStockInQty),              │
│        未入库(FNoStockInQty)                               │
├─────────────────────────────────────────────────────────────┤
│ Step 3e: STK_InStock (委外入库) - 委外加工 Receipts         │
│   Filter: FInStockEntry_FMtoNo='AK2510034'                 │
│          AND FBillTypeID.FNumber='RKD02_SYS'               │
│   Get: FRealQty for subcontracted items                    │
├─────────────────────────────────────────────────────────────┤
│ Step 3f: PRD_PickMtrl (生产领料) - 领料跟踪                 │
│   Filter: FEntity_FMTONO='AK2510034'                       │
│   Get: 申请数量(FAppQty), 实发数量(FActualQty)             │
├─────────────────────────────────────────────────────────────┤
│ Step 3g: SAL_OUTSTOCK (销售出库) - 出库跟踪                 │
│   Filter: FSAL_OUTSTOCKENTRY_FMTONO='AK2510034'            │
│   Get: FRealQty for delivered items                        │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 4: Aggregate by Material Type                          │
│   - Match child materials by code across all sources       │
│   - Use correct receipt source based on FMaterialType:     │
│     * 自制(1) → PRD_INSTOCK                                │
│     * 外购(2) → STK_InStock (标准采购)                     │
│     * 委外(3) → STK_InStock (委外入库)                     │
│   - Calculate 未入库数量 = 需求数量 - 入库数量             │
│   - Highlight negative 未领数量 (超领)                      │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 5: Return MTOStatusResponse                            │
│   - Parent item info                                       │
│   - List of child items with all quantities by type        │
└─────────────────────────────────────────────────────────────┘
```

### Quantity Source Logic by Material Type

**IMPORTANT**: Quantities come from different sources depending on the material type. PRD_PPBOM provides the BOM structure and picking quantities, but **receipt quantities** come from different forms.

#### Material Type Determination

The `FMaterialType` field in PRD_PPBOM indicates:
- `1` = 自制件 (Self-made) → Receipt from PRD_INSTOCK
- `2` = 外购件 (Purchased) → Receipt from STK_InStock (标准采购入库)
- `3` = 委外件 (Subcontracted) → Receipt from STK_InStock (委外入库)

#### Quantity Source Matrix

| Material Type | Chinese | Order Qty Source | Receipt Qty Source | Form ID |
|--------------|---------|------------------|-------------------|---------|
| **Parent Item** | 生产订单 | PRD_MO `FQty` | PRD_INSTOCK `FRealQty` | PRD_MO, PRD_INSTOCK |
| **Self-made** (自制件) | 生产入库 | PRD_PPBOM `FNeedQty` | PRD_INSTOCK `FRealQty` | PRD_PPBOM, PRD_INSTOCK |
| **Purchased** (外购物料) | 采购入库 | PUR_PurchaseOrder `FQty` | STK_InStock `FRealQty` | PUR_PurchaseOrder, STK_InStock |
| **Subcontracted** (委外加工) | 委外入库 | SUB_POORDER `FQty` | STK_InStock `FRealQty` | SUB_POORDER, STK_InStock |
| **Picking** (领料) | 生产领料 | PRD_PPBOM `FMustQty` | PRD_PickMtrl `FRealQty` | PRD_PPBOM, PRD_PickMtrl |
| **Sales** (销售出库) | 销售出库 | SAL_SaleOrder `FQty` | SAL_OUTSTOCK `FRealQty` | SAL_SaleOrder, SAL_OUTSTOCK |

#### Key Fields by Source

**For 外购物料 (Purchased Materials)**
```python
# From PUR_PurchaseOrder
采购数量 = FPOOrderEntry_FQty
累计入库数量 = FPOOrderEntry_FStockInQty
剩余入库数量 = FPOOrderEntry_FRemainStockInQty

# From STK_InStock
实收数量 = FInStockEntry_FRealQty
```

**For 委外加工 (Subcontracted Items)**
```python
# From SUB_POORDER
委外数量 = FTreeEntity_FQty
已入库数量 = FTreeEntity_FStockInQty
未入库数量 = FTreeEntity_FNoStockInQty

# From STK_InStock (单据类型=委外入库单)
实收数量 = FInStockEntry_FRealQty
```

**For 自制件 (Self-made Items)**
```python
# From PRD_PPBOM
需求数量 = FPPBomEntry_FNeedQty

# From PRD_INSTOCK
实收数量 = FEntity_FRealQty
```

**For 领料跟踪 (Material Picking)**
```python
# From PRD_PickMtrl
申请数量 = FEntity_FAppQty
实发数量 = FEntity_FActualQty  # or FRealQty
```

#### STK_InStock Document Type Differentiation

The STK_InStock form handles both purchase receipts and subcontracting receipts:
- **标准采购入库**: `FBillTypeID` = standard purchase
- **委外入库**: `FBillTypeID` = subcontracting receipt

Filter example:
```python
# For purchased materials only
FilterString: "FInStockEntry_FMtoNo='AK2510034' AND FBillTypeID.FNumber='RKD01_SYS'"

# For subcontracting receipts only
FilterString: "FInStockEntry_FMtoNo='AK2510034' AND FBillTypeID.FNumber='RKD02_SYS'"
```

---

## 3. Security & Authentication

### 3.1 Authentication Strategy

**Approach**: JWT (JSON Web Token) authentication using `python-jose` library.

#### JWT Configuration

**File: `src/auth/config.py`**

```python
from datetime import timedelta
from pydantic_settings import BaseSettings

class AuthConfig(BaseSettings):
    """JWT Authentication Configuration"""
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    class Config:
        env_prefix = "AUTH_"
```

#### Authentication Router

**File: `src/api/routers/auth.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=30))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return username

@router.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # Validate user credentials (implement your user validation)
    if not validate_user(form_data.username, form_data.password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}
```

#### Protecting Routes

```python
from src.api.routers.auth import get_current_user

@router.get("/api/mto/{mto_number}")
async def get_mto_status(
    mto_number: str,
    current_user: str = Depends(get_current_user)  # Requires auth
):
    ...

@router.post("/api/sync/trigger")
async def trigger_sync(
    request: SyncTriggerRequest,
    current_user: str = Depends(get_current_user)  # Requires auth
):
    ...
```

### 3.2 Input Validation

**MTO Number Validation**:
```python
from fastapi import Path
import re

MTO_PATTERN = r"^[A-Z]{2}\d{7,10}$"  # e.g., AK2510034

@router.get("/api/mto/{mto_number}")
async def get_mto_status(
    mto_number: str = Path(..., regex=MTO_PATTERN, description="MTO tracking number")
):
    ...
```

### 3.3 Rate Limiting

**Using slowapi**:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@router.get("/api/mto/{mto_number}")
@limiter.limit("30/minute")
async def get_mto_status(request: Request, mto_number: str):
    ...
```

### 3.4 CORS Configuration

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)
```

### 3.5 Security Checklist

- [ ] JWT authentication implemented
- [ ] All API endpoints protected (except /health, /api/auth/token)
- [ ] Input validation with regex patterns
- [ ] Rate limiting enabled (30 req/min per IP)
- [ ] CORS configured for allowed origins
- [ ] Secrets not committed to git (conf.ini in .gitignore)
- [ ] HTTPS enforced in production

---

## 4. Parallel Development Setup

### Recommended: 4 Parallel Terminals

Based on the modular architecture, use **4 parallel terminals** for concurrent development:

| Terminal | Module | Dependencies | Workload |
|----------|--------|--------------|----------|
| **Terminal 1** | Foundation (config, database, kingdee client) | None (priority) | High |
| **Terminal 2** | Data Readers (8 Readers) | Depends on T1 KingdeeClient | High |
| **Terminal 3** | Sync Service + API Routes | Depends on T1+T2 | Medium |
| **Terminal 4** | Frontend Development | Can parallel with backend | Medium |

### Development Sequence

```
Timeline:
──────────────────────────────────────────────────────────────────>

Terminal 1: [Config] → [Database] → [KingdeeClient] → [Support others]
Terminal 2:            [Wait for Client] → [Readers: PRD_MO → PRD_PPBOM → ...]
Terminal 3:                              [Wait for Readers] → [SyncService] → [API]
Terminal 4: [HTML structure] → [Alpine components] → [Sync UI] → [Integration test]
```

---

## 4. Sync Configuration

### Sync Config Structure

**File: `sync_config.json`**

```json
{
  "auto_sync": {
    "enabled": true,
    "schedule": ["07:00", "12:00", "16:00", "18:00"],
    "days_back": 90
  },
  "manual_sync": {
    "default_days": 90,
    "max_days": 365,
    "min_days": 1
  },
  "performance": {
    "chunk_days": 7,
    "batch_size": 1000,
    "parallel_chunks": 2,
    "retry_count": 3
  }
}
```

### Manual Sync API

**Endpoint: `POST /api/sync/trigger`**

```python
class SyncTriggerRequest(BaseModel):
    days_back: int = Field(90, ge=1, le=365, description="Days to sync")
    chunk_days: Optional[int] = Field(7, ge=1, le=30, description="Chunk size in days")
    force_full: bool = Field(False, description="Force full refresh")

@router.post("/sync/trigger")
async def trigger_sync(
    request: SyncTriggerRequest,
    background_tasks: BackgroundTasks
) -> dict:
    """Manually trigger sync task"""
    if sync_service.is_running():
        raise HTTPException(409, "Sync task already running")

    background_tasks.add_task(
        sync_service.run_sync,
        days_back=request.days_back,
        chunk_days=request.chunk_days
    )
    return {"status": "sync_started", "days_back": request.days_back}
```

### Auto Sync Scheduler

**File: `src/sync/scheduler.py`**

```python
class SyncScheduler:
    def __init__(self, config: SyncConfig, sync_service: SyncService):
        self.config = config
        self.sync_service = sync_service
        self._scheduler = None

    def start(self):
        """Start auto sync scheduler"""
        if not self.config.auto_sync.enabled:
            logger.info("Auto sync disabled")
            return

        for time_str in self.config.auto_sync.schedule:
            schedule.every().day.at(time_str).do(self._sync_job)

        self._scheduler = threading.Thread(target=self._run_scheduler, daemon=True)
        self._scheduler.start()
        logger.info(f"Auto sync started: {self.config.auto_sync.schedule}")

    def _sync_job(self):
        """Execute sync task"""
        self.config.reload()  # Support runtime config changes
        days_back = self.config.auto_sync.days_back
        self.sync_service.run_sync(days_back=days_back)
```

### Sync Config API

**Endpoints: `GET/PUT /api/sync/config`**

```python
@router.get("/sync/config")
async def get_sync_config() -> SyncConfigResponse:
    """Get current sync configuration"""
    return SyncConfigResponse(
        auto_sync_enabled=config.auto_sync.enabled,
        auto_sync_schedule=config.auto_sync.schedule,
        auto_sync_days=config.auto_sync.days_back,
        manual_sync_default_days=config.manual_sync.default_days
    )

@router.put("/sync/config")
async def update_sync_config(request: SyncConfigUpdateRequest):
    """Update sync configuration"""
    if request.auto_sync_days:
        if not (1 <= request.auto_sync_days <= 365):
            raise HTTPException(400, "Sync days must be between 1-365")
        config.auto_sync.days_back = request.auto_sync_days

    if request.auto_sync_enabled is not None:
        config.auto_sync.enabled = request.auto_sync_enabled

    config.save()
    return {"status": "config_updated"}
```

### Sync Progress Tracking

**Status file: `reports/sync_status.json`**

```json
{
  "status": "running",
  "phase": "read",
  "message": "Reading production orders...",
  "started_at": "2026-01-17T09:00:00",
  "days_back": 90,
  "progress": {
    "prd_mo_count": 1234,
    "prd_ppbom_count": 5678,
    "prd_instock_count": 890,
    "pur_order_count": 456,
    "stk_instock_count": 321
  }
}
```

---

## 5. Implementation Phases

### Phase 1: Foundation

#### 1.1 Project Setup

**Create `pyproject.toml`:**
```toml
[project]
name = "quickpulse-v2"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "httpx>=0.26.0",
    "sqlalchemy>=2.0.25",
    "aiosqlite>=0.19.0",
    "schedule>=1.2.0",
    # Security dependencies
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "slowapi>=0.1.9",
]

[project.optional-dependencies]
dev = ["pytest>=7.4.0", "pytest-asyncio>=0.23.0", "httpx>=0.26.0"]
```

#### 1.2 Config Module

**File: `src/config.py`**

```python
"""
Configuration Management Module

Responsibilities:
1. Read Kingdee API credentials from conf.ini
2. Read sync config from sync_config.json
3. Support environment variable overrides
4. Config validation and defaults
"""

from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
import configparser
import json


class KingdeeConfig(BaseSettings):
    """Kingdee K3Cloud API Configuration"""
    server_url: str = Field(..., description="K3Cloud server URL")
    acct_id: str = Field(..., description="Account ID")
    user_name: str = Field(..., description="Username")
    app_id: str = Field(..., description="Application ID")
    app_sec: str = Field(..., description="Application Secret")
    lcid: int = Field(2052, description="Language ID (2052=Chinese)")
    connect_timeout: int = Field(15, description="Connection timeout (seconds)")
    request_timeout: int = Field(30, description="Request timeout (seconds)")

    @classmethod
    def from_ini(cls, ini_path: str = "conf.ini") -> "KingdeeConfig":
        """Load config from INI file"""
        config = configparser.ConfigParser()
        config.read(ini_path, encoding='utf-8')

        section = config['config']
        return cls(
            server_url=section['X-KDApi-ServerUrl'],
            acct_id=section['X-KDApi-AcctID'],
            user_name=section['X-KDApi-UserName'],
            app_id=section['X-KDApi-AppID'],
            app_sec=section['X-KDApi-AppSec'],
            lcid=int(section.get('X-KDApi-LCID', 2052)),
            connect_timeout=int(section.get('X-KDApi-ConnectTimeout', 15)),
            request_timeout=int(section.get('X-KDApi-RequestTimeout', 30))
        )


class AutoSyncConfig(BaseSettings):
    """Auto Sync Configuration"""
    enabled: bool = Field(True, description="Enable auto sync")
    schedule: list[str] = Field(
        ["07:00", "12:00", "16:00", "18:00"],
        description="Auto sync schedule (HH:MM format)"
    )
    days_back: int = Field(90, ge=1, le=365, description="Days to sync")

    @field_validator('schedule')
    def validate_schedule(cls, v):
        import re
        for time_str in v:
            if not re.match(r'^([01]?\d|2[0-3]):([0-5]\d)$', time_str):
                raise ValueError(f"Invalid time format: {time_str}")
        return v


class ManualSyncConfig(BaseSettings):
    """Manual Sync Configuration"""
    default_days: int = Field(90, description="Default sync days")
    max_days: int = Field(365, description="Maximum sync days")
    min_days: int = Field(1, description="Minimum sync days")


class PerformanceConfig(BaseSettings):
    """Performance Configuration"""
    chunk_days: int = Field(7, ge=1, le=30, description="Chunk days")
    batch_size: int = Field(1000, ge=100, le=10000, description="Batch insert size")
    parallel_chunks: int = Field(2, ge=1, le=4, description="Parallel chunk count")
    retry_count: int = Field(3, ge=1, le=5, description="Retry count")


class SyncConfig(BaseSettings):
    """Complete Sync Configuration"""
    auto_sync: AutoSyncConfig = Field(default_factory=AutoSyncConfig)
    manual_sync: ManualSyncConfig = Field(default_factory=ManualSyncConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)

    _config_path: str = "sync_config.json"

    @classmethod
    def load(cls, path: str = "sync_config.json") -> "SyncConfig":
        """Load config from JSON file"""
        config_path = Path(path)
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            instance = cls(**data)
        else:
            instance = cls()
        instance._config_path = path
        return instance

    def save(self):
        """Save config to JSON file"""
        with open(self._config_path, 'w', encoding='utf-8') as f:
            json.dump(self.model_dump(), f, indent=2, ensure_ascii=False)

    def reload(self):
        """Reload config (for detecting runtime changes)"""
        new_config = SyncConfig.load(self._config_path)
        self.auto_sync = new_config.auto_sync
        self.manual_sync = new_config.manual_sync
        self.performance = new_config.performance


class Config:
    """Main Config Class - Factory Pattern (NOT Singleton)

    Use FastAPI's Depends() for dependency injection instead of singleton.
    This enables easier testing and follows Dependency Inversion Principle.
    """

    def __init__(
        self,
        kingdee: KingdeeConfig,
        sync: SyncConfig,
        db_path: Path = Path("data/quickpulse.db"),
        reports_dir: Path = Path("reports")
    ):
        self.kingdee = kingdee
        self.sync = sync
        self.db_path = db_path
        self.reports_dir = reports_dir

    @classmethod
    def load(cls, ini_path: str = "conf.ini", sync_path: str = "sync_config.json") -> "Config":
        """Factory method to load config from files"""
        return cls(
            kingdee=KingdeeConfig.from_ini(ini_path),
            sync=SyncConfig.load(sync_path)
        )


# FastAPI dependency injection
from functools import lru_cache

@lru_cache()
def get_config() -> Config:
    """Get config instance (cached for performance)"""
    return Config.load()


def get_kingdee_client(config: Config = Depends(get_config)) -> KingdeeClient:
    """Get KingdeeClient via dependency injection"""
    return KingdeeClient(config.kingdee)


def get_database(config: Config = Depends(get_config)) -> Database:
    """Get Database via dependency injection"""
    return Database(config.db_path)
```

**Note**: Directory creation should be done in `main.py` lifespan handler, not in Config:

```python
# In src/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_config()
    # Create directories at startup
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    config.reports_dir.mkdir(parents=True, exist_ok=True)
    yield
```

#### 1.3 Kingdee Client Wrapper

**File: `src/kingdee/client.py`**

```python
"""
Kingdee K3Cloud API Client Wrapper

Responsibilities:
1. Wrap K3Cloud SDK calls
2. Unified error handling and retry logic
3. Support async queries
4. Date range chunk queries
"""

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional
from kingdee.cdp.webapi.sdk import K3CloudApiSdk

logger = logging.getLogger(__name__)


class KingdeeError(Exception):
    """Kingdee API error base class"""
    pass


class KingdeeConnectionError(KingdeeError):
    """Connection error"""
    pass


class KingdeeQueryError(KingdeeError):
    """Query error"""
    pass


class KingdeeClient:
    """K3Cloud SDK Wrapper"""

    def __init__(self, config: "KingdeeConfig"):
        self.config = config
        self._sdk: Optional[K3CloudApiSdk] = None
        self._lock = asyncio.Lock()

    async def _get_sdk(self) -> K3CloudApiSdk:
        """Get or create SDK instance (thread-safe)"""
        async with self._lock:
            if self._sdk is None:
                self._sdk = K3CloudApiSdk(self.config.server_url)
                self._sdk.InitConfig(
                    acct_id=self.config.acct_id,
                    user_name=self.config.user_name,
                    app_id=self.config.app_id,
                    app_sec=self.config.app_sec,
                    lcid=self.config.lcid
                )
            return self._sdk

    async def query(
        self,
        form_id: str,
        field_keys: list[str],
        filter_string: str = "",
        limit: int = 2000,
        start_row: int = 0
    ) -> list[dict]:
        """
        Execute Query API call

        Args:
            form_id: Form ID (e.g., PRD_MO, PRD_PPBOM)
            field_keys: Fields to return
            filter_string: Filter condition (SQL WHERE format)
            limit: Max records to return
            start_row: Starting row (for pagination)

        Returns:
            List of records, each record is a field-to-value dict

        Raises:
            KingdeeQueryError: When query fails
        """
        sdk = await self._get_sdk()

        params = {
            "FormId": form_id,
            "FieldKeys": ",".join(field_keys),
            "FilterString": filter_string,
            "Limit": limit,
            "StartRow": start_row
        }

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: sdk.ExecuteBillQuery(params)
            )

            if not response:
                return []

            # Convert 2D array to list of dicts
            return [
                dict(zip(field_keys, row))
                for row in response
            ]

        except Exception as e:
            logger.error(f"Kingdee query failed: {form_id}, error: {e}")
            raise KingdeeQueryError(f"Query {form_id} failed: {e}") from e

    async def query_all(
        self,
        form_id: str,
        field_keys: list[str],
        filter_string: str = "",
        page_size: int = 2000
    ) -> list[dict]:
        """
        Paginated query for all records

        Automatically handles pagination, returns all matching records
        """
        all_records = []
        start_row = 0

        while True:
            batch = await self.query(
                form_id=form_id,
                field_keys=field_keys,
                filter_string=filter_string,
                limit=page_size,
                start_row=start_row
            )

            if not batch:
                break

            all_records.extend(batch)

            if len(batch) < page_size:
                break  # Last page

            start_row += page_size

        logger.info(f"Query {form_id}: {len(all_records)} records total")
        return all_records

    async def query_by_date_range(
        self,
        form_id: str,
        field_keys: list[str],
        date_field: str,
        start_date: date,
        end_date: date,
        extra_filter: str = ""
    ) -> list[dict]:
        """
        Query by date range

        Args:
            date_field: Date field name (e.g., FDate, FCreateDate)
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            extra_filter: Additional filter conditions

        Returns:
            All records within date range
        """
        filter_parts = [
            f"{date_field}>='{start_date.isoformat()}'",
            f"{date_field}<='{end_date.isoformat()}'"
        ]

        if extra_filter:
            filter_parts.append(f"({extra_filter})")

        filter_string = " AND ".join(filter_parts)

        return await self.query_all(
            form_id=form_id,
            field_keys=field_keys,
            filter_string=filter_string
        )

    async def query_by_mto(
        self,
        form_id: str,
        field_keys: list[str],
        mto_field: str,
        mto_number: str
    ) -> list[dict]:
        """
        Query by MTO number

        Args:
            mto_field: MTO field name (varies by form)
            mto_number: 计划跟踪号

        Returns:
            Matching records
        """
        filter_string = f"{mto_field}='{mto_number}'"
        return await self.query_all(
            form_id=form_id,
            field_keys=field_keys,
            filter_string=filter_string
        )
```

#### 1.4 Pydantic Models

**File: `src/models/mto_status.py`**

```python
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class ParentItem(BaseModel):
    """Production order (parent item) info."""
    production_order_no: str      # 生产订单编号
    workshop: str                 # 生产车间
    mto_number: str               # 计划跟踪号
    material_code: str            # 父项物料编码
    material_name: str            # 父项物料名称
    specification: str            # 父项规格型号
    aux_attributes: str           # 父项辅助属性
    order_qty: Decimal            # 订单数量


class ChildItem(BaseModel):
    """BOM component (child item) with status."""
    # Basic Info
    material_code: str            # 子项物料编码
    material_name: str            # 子项物料名称
    specification: str            # 子项规格型号
    aux_attributes: str           # 子项辅助属性
    material_type: int            # 物料类型: 1=自制, 2=外购, 3=委外
    material_type_name: str       # 物料类型名称

    # BOM Quantities (from PRD_PPBOM)
    required_qty: Decimal         # 需求数量 (FNeedQty)
    picked_qty: Decimal           # 已领数量 (FPickedQty)
    unpicked_qty: Decimal         # 未领数量 (FNoPickedQty, negative = 超领)

    # Order Quantities (source depends on material_type)
    order_qty: Decimal            # 订单数量 (采购/委外订单)

    # Receipt Quantities (source depends on material_type)
    receipt_qty: Decimal          # 入库数量 (实收)
    unreceived_qty: Decimal       # 未入库数量 (calculated or from order)

    # Picking Quantities (from PRD_PickMtrl)
    pick_request_qty: Decimal     # 申请数量 (FAppQty)
    pick_actual_qty: Decimal      # 实发数量 (FActualQty)

    # Sales & Inventory
    delivered_qty: Decimal        # 销售出库
    inventory_qty: Decimal        # 即时库存

    # Source tracking
    receipt_source: str           # 入库来源: PRD_INSTOCK/STK_InStock/STK_InStock(委外)


class MTOStatusResponse(BaseModel):
    """Complete MTO status response."""
    mto_number: str
    parent: ParentItem
    children: list[ChildItem]
    query_time: datetime


class MTOSummary(BaseModel):
    """Summary for search results."""
    mto_number: str
    material_name: str
    order_qty: Decimal
    status: str
```

**File: `src/models/sync.py`** (API Request/Response Models)

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SyncTriggerRequest(BaseModel):
    """Request to trigger manual sync."""
    days_back: int = Field(90, ge=1, le=365, description="Days to sync")
    chunk_days: int = Field(7, ge=1, le=30, description="Chunk size in days")
    force_full: bool = Field(False, description="Force full refresh")


class SyncStatusResponse(BaseModel):
    """Sync status response."""
    status: str  # idle, running, success, error
    phase: str
    message: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    days_back: int
    progress: dict = {}
    error: Optional[str] = None


class SyncConfigResponse(BaseModel):
    """Sync configuration response."""
    auto_sync_enabled: bool
    auto_sync_schedule: list[str]
    auto_sync_days: int
    manual_sync_default_days: int


class SyncConfigUpdateRequest(BaseModel):
    """Request to update sync configuration."""
    auto_sync_enabled: Optional[bool] = None
    auto_sync_days: Optional[int] = Field(None, ge=1, le=365)
    manual_sync_default_days: Optional[int] = Field(None, ge=1, le=365)
```

#### 1.5 Database Schema

**File: `src/database/schema.sql`**

```sql
-- Enable WAL mode for better concurrent read/write performance
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;

-- Production orders cache
CREATE TABLE IF NOT EXISTS cached_production_orders (
    id INTEGER PRIMARY KEY,
    mto_number TEXT NOT NULL,
    bill_no TEXT NOT NULL UNIQUE,
    workshop TEXT,
    material_code TEXT,
    material_name TEXT,
    specification TEXT,
    aux_attributes TEXT,
    qty REAL,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_po_mto ON cached_production_orders(mto_number);
CREATE INDEX IF NOT EXISTS idx_po_synced ON cached_production_orders(synced_at);
CREATE INDEX IF NOT EXISTS idx_po_material ON cached_production_orders(material_code);

-- Production BOM cache
CREATE TABLE IF NOT EXISTS cached_production_bom (
    id INTEGER PRIMARY KEY,
    mo_bill_no TEXT NOT NULL,
    material_code TEXT NOT NULL,
    material_name TEXT,
    material_type INTEGER,  -- 1=自制, 2=外购, 3=委外
    need_qty REAL,
    picked_qty REAL,
    no_picked_qty REAL,
    raw_data TEXT,
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bom_mo ON cached_production_bom(mo_bill_no);
CREATE INDEX IF NOT EXISTS idx_bom_material ON cached_production_bom(material_code);
CREATE INDEX IF NOT EXISTS idx_bom_type ON cached_production_bom(material_type);

-- Sync history
CREATE TABLE IF NOT EXISTS sync_history (
    id INTEGER PRIMARY KEY,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status TEXT NOT NULL,  -- success/error
    days_back INTEGER,
    records_synced INTEGER,
    error_message TEXT
);
```

---

### Phase 2: Data Ingestion

#### 2.1 Base Reader

**File: `src/readers/base.py`**

```python
"""
Data Reader Abstract Base Class

Each reader implementation needs to:
1. Define form_id (Kingdee form ID)
2. Define field_keys (fields to query)
3. Define mto_field (MTO field name, varies by form)
4. Implement to_model() method (raw data -> Pydantic model)
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic
from datetime import date
from pydantic import BaseModel

from src.kingdee.client import KingdeeClient

T = TypeVar('T', bound=BaseModel)


class BaseReader(ABC, Generic[T]):
    """Data Reader Abstract Base Class"""

    def __init__(self, client: KingdeeClient):
        self.client = client

    @property
    @abstractmethod
    def form_id(self) -> str:
        """Kingdee form ID"""
        pass

    @property
    @abstractmethod
    def field_keys(self) -> list[str]:
        """Fields to query"""
        pass

    @property
    @abstractmethod
    def mto_field(self) -> str:
        """MTO field name (计划跟踪号 field)"""
        pass

    @property
    def date_field(self) -> str:
        """Date field name (for date range queries)"""
        return "FDate"  # Default, subclasses can override

    @abstractmethod
    def to_model(self, raw_data: dict) -> T:
        """Convert raw data to Pydantic model"""
        pass

    async def fetch_by_mto(self, mto_number: str) -> list[T]:
        """Query by MTO number and convert to models"""
        raw_records = await self.client.query_by_mto(
            form_id=self.form_id,
            field_keys=self.field_keys,
            mto_field=self.mto_field,
            mto_number=mto_number
        )
        return [self.to_model(r) for r in raw_records]

    async def fetch_by_date_range(
        self,
        start_date: date,
        end_date: date,
        extra_filter: str = ""
    ) -> list[T]:
        """Query by date range and convert to models"""
        raw_records = await self.client.query_by_date_range(
            form_id=self.form_id,
            field_keys=self.field_keys,
            date_field=self.date_field,
            start_date=start_date,
            end_date=end_date,
            extra_filter=extra_filter
        )
        return [self.to_model(r) for r in raw_records]

    async def fetch_by_bill_no(self, bill_no: str, bill_field: str = "FBillNo") -> list[T]:
        """Query by bill number"""
        raw_records = await self.client.query_all(
            form_id=self.form_id,
            field_keys=self.field_keys,
            filter_string=f"{bill_field}='{bill_no}'"
        )
        return [self.to_model(r) for r in raw_records]
```

#### 2.2 Readers to Implement

| Reader | Form ID | Key Fields | Purpose |
|--------|---------|------------|---------|
| ProductionOrderReader | PRD_MO | FBillNo, FMTONo, FMaterialId.*, FQty | Parent item info |
| ProductionBOMReader | PRD_PPBOM | FMOBillNO, FMaterialID.*, FMaterialType, FNeedQty, FPickedQty | Child items & type |
| ProductionReceiptReader | PRD_INSTOCK | FEntity_FMtoNo, FEntity_FRealQty | 自制品 receipts |
| PurchaseOrderReader | PUR_PurchaseOrder | FPOOrderEntry_FMtoNo, FQty, FStockInQty, FRemainStockInQty | 外购 order info |
| PurchaseReceiptReader | STK_InStock | FInStockEntry_FMtoNo, FInStockEntry_FRealQty, FBillTypeID | 外购/委外 receipts |
| SubcontractingOrderReader | SUB_POORDER | FTreeEntity_FMtoNo, FQty, FStockInQty, FNoStockInQty | 委外 order info |
| MaterialPickingReader | PRD_PickMtrl | FEntity_FMTONO, FAppQty, FActualQty | Actual picking |
| SalesDeliveryReader | SAL_OUTSTOCK | FSAL_OUTSTOCKENTRY_FMTONO, FRealQty | Sales delivery |
| SalesOrderReader | SAL_SaleOrder | FMtoNo, FCustomerID, FDeliveryDate | Customer info, delivery dates |

#### 2.3 Production Order Reader Example

**File: `src/readers/production_order.py`**

```python
"""
Production Order Reader (PRD_MO)

Kingdee Form: PRD_MO (生产订单)
Purpose: Get parent item info
"""

from decimal import Decimal
from typing import Optional
from pydantic import BaseModel

from src.readers.base import BaseReader


class ProductionOrderModel(BaseModel):
    """Production Order Model (Parent Item)"""
    bill_no: str              # FBillNo - 生产订单编号
    mto_number: str           # FMTONo - 计划跟踪号
    workshop: str             # FWorkShopID.FName - 生产车间
    material_code: str        # FMaterialId.FNumber - 物料编码
    material_name: str        # FMaterialId.FName - 物料名称
    specification: str        # FMaterialId.FSpecification - 规格型号
    aux_attributes: str       # FAuxPropId.FName - 辅助属性
    qty: Decimal              # FQty - 订单数量
    status: str               # FStatus - 单据状态
    create_date: Optional[str] = None  # FCreateDate


class ProductionOrderReader(BaseReader[ProductionOrderModel]):
    """Production Order Reader"""

    @property
    def form_id(self) -> str:
        return "PRD_MO"

    @property
    def field_keys(self) -> list[str]:
        return [
            "FBillNo",
            "FMTONo",
            "FWorkShopID.FName",
            "FMaterialId.FNumber",
            "FMaterialId.FName",
            "FMaterialId.FSpecification",
            "FAuxPropId.FName",
            "FQty",
            "FStatus",
            "FCreateDate"
        ]

    @property
    def mto_field(self) -> str:
        return "FMTONo"

    @property
    def date_field(self) -> str:
        return "FCreateDate"

    def to_model(self, raw_data: dict) -> ProductionOrderModel:
        """Raw data -> Model"""
        return ProductionOrderModel(
            bill_no=raw_data.get("FBillNo", ""),
            mto_number=raw_data.get("FMTONo", ""),
            workshop=raw_data.get("FWorkShopID.FName", ""),
            material_code=raw_data.get("FMaterialId.FNumber", ""),
            material_name=raw_data.get("FMaterialId.FName", ""),
            specification=raw_data.get("FMaterialId.FSpecification", ""),
            aux_attributes=raw_data.get("FAuxPropId.FName", ""),
            qty=Decimal(str(raw_data.get("FQty", 0))),
            status=raw_data.get("FStatus", ""),
            create_date=raw_data.get("FCreateDate")
        )
```

#### 2.4 Sync Service

**File: `src/sync/sync_service.py`**

```python
class SyncService:
    def __init__(
        self,
        readers: dict[str, BaseReader],
        db: Database,
        progress: SyncProgress
    ):
        self.readers = readers
        self.db = db
        self.progress = progress
        self._lock = asyncio.Lock()

    async def run_sync(
        self,
        days_back: int = 90,
        chunk_days: int = 7
    ) -> SyncResult:
        """Execute data sync"""
        async with self._lock:
            try:
                self.progress.start(days_back)

                # Calculate date range
                end_date = date.today()
                start_date = end_date - timedelta(days=days_back)

                # Process in chunks
                for chunk_start, chunk_end in self._generate_chunks(
                    start_date, end_date, chunk_days
                ):
                    await self._sync_chunk(chunk_start, chunk_end)

                self.progress.finish_success()
                return SyncResult(status="success", ...)

            except Exception as e:
                self.progress.finish_error(str(e))
                raise
```

---

### Phase 3: Query & API

#### 3.1 MTO Query Handler

**File: `src/query/mto_handler.py`**

```python
class MTOQueryHandler:
    """Handler for MTO number lookups."""

    async def get_status(self, mto_number: str) -> MTOStatusResponse:
        # 1. Get production order
        prod_orders = await self.prod_reader.fetch_by_mto(mto_number)

        # 2. Get BOM entries for each production order
        bom_entries = []
        for po in prod_orders:
            entries = await self.bom_reader.fetch_by_bill_no(po.bill_no)
            bom_entries.extend(entries)

        # 3. Get receipts (parallel by material type)
        prod_receipts, purch_receipts, sub_receipts, deliveries = await asyncio.gather(
            self.prod_receipt_reader.fetch_by_mto(mto_number),
            self.purch_receipt_reader.fetch_by_mto(mto_number),
            self.sub_receipt_reader.fetch_by_mto(mto_number),
            self.delivery_reader.fetch_by_mto(mto_number),
        )

        # 4. Aggregate and build response
        return self._build_response(
            prod_orders, bom_entries,
            prod_receipts, purch_receipts, sub_receipts, deliveries
        )
```

#### 3.2 API Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sync/trigger` | Manually trigger sync |
| GET | `/api/sync/status` | Get sync status |
| GET | `/api/sync/config` | Get sync configuration |
| PUT | `/api/sync/config` | Update sync configuration |
| GET | `/api/sync/history` | Get sync history |
| GET | `/api/mto/{mto_number}` | Query MTO status |
| GET | `/api/search?q={query}` | Search MTO numbers |
| GET | `/api/export/mto/{mto_number}` | Export to Excel |

#### 3.3 FastAPI Routes

**File: `src/api/routes.py`**

```python
@router.get("/api/mto/{mto_number}", response_model=MTOStatusResponse)
async def get_mto_status(mto_number: str) -> MTOStatusResponse:
    """Get complete MTO status by tracking number."""
    handler = MTOQueryHandler(...)
    return await handler.get_status(mto_number)

@router.get("/api/search")
async def search_mto(q: str = Query(..., min_length=2)) -> list[MTOSummary]:
    """Search for MTO numbers (autocomplete)."""
    # Search cached production orders
```

---

### Phase 4: Frontend (Industrial Precision Design)

> **Design Direction**: "Industrial Precision" - German industrial design meets modern enterprise. Dark theme, data-dense, optimized for manufacturing clerks.

#### 4.1 Design System

**Typography**:
- Display/Headers: `Geist` (Vercel's font) - geometric, modern
- Body/Chinese: `Noto Sans SC` - optimized CJK support
- Monospace: `Geist Mono` - material codes, quantities

**Color Palette**:
```css
/* Dark theme base */
--slate-950: #0a0a0b;      /* Primary dark - headers, nav */
--slate-900: #111113;      /* Card backgrounds */
--slate-800: #1e1e21;      /* Borders, dividers */
--slate-400: #9ca3af;      /* Secondary text */
--slate-50: #f8fafc;       /* Light text on dark */

/* Semantic colors */
--emerald-500: #10b981;    /* Success, 自制 badge */
--sky-500: #0ea5e9;        /* Info, 外购 badge */
--violet-500: #8b5cf6;     /* 委外 badge */
--amber-500: #f59e0b;      /* Warnings, pending */
--rose-500: #f43f5e;       /* Errors, 超领 highlighting */
```

**Visual Signature**:
- Dark mode default - easier on eyes for daily use
- Sharp corners (2-4px max radius) - industrial precision
- Hairline borders (1px slate-800) instead of shadows
- Accent glow effects on interactive elements
- Subtle dot pattern backgrounds for texture

#### 4.2 File Structure

```
src/frontend/
├── index.html              # Login page
├── dashboard.html          # MTO query + results
├── sync.html               # Sync admin panel
├── static/
│   ├── css/
│   │   └── main.css        # Design tokens + custom styles
│   ├── js/
│   │   ├── api.js          # Auth-aware fetch wrapper
│   │   ├── auth.js         # Login/logout logic
│   │   ├── dashboard.js    # MTO search component
│   │   └── sync.js         # Sync panel component
```

#### 4.3 Dashboard Table with Column Group Tinting

**13-Column Table with Visual Grouping**:

| Group | Columns | Background Tint |
|-------|---------|-----------------|
| Info | 序号, 物料编码, 物料名称, 规格型号, 物料类型 | `bg-slate-900` |
| BOM | 需求量, 已领量, 未领量 | `bg-emerald-950/30` |
| Receipt | 订单数量, 入库量, 未入库量 | `bg-sky-950/30` |
| Status | 销售出库, 即时库存 | `bg-violet-950/30` |

**Over-Picking Row Style**:
```css
.row-overpick {
  background: repeating-linear-gradient(
    -45deg,
    rgb(254 205 211 / 0.1) 0px,
    rgb(254 205 211 / 0.1) 4px,
    transparent 4px,
    transparent 8px
  );
  border-left: 3px solid var(--rose-500);
}
```

**Material Type Badges**:
```css
.badge-self-made {    /* 自制 */
  background: rgb(16 185 129 / 0.2);
  color: var(--emerald-400);
  border: 1px solid rgb(16 185 129 / 0.3);
}
.badge-purchased {    /* 外购 */
  background: rgb(14 165 233 / 0.2);
  color: var(--sky-400);
  border: 1px solid rgb(14 165 233 / 0.3);
}
.badge-subcontracted { /* 委外 */
  background: rgb(139 92 246 / 0.2);
  color: var(--violet-400);
  border: 1px solid rgb(139 92 246 / 0.3);
}
```

#### 4.4 Styling Notes

- **Rose highlight** for negative quantities (超领) with striped pattern
- **Emerald** for completed/success states
- **Amber** for pending/warning states
- **Focus glow**: `box-shadow: 0 0 0 2px var(--slate-950), 0 0 0 4px var(--emerald-500)`
- **Loading skeleton**: Animated gradient shimmer effect

#### 4.5 Mobile-Responsive Design

**Requirement**: Support screens from 320px (mobile) to 1920px+ (desktop).

**Breakpoints**:
- `< 768px` (mobile): Card layout for BOM items
- `768px - 1024px` (tablet): Simplified table with fewer columns
- `> 1024px` (desktop): Full 13-column table

**Mobile Card Layout** (`< 768px`):

```css
@media (max-width: 767px) {
  .bom-table { display: none; }
  .bom-cards { display: block; }

  .bom-card {
    background: var(--slate-900);
    border: 1px solid var(--slate-800);
    border-radius: 4px;
    padding: 1rem;
    margin-bottom: 0.75rem;
  }

  .bom-card-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
  }

  .touch-target {
    min-height: 44px;
    min-width: 44px;
  }
}
```

**Touch Target Requirements**:
- Minimum touch target size: 44x44px (WCAG 2.1 AAA)
- Buttons, links, and interactive elements must meet this requirement

#### 4.6 Accessibility Requirements (WCAG 2.1 AA)

**Target**: 100% WCAG 2.1 Level AA compliance

**Dark Theme Contrast Notes**:
- Slate-50 (#f8fafc) on Slate-950 (#0a0a0b) = 18.5:1 ratio ✓
- Slate-400 (#9ca3af) on Slate-950 = 8.1:1 ratio ✓
- All accent colors meet minimum 4.5:1 contrast

**Required Implementations**:

1. **ARIA Labels**:
```html
<button aria-label="搜索MTO单号" @click="search()">
    <span x-show="!loading">搜索</span>
    <span x-show="loading" class="sr-only">搜索中...</span>
</button>

<input type="text" id="mto-search"
       aria-label="计划跟踪号"
       aria-describedby="mto-help"
       x-model="mtoNumber">
<p id="mto-help" class="sr-only">输入MTO跟踪号进行搜索，例如 AK2510034</p>
```

2. **Keyboard Navigation**:
```javascript
setupKeyboardListeners() {
    document.addEventListener('keydown', (e) => {
        if (e.key === 'F11' && this.childItems.length > 0) {
            e.preventDefault();
            this.toggleFullScreen();
        }
        if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
            e.preventDefault();
            document.getElementById('mto-search')?.focus();
        }
    });
}
```

3. **Screen Reader Support**:
```html
<!-- Live region for dynamic updates -->
<div aria-live="polite" aria-atomic="true" class="sr-only"
     x-text="loading ? '正在加载...' : (error ? '发生错误: ' + error : (parentItem ? '已加载MTO单号 ' + mtoNumber + ' 的数据' : ''))">
</div>

<!-- Table accessibility -->
<table role="table">
    <thead>
        <tr role="row">
            <th scope="col" role="columnheader">物料编码</th>
            <th scope="col" role="columnheader">物料名称</th>
        </tr>
    </thead>
    <tbody role="rowgroup">
        <tr role="row"><td role="cell">...</td></tr>
    </tbody>
</table>
```

4. **Color-blind Safe Status Indicators**:
```html
<!-- Icons + text alongside colors -->
<span :class="isOverPicked(item.unpicked_qty) ? 'text-rose-400 font-bold' : 'text-slate-200'">
    <span x-text="formatNumber(item.unpicked_qty)"></span>
    <span x-show="isOverPicked(item.unpicked_qty)" class="text-xs ml-1 text-rose-500">(超领)</span>
</span>
```

5. **Reduced Motion Support**:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

**Accessibility Checklist**:
- [ ] All images have alt text
- [ ] All form inputs have labels
- [ ] Color contrast meets 4.5:1 ratio (dark theme verified)
- [ ] Keyboard navigation works (F11, ESC, / shortcuts)
- [ ] Focus indicators visible (emerald glow)
- [ ] ARIA landmarks defined (main, nav, header)
- [ ] Tables have proper scope/role attributes
- [ ] Dynamic content uses aria-live regions
- [ ] Skip links provided for keyboard users

---

## 6. Project Structure

```
Quickpulsev2/
├── pyproject.toml
├── conf.ini                      # Kingdee credentials
├── sync_config.json              # Sync configuration
├── src/
│   ├── __init__.py
│   ├── config.py                 # Config class
│   ├── exceptions.py             # Custom exceptions
│   ├── main.py                   # FastAPI app entry
│   │
│   ├── kingdee/
│   │   ├── __init__.py
│   │   └── client.py             # K3Cloud SDK wrapper
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── production_order.py
│   │   ├── production_bom.py
│   │   └── mto_status.py         # Combined response model
│   │
│   ├── readers/
│   │   ├── __init__.py
│   │   ├── base.py               # Abstract base
│   │   ├── production_order.py   # PRD_MO
│   │   ├── production_bom.py     # PRD_PPBOM
│   │   ├── production_receipt.py # PRD_INSTOCK
│   │   ├── sales_order.py        # SAL_SaleOrder
│   │   ├── purchase_order.py     # PUR_PurchaseOrder
│   │   ├── purchase_receipt.py   # STK_InStock
│   │   ├── subcontracting_order.py # SUB_POORDER
│   │   ├── material_picking.py   # PRD_PickMtrl
│   │   └── sales_delivery.py     # SAL_OUTSTOCK
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   └── schema.sql
│   │
│   ├── sync/
│   │   ├── __init__.py
│   │   ├── sync_service.py       # Sync logic
│   │   ├── scheduler.py          # Auto sync scheduler
│   │   └── progress.py           # Progress tracking
│   │
│   ├── query/
│   │   ├── __init__.py
│   │   └── mto_handler.py        # MTO lookup logic
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py             # FastAPI routes
│   │   └── routers/
│   │       ├── mto.py
│   │       └── sync.py
│   │
│   └── frontend/
│       ├── index.html            # Login page (dark theme)
│       ├── dashboard.html        # MTO query + results
│       ├── sync.html             # Sync admin panel
│       └── static/
│           ├── css/main.css      # Design tokens + custom styles
│           └── js/
│               ├── api.js        # Auth-aware fetch wrapper
│               ├── auth.js       # Login/logout logic
│               ├── dashboard.js  # MTO search component
│               └── sync.js       # Sync panel component
│
├── tests/
│   ├── __init__.py
│   ├── test_kingdee_client.py
│   └── test_mto_handler.py
│
├── data/                         # SQLite database (gitignored)
│   └── quickpulse.db
│
├── reports/                      # Sync status files
│   ├── sync_status.json
│   └── sync_history.json
│
├── docker/
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   └── nginx.conf
│
├── docs/                         # Documentation
│   ├── IMPLEMENTATION_PLAN.md
│   ├── API_FIELD_ANALYSIS.md
│   ├── api/
│   └── fields/
│
└── scripts/                      # Exploration scripts
    └── explore_*.py
```

---

## 7. Docker Deployment

### Dockerfile (Production)

```dockerfile
# docker/Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY src/ ./src/
COPY conf.ini ./
COPY sync_config.json ./

RUN mkdir -p /app/data /app/reports

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml (Production)

```yaml
version: '3.8'

services:
  quickpulse:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: quickpulse-v2
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./reports:/app/reports
      - ./sync_config.json:/app/sync_config.json
      - ./conf.ini:/app/conf.ini:ro
    environment:
      - TZ=Asia/Shanghai
      - PYTHONUNBUFFERED=1
    networks:
      - quickpulse-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  # Optional: Nginx reverse proxy
  nginx:
    image: nginx:alpine
    container_name: quickpulse-nginx
    restart: unless-stopped
    ports:
      - "80:80"
    volumes:
      - ./docker/nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - quickpulse
    networks:
      - quickpulse-network

networks:
  quickpulse-network:
    driver: bridge
```

### docker-compose.dev.yml (Development)

```yaml
version: '3.8'

services:
  quickpulse-dev:
    build:
      context: .
      dockerfile: docker/Dockerfile.dev
    container_name: quickpulse-v2-dev
    ports:
      - "8000:8000"
    volumes:
      - ./src:/app/src
      - ./data:/app/data
      - ./reports:/app/reports
      - ./sync_config.json:/app/sync_config.json
      - ./conf.ini:/app/conf.ini
    environment:
      - TZ=Asia/Shanghai
      - PYTHONUNBUFFERED=1
      - DEBUG=1
    command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker Commands

```bash
# Build and start (production)
docker-compose up -d --build

# Build and start (development)
docker-compose -f docker-compose.dev.yml up --build

# View logs
docker-compose logs -f quickpulse

# Stop services
docker-compose down

# Restart services
docker-compose restart quickpulse

# Enter container for debugging
docker exec -it quickpulse-v2 bash

# Manually trigger sync (inside container)
docker exec quickpulse-v2 curl -X POST http://localhost:8000/api/sync/trigger
```

### .dockerignore

```
.git
.gitignore
__pycache__
*.pyc
*.pyo
.pytest_cache
.mypy_cache
*.egg-info
.venv
venv
.idea
.vscode
*.swp
data/*.db
reports/*.json
reports/*.log
docs/
*.md
!README.md
tests/
```

---

## 8. API Query Patterns Reference

### Core Queries

```python
# Find Production Order by MTO (Parent Item)
{
    "FormId": "PRD_MO",
    "FieldKeys": "FBillNo,FMTONo,FMaterialId.FNumber,FMaterialId.FName,FQty,FWorkShopID.FName",
    "FilterString": "FMTONo='AK2510034'"
}

# Find BOM entries by Production Order (Child Items)
{
    "FormId": "PRD_PPBOM",
    "FieldKeys": "FPPBomEntry_FMaterialID.FNumber,FPPBomEntry_FMaterialID.FName,FPPBomEntry_FMaterialType,FPPBomEntry_FNeedQty,FPPBomEntry_FPickedQty,FPPBomEntry_FNoPickedQty",
    "FilterString": "FMOBillNO='MO251203242'"
}
```

### Receipt Queries by Material Type

```python
# 自制品: Production Receipts (PRD_INSTOCK)
{
    "FormId": "PRD_INSTOCK",
    "FieldKeys": "FEntity_FMaterialId.FNumber,FEntity_FRealQty,FEntity_FMustQty",
    "FilterString": "FEntity_FMtoNo='AK2510034'"
}

# 外购物料: Purchase Order Info (Order Qty, Received Qty)
{
    "FormId": "PUR_PurchaseOrder",
    "FieldKeys": "FBillNo,FPOOrderEntry_FMaterialId.FNumber,FPOOrderEntry_FQty,FPOOrderEntry_FStockInQty,FPOOrderEntry_FRemainStockInQty",
    "FilterString": "FPOOrderEntry_FMtoNo='AK2510034'"
}

# 外购物料: Purchase Receipts (STK_InStock - Standard Type)
{
    "FormId": "STK_InStock",
    "FieldKeys": "FInStockEntry_FMaterialId.FNumber,FInStockEntry_FRealQty,FInStockEntry_FMustQty",
    "FilterString": "FInStockEntry_FMtoNo='AK2510034' AND FBillTypeID.FNumber='RKD01_SYS'"
}

# 委外加工: Subcontracting Order Info
{
    "FormId": "SUB_POORDER",
    "FieldKeys": "FBillNo,FTreeEntity_FMaterialId.FNumber,FTreeEntity_FQty,FTreeEntity_FStockInQty,FTreeEntity_FNoStockInQty",
    "FilterString": "FTreeEntity_FMtoNo='AK2510034'"
}

# 委外加工: Subcontracting Receipts (STK_InStock - Subcontract Type)
{
    "FormId": "STK_InStock",
    "FieldKeys": "FInStockEntry_FMaterialId.FNumber,FInStockEntry_FRealQty,FInStockEntry_FMustQty",
    "FilterString": "FInStockEntry_FMtoNo='AK2510034' AND FBillTypeID.FNumber='RKD02_SYS'"
}
```

### Material Picking & Sales Queries

```python
# Material Picking (Actual Consumption)
{
    "FormId": "PRD_PickMtrl",
    "FieldKeys": "FEntity_FMaterialId.FNumber,FEntity_FAppQty,FEntity_FActualQty,FEntity_FPPBomBillNo",
    "FilterString": "FEntity_FMTONO='AK2510034'"
}

# Sales Deliveries
{
    "FormId": "SAL_OUTSTOCK",
    "FieldKeys": "FSAL_OUTSTOCKENTRY_FMaterialId.FNumber,FSAL_OUTSTOCKENTRY_FRealQty,FSAL_OUTSTOCKENTRY_FMustQty",
    "FilterString": "FSAL_OUTSTOCKENTRY_FMTONO='AK2510034'"
}
```

---

## 9. Verification Plan

### Phase 1 Complete When:
- [ ] `python -c "from src.config import Config; c = Config(); print(c.kingdee.server_url)"` works
- [ ] `python -c "from src.kingdee.client import KingdeeClient"` imports without error
- [ ] Kingdee client can execute test query against PRD_MO
- [ ] SQLite database created with correct schema

### Phase 2 Complete When:
- [ ] `ProductionOrderReader.fetch_by_mto("AK2510034")` returns data
- [ ] `ProductionBOMReader.fetch_by_bill_no("MO251203242")` returns BOM entries
- [ ] All 8 readers implemented and tested
- [ ] Data cached in SQLite after fetch

### Phase 3 Complete When:
- [ ] `GET /api/mto/AK2510034` returns complete `MTOStatusResponse`
- [ ] Response includes parent item with correct fields
- [ ] Response includes all child items with quantities
- [ ] Calculated fields (未入库数量, 未领数量) are correct
- [ ] Sync APIs work (trigger, status, config)

### Phase 4 Complete When:
- [ ] Web UI loads at `http://localhost:8000`
- [ ] Search by MTO number displays parent info
- [ ] BOM table shows all child items
- [ ] Negative quantities highlighted in red
- [ ] Sync control panel works
- [ ] Export to Excel works
- [ ] Docker deployment works

---

## 10. Notes & Key Reminders

1. **超领 Detection**: When `未领数量` (FNoPickedQty) is negative, it means materials were over-picked - highlight in red

2. **Material Type Determines Receipt Source**:
   - `FMaterialType = 1` (自制件) → Query PRD_INSTOCK
   - `FMaterialType = 2` (外购件) → Query STK_InStock with FBillTypeID='RKD01_SYS'
   - `FMaterialType = 3` (委外件) → Query STK_InStock with FBillTypeID='RKD02_SYS'

3. **入库数量 Sources**:
   - 自制品: PRD_INSTOCK `FEntity_FRealQty`
   - 外购物料: STK_InStock `FInStockEntry_FRealQty` (标准采购入库)
   - 委外加工: STK_InStock `FInStockEntry_FRealQty` (委外入库单)

4. **Order Quantity Sources**:
   - 外购物料: PUR_PurchaseOrder `FPOOrderEntry_FQty`
   - 委外加工: SUB_POORDER `FTreeEntity_FQty`
   - Shows: 累计入库数量, 剩余入库数量 for tracking

5. **Parallel Fetching**: Use `asyncio.gather()` for independent API calls by material type

6. **Caching Strategy**: Cache by MTO number with timestamp, refresh on demand

7. **Field Mapping Reference**: Use `docs/API_FIELD_ANALYSIS.md` for complete field documentation

8. **STK_InStock Document Types**:
   - `RKD01_SYS` = 标准采购入库单 (Standard Purchase Receipt)
   - `RKD02_SYS` = 委外入库单 (Subcontracting Receipt)

9. **Confirmed Settings**:
   | Setting | Value | Notes |
   |---------|-------|-------|
   | Auto sync schedule | 07:00, 12:00, 16:00, 18:00 | 4 times daily |
   | Default sync days | 90 days | Covers last 3 months |
   | Config storage | JSON file | sync_config.json, supports hot reload |
   | Frontend framework | Alpine.js | Consistent with existing frontend |

---

## 11. Implementation Status (Updated 2026-01-18)

### Phase 1: Foundation ✅ COMPLETE

| Component | File(s) | Status |
|-----------|---------|--------|
| Project Setup | `pyproject.toml` | ✅ Complete |
| Package Init | `src/__init__.py` | ✅ Complete |
| Exceptions | `src/exceptions.py` | ✅ Complete |
| Configuration | `src/config.py` | ✅ Complete |
| Kingdee Client | `src/kingdee/client.py` | ✅ Complete |
| Database Connection | `src/database/connection.py` | ✅ Complete |
| Database Schema | `src/database/schema.sql` | ✅ Complete |
| Sync Config | `sync_config.json` | ✅ Complete |
| Pydantic Models | `src/models/mto_status.py`, `src/models/sync.py` | ✅ Complete |
| Logging | `src/logging_config.py` | ✅ Complete |

### Phase 2: Data Readers ✅ COMPLETE

| Reader | Form ID | Status | Notes |
|--------|---------|--------|-------|
| ProductionOrderReader | PRD_MO | ✅ Complete | Via factory pattern |
| ProductionBOMReader | PRD_PPBOM | ✅ Complete | Via factory pattern |
| ProductionReceiptReader | PRD_INSTOCK | ✅ Complete | Via factory pattern |
| PurchaseOrderReader | PUR_PurchaseOrder | ✅ Complete | Via factory pattern |
| PurchaseReceiptReader | STK_InStock | ✅ Complete | Via factory pattern |
| SubcontractingOrderReader | SUB_POORDER | ✅ Complete | Via factory pattern |
| MaterialPickingReader | PRD_PickMtrl | ✅ Complete | Via factory pattern |
| SalesDeliveryReader | SAL_OUTSTOCK | ✅ Complete | Via factory pattern |
| SalesOrderReader | SAL_SaleOrder | ✅ Complete | Via factory pattern |

**Implementation Note**: Instead of 9 separate reader files, readers were consolidated into:
- `src/readers/factory.py` - Generic reader class with declarative configuration
- `src/readers/models.py` - Pydantic models for each reader

### Phase 3: Sync & API ✅ COMPLETE

| Component | File(s) | Status |
|-----------|---------|--------|
| Sync Service | `src/sync/sync_service.py` | ✅ Complete |
| Sync Scheduler | `src/sync/scheduler.py` | ✅ Complete |
| Sync Progress | `src/sync/progress.py` | ✅ Complete |
| MTO Handler | `src/query/mto_handler.py` | ✅ Complete |
| MTO API Routes | `src/api/routers/mto.py` | ✅ Complete |
| Sync API Routes | `src/api/routers/sync.py` | ✅ Complete |
| Auth Routes | `src/api/routers/auth.py` | ✅ Complete |
| Rate Limiting | `src/api/middleware/rate_limit.py` | ✅ Complete |
| Main App | `src/main.py` | ✅ Complete |

### Phase 4: Frontend & Docker ✅ COMPLETE

| Component | File(s) | Status |
|-----------|---------|--------|
| Login Page | `src/frontend/index.html` | ✅ Complete |
| Dashboard | `src/frontend/dashboard.html` | ✅ Complete |
| Sync Panel | `src/frontend/sync.html` | ✅ Complete |
| Static Assets | `src/frontend/static/` | ✅ Complete |
| Docker Prod | `docker/Dockerfile` | ✅ Complete |
| Docker Dev | `docker/Dockerfile.dev` | ✅ Complete |
| Docker Compose | `docker-compose.yml` | ✅ Complete |
| Docker Dev Compose | `docker-compose.dev.yml` | ✅ Complete |

### Verification Checklist

#### Phase 1 ✅
- [x] `python -c "from src.config import Config"` imports without error
- [x] `python -c "from src.kingdee.client import KingdeeClient"` imports without error
- [x] Database schema includes all required tables

#### Phase 2 ✅
- [x] All 9 readers implemented via factory pattern
- [x] Readers support `fetch_by_mto()`, `fetch_by_date_range()`, `fetch_by_bill_no()` methods

#### Phase 3 ✅
- [x] `GET /api/mto/{mto_number}` returns `MTOStatusResponse`
- [x] `POST /api/sync/trigger` triggers background sync
- [x] `GET /api/sync/status` returns current sync status
- [x] JWT authentication implemented
- [x] Rate limiting enabled (30 req/min for MTO, 60 req/min for search)

#### Phase 4 ✅
- [x] Frontend pages created (login, dashboard, sync)
- [x] Docker production build configured
- [x] Docker development build with hot reload
- [x] Health check endpoint `/health` available

### Architecture Improvements Made

1. **Factory Pattern for Readers**: Consolidated 9 reader files into a single `factory.py` with declarative `ReaderConfig` definitions
2. **Lifespan Dependency Injection**: All services initialized via FastAPI's `lifespan` context manager
3. **Type-safe Generic Reader**: `GenericReader[T]` provides full type inference for each reader
4. **Parallel Receipt Fetching**: `asyncio.gather()` used in `MTOQueryHandler` for concurrent API calls

### Remaining Work (Optional Enhancements)

- [ ] Add comprehensive test suite (`tests/`)
- [ ] Implement real-time inventory lookup (F_QWJI_JSKC field)
- [ ] Add Excel export with openpyxl (current uses CSV with .xlsx extension)
- [x] Production Nginx reverse proxy configuration ✅ (ops-nginx on CVM)
- [x] CI/CD pipeline setup ✅ (`.github/workflows/cd.yml` — SSH-based deploy)

### CVM Deployment ✅ COMPLETE (2026-02-11)

Deployed to shared Aliyun CVM at `121.41.81.36`:
- **Prod**: `https://fltpulse.szfluent.cn` → `quickpulse-prod` (128 MB, `main` branch)
- **Dev**: `https://dev.fltpulse.szfluent.cn` → `quickpulse-dev` (96 MB, `develop` branch)
- **SSL**: Let's Encrypt (auto-renewal via certbot, expires 2026-05-12)
- **CI/CD**: Push to `develop` auto-deploys dev; manual dispatch for prod
- **Infrastructure**: See `docs/CVM_INFRASTRUCTURE.md` for full details

### Bug Fixes In Progress

See `docs/BUGFIX_PLAN.md` for current status of:
- JWT token expiration (30min → 24hr)
- SQLite ON CONFLICT constraint errors
- Subcontracting order form ID fix
