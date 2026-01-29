# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QuickPulse V2 is a web dashboard that displays **产品状态明细表** (Product Status Detail Sheet) by querying **计划跟踪号** (MTO Number). It integrates with Kingdee K3Cloud ERP via their Python SDK.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLite (WAL mode), aiosqlite
- **Frontend**: Alpine.js, Tailwind CSS (CDN)
- **External**: Kingdee K3Cloud WebAPI SDK (`kingdee.cdp.webapi.sdk`)
- **Deployment**: Docker Compose, Uvicorn

## Architecture

### Two-Layer Data Architecture
```
Layer 1 (Cache)     → SQLite snapshot cache    → <100ms queries
Layer 2 (Real-time) → Direct Kingdee API calls → 1-5s queries
```

### MTO Query Data Flow
```
User Input: MTO Number (e.g., AK2510034)
    │
    ▼
PRD_MO (生产订单) → Get parent item info + FBillNo
    │
    ▼ Link via FMOBillNO
PRD_PPBOM (生产用料清单) → Get child items + FMaterialType
    │
    ▼ Parallel queries by material type:
    ├─ FMaterialType=1 (自制) → PRD_INSTOCK receipts
    ├─ FMaterialType=2 (外购) → STK_InStock (RKD01_SYS)
    └─ FMaterialType=3 (委外) → STK_InStock (RKD02_SYS)
    │
    ▼
Aggregate and return MTOStatusResponse
```

### Key Material Type Logic
- `FMaterialType=1` (自制件): Query `PRD_INSTOCK` for receipts
- `FMaterialType=2` (外购件): Query `STK_InStock` with `FBillTypeID.FNumber='RKD01_SYS'`
- `FMaterialType=3` (委外件): Query `STK_InStock` with `FBillTypeID.FNumber='RKD02_SYS'`

## Commands

### Development
```bash
# Install dependencies
pip install -e .

# Run development server
uvicorn src.main:app --reload --port 8000

# Run with Docker (development)
docker-compose -f docker-compose.dev.yml up --build
```

### Production
```bash
# Docker production build
docker-compose up -d --build

# Check health
curl http://localhost:8000/health
```

### Testing
```bash
# Run all tests
pytest

# Run single test file
pytest tests/test_kingdee_client.py -v

# Run with coverage
pytest --cov=src
```

### Kingdee SDK Exploration
```bash
# Explore API fields (requires KINGDEE_* env vars or .env file)
python scripts/explore_all_api_fields.py
```

## Kingdee K3Cloud SDK Usage

The SDK is initialized from environment variables (preferred) or `.env` file:
```python
# Credentials loaded automatically from environment
from src.config import KingdeeConfig
config = KingdeeConfig.load()

# Or manually via SDK (for scripts)
from k3cloud_webapi_sdk.main import K3CloudApiSdk
import os

api_sdk = K3CloudApiSdk(os.environ["KINGDEE_SERVER_URL"])
api_sdk.InitConfig(
    acct_id=os.environ["KINGDEE_ACCT_ID"],
    user_name=os.environ["KINGDEE_USER_NAME"],
    app_id=os.environ["KINGDEE_APP_ID"],
    app_sec=os.environ["KINGDEE_APP_SEC"],
    server_url=os.environ["KINGDEE_SERVER_URL"],
    lcid=int(os.environ.get("KINGDEE_LCID", 2052)),
)

# Execute query
params = {
    "FormId": "PRD_MO",
    "FieldKeys": "FBillNo,FMTONo,FMaterialId.FNumber",
    "FilterString": "FMTONo='AK2510034'",
    "Limit": 100
}
result = api_sdk.ExecuteBillQuery(params)
```

## Key Kingdee Form IDs

| Form ID | Chinese Name | Purpose |
|---------|-------------|---------|
| PRD_MO | 生产订单 | Parent item (production order) |
| PRD_PPBOM | 生产用料清单 | BOM components with material type |
| PRD_INSTOCK | 生产入库单 | Self-made item receipts |
| PUR_PurchaseOrder | 采购订单 | Purchase order quantities |
| STK_InStock | 采购入库单 | Purchase/subcontracting receipts |
| SUB_POORDER | 委外订单 | Subcontracting order quantities |
| PRD_PickMtrl | 生产领料单 | Material picking |
| SAL_OUTSTOCK | 销售出库单 | Sales deliveries |

## Project Structure (Target)

```
src/
├── config.py           # Single config class (from conf.ini + sync_config.json)
├── exceptions.py       # Custom exception hierarchy
├── main.py             # FastAPI app entry
├── kingdee/
│   └── client.py       # Async wrapper around K3Cloud SDK
├── readers/            # One reader per Kingdee form
│   ├── base.py         # Abstract BaseReader
│   ├── production_order.py    # PRD_MO
│   ├── production_bom.py      # PRD_PPBOM
│   └── ...
├── database/
│   ├── connection.py   # aiosqlite connection
│   └── schema.sql      # Cache tables with indexes
├── sync/
│   ├── sync_service.py # Orchestrates data sync
│   └── scheduler.py    # Auto-sync at 07:00, 12:00, 16:00, 18:00
├── query/
│   └── mto_handler.py  # MTO lookup logic with parallel fetches
├── api/routers/
│   ├── mto.py          # GET /api/mto/{mto_number}
│   └── sync.py         # POST /api/sync/trigger, GET /api/sync/status
└── frontend/           # Static HTML/JS served by FastAPI
```

## Configuration Files

### Credentials (Priority Order)
1. **Environment variables** (preferred): `KINGDEE_*` variables
2. **`.env` file**: Copy from `.env.example` (gitignored)
3. **`conf.ini`**: Legacy fallback (gitignored, not recommended)

### Environment Variables
```bash
KINGDEE_SERVER_URL=http://your-server.com:8200/k3cloud/
KINGDEE_ACCT_ID=your_account_id
KINGDEE_USER_NAME=your_username
KINGDEE_APP_ID=your_app_id
KINGDEE_APP_SEC=your_app_secret
KINGDEE_LCID=2052
```

### Other Config Files
- `.env.example`: Template for credentials (committed)
- `sync_config.json`: Sync schedule and performance settings
- `.gitignore`: Excludes `.env`, `conf.ini`, `data/*.json`, `*.log`

## API Field Documentation

Detailed field mappings are in `docs/fields/` and `docs/api/`:
- `PRD_MO_FIELDS.md` - Production order fields
- `PRD_PPBOM_FIELDS.md` - BOM component fields
- `STK_InStock_FIELDS.md` - Instock receipt fields

## Important Implementation Notes

1. **超领 Detection**: Negative `FNoPickedQty` means over-picking - highlight in red
2. **Async SDK Calls**: Use `asyncio.Lock()` and `run_in_executor()` since SDK is synchronous
3. **Parallel Fetching**: Use `asyncio.gather()` for independent receipt queries by material type
4. **SQLite WAL Mode**: Enable for better concurrent read/write performance
5. **Chunk Sync**: Process date ranges in 7-day chunks to avoid memory issues

---

## Planning Practices

### Two-Tier Planning System

| Plan Type | Location | Purpose | Lifecycle |
|-----------|----------|---------|-----------|
| **Temporary Plans** | `/tmp/` | Quick fixes, debugging, one-off tasks | Ephemeral, deleted after completion |
| **Project Plans** | `docs/` | Feature roadmaps, architectural decisions | Persistent, version controlled |

### Temporary Plans (`/tmp/`)

Use `/tmp/` for:
- Bug fix plans that don't need history
- Exploration/investigation notes
- Quick implementation sketches
- Debugging session notes

**Naming convention**: `/tmp/PLAN_<task>_<date>.md`
```
/tmp/PLAN_fix_api_timeout_20260129.md
/tmp/PLAN_debug_mto_query_20260129.md
```

### Project Plans (`docs/`)

Use `docs/` for plans that:
- Affect multiple components
- Represent architectural decisions
- Need team visibility or review
- Should be referenced later

**Update existing project plans regularly**:
- `docs/IMPLEMENTATION_PLAN.md` - Current sprint/milestone work
- `docs/*_PLAN.md` - Feature-specific planning docs

**When to promote `/tmp/` to `docs/`**:
- Task scope expanded beyond original estimate
- Decisions made that affect future work
- Documentation value for similar future tasks

### Plan Mode Workflow

```
1. Quick fix/debug → Create plan in /tmp/
2. Complex feature → Create/update plan in docs/
3. After completion:
   - /tmp/ plans: Delete or let expire
   - docs/ plans: Update status, archive if complete
```

### Commit Checkpoints

After every commit, Claude should:

1. **Check alignment** - Compare commit with active plans:
   - Does it complete tasks from `/tmp/` fix plans?
   - Does it advance items in `docs/*_PLAN.md`?

2. **Update documentation**:
   - Mark completed items in the relevant plan
   - If temp plan fully done → delete or archive
   - Update `docs/IMPLEMENTATION_PLAN.md` status section

3. **Trigger promotion** if needed:
   - Temp plan scope grew → promote to `docs/`
   - Plan completed → move to `docs/archive/`

### Plan File Requirements

Every `.md` plan must include:

1. **Design Specs Section**:
   - Problem statement
   - Proposed solution with architecture/approach
   - Files to modify
   - Data flow or sequence (if applicable)

2. **Test Cases Section**:
   - Unit test scenarios matching the use case
   - Integration test scenarios (if applicable)
   - Manual verification steps

3. **Acceptance Criteria**:
   - What defines "done"
   - Expected behavior/output

**Plan Template:**
```markdown
# Plan: [Feature/Fix Name]

## Status: [Not Started | In Progress | Complete]

## Design Spec
### Problem
### Solution
### Files to Modify

## Test Cases
### Unit Tests
- [ ] Test case 1: ...
- [ ] Test case 2: ...

### Integration Tests
- [ ] ...

### Manual Verification
1. Step 1...
2. Step 2...

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
```

---

## MTO 查询修改指南

> 详细文档见 `docs/QUICKPULSE_MODIFICATION_GUIDE.md`

### 关键文件
| 文件 | 作用 | 修改频率 |
|-----|------|---------|
| `config/mto_config.json` | 物料类型路由 + 列计算配置 | ⭐ 高 |
| `src/readers/factory.py` | 金蝶字段映射 (Python) | ⭐⭐ 中 |
| `src/readers/models.py` | Pydantic 数据模型 | ⭐⭐ 中 |
| `src/query/mto_handler.py` | 数据聚合逻辑 | ⭐⭐⭐ 低 |
| `src/frontend/dashboard.html` | UI 表格显示 | ⭐⭐ 中 |

### 物料类型路由
| 物料编码前缀 | 类型 | 源单 | MTO 字段 |
|-------------|------|------|----------|
| `07.xx.xxx` | 成品 | `SAL_SaleOrder` | `FMtoNo` |
| `05.xx.xxx` | 自制 | `PRD_MO` | `FMTONo` |
| `03.xx.xxx` | 外购 | `PUR_PurchaseOrder` | `FMtoNo` |

### MTO 字段名速查 (大小写敏感!)
| 表单 | MTO 字段名 |
|-----|-----------|
| SAL_SaleOrder | `FMtoNo` |
| PRD_MO | `FMTONo` |
| PUR_PurchaseOrder | `FMtoNo` |
| PRD_INSTOCK | `FMtoNo` |
| STK_InStock | `FMtoNo` |
| PRD_PickMtrl | `FMTONO` |
| SAL_OUTSTOCK | `FMTONO` |
| PRD_PPBOM | `FMTONO` |

### 数量字段速查
| 用途 | 字段名 | 表单 |
|-----|-------|------|
| 需求/订单数量 | `FQty` | 几乎所有源单 |
| 实收/实发数量 | `FRealQty` | 入库单/出库单 |
| 应收/应发数量 | `FMustQty` | 入库单/出库单 |
| 申请领料数量 | `FAppQty` | PRD_PickMtrl |
| 实际领料数量 | `FActualQty` | PRD_PickMtrl |
| 累计入库数量 | `FStockInQty` | PUR_PurchaseOrder |
| 未入库数量 | `FRemainStockInQty` | PUR_PurchaseOrder |

### 修改步骤 (添加新字段)
1. `factory.py` - 添加 FieldMapping
2. `models.py` - 添加 Pydantic 字段
3. `mto_handler.py` - 传递到 ChildItem
4. `dashboard.html` - 添加 UI 列

---

## Deployment Preferences

### Credential Management

**NEVER commit credentials to git.** Use environment variables instead.

**Local development**:
```bash
# Copy template and fill in credentials
cp .env.example .env
# Edit .env with your credentials
```

**CVM/Production** (use env-file approach):
```bash
# Create credential file on CVM (one-time setup)
cat > /home/ubuntu/.quickpulse.env << 'EOF'
KINGDEE_SERVER_URL=http://flt.hotker.com:8200/k3cloud/
KINGDEE_ACCT_ID=696f1cca847085
KINGDEE_USER_NAME=张增辉
KINGDEE_APP_ID=334941_QY7BWcsOTNoX1X+FS0RNSzxF2I16RBMJ
KINGDEE_APP_SEC=b3ab5bd2958b4563a86fd80f6e68c872
KINGDEE_LCID=2052
EOF
chmod 600 /home/ubuntu/.quickpulse.env
```

**IMPORTANT**: Credentials are NOT baked into Docker images. The app will fail to start with a clear error if KINGDEE_* env vars are missing.

### CVM Deployment

**Server**: `ubuntu@175.27.161.234`
**Project Path**: `/home/ubuntu/Quickpulsev2`
**Container**: `quickpulse-v2`
**Port**: `8000`
**SSH Password**: `+Vb~W^{zB4|*8`

### Auto-Deploy After Push

**IMPORTANT**: After every `git push` to main, Claude should automatically:

1. SSH into CVM: `sshpass -p '+Vb~W^{zB4|*8' ssh ubuntu@175.27.161.234`
2. Run `git pull origin main`
3. Determine if Docker rebuild/restart is needed based on changed files:

| Files Changed | Action Required |
|---------------|-----------------|
| `Dockerfile*`, `pyproject.toml`, `requirements*.txt` | **Full rebuild**: `docker build` + `docker stop/rm/run` |
| `src/**/*.py`, `config/*.json`, `src/frontend/**` | **Restart only**: `docker restart quickpulse-v2` |
| `docs/**`, `.gitignore`, `*.md`, `tests/**` | **No action**: Documentation/tests only |

**Full Redeployment**:
```bash
ssh ubuntu@175.27.161.234
cd /home/ubuntu/Quickpulsev2
git pull origin main
docker build -t dev-quickpulse:latest -f docker/Dockerfile.dev .
docker stop quickpulse-v2 && docker rm quickpulse-v2

docker run -d \
  --name quickpulse-v2 \
  --restart unless-stopped \
  -p 8000:8000 \
  --env-file /home/ubuntu/.quickpulse.env \
  -v /home/ubuntu/quickpulse-data:/app/data \
  -v /home/ubuntu/quickpulse-reports:/app/reports \
  -v /home/ubuntu/quickpulse-config:/app/config:ro \
  -v /home/ubuntu/sync_config.json:/app/sync_config.json:ro \
  --health-cmd="curl -f http://localhost:8000/health || exit 1" \
  --health-interval=30s \
  dev-quickpulse:latest
```

**Quick Code Update** (no dependency changes):
```bash
ssh ubuntu@175.27.161.234
cd /home/ubuntu/Quickpulsev2
git pull origin main
docker build -t dev-quickpulse:latest -f docker/Dockerfile.dev .
docker restart quickpulse-v2
```

**View Logs**:
```bash
docker logs quickpulse-v2 --tail 50
docker logs quickpulse-v2 -f  # follow
```

**Volume Mounts**:
| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `/home/ubuntu/quickpulse-data` | `/app/data` | SQLite DB |
| `/home/ubuntu/quickpulse-reports` | `/app/reports` | Reports |
| `/home/ubuntu/quickpulse-config` | `/app/config` | MTO config |
| `/home/ubuntu/sync_config.json` | `/app/sync_config.json` | Sync settings |
