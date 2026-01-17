# QuickPulse V2 实施计划 (中文版)

## 项目概述

构建一个 Web 仪表板，当搜索 **计划跟踪号** (MTO Number) 时显示 **产品状态明细表**。

---

## 并行开发终端配置

### 推荐: 4个并行终端

基于模块化架构，可以使用 **4个并行终端** 同时开发：

| 终端 | 负责模块 | 依赖关系 | 预估工作量 |
|------|----------|----------|-----------|
| **终端 1** | 基础层 (config, database, kingdee client) | 无依赖 (优先完成) | 高 |
| **终端 2** | 数据读取器 (8个 Readers) | 依赖终端1的 KingdeeClient | 高 |
| **终端 3** | 同步服务 + API 路由 | 依赖终端1+2 | 中 |
| **终端 4** | 前端开发 | 可与后端并行 | 中 |

### 开发顺序建议

```
时间线:
──────────────────────────────────────────────────────────────────>

终端1: [Config] → [Database] → [KingdeeClient] → [完成后支援其他终端]
终端2:            [等待Client] → [Readers开发: PRD_MO → PRD_PPBOM → ...]
终端3:                          [等待Readers] → [SyncService] → [API]
终端4: [HTML结构] → [Alpine组件] → [同步功能UI] → [测试集成]
```

---

## 数据同步架构 (与 Legacy 一致)

### 两层数据架构

```
第一层 (缓存层)    → SQLite 缓存快照    → <100ms 查询
第二层 (实时层)    → 直接 API 调用      → 1-5s 查询
```

### 同步配置结构

**文件: `sync_config.json`**

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

---

## 同步功能详细设计

### 1. 手动同步 (Manual Sync)

**API 端点: `POST /api/sync/trigger`**

```python
class SyncTriggerRequest(BaseModel):
    days_back: int = Field(90, ge=1, le=365, description="同步天数")
    chunk_days: Optional[int] = Field(7, ge=1, le=30, description="分块天数")
    force_full: bool = Field(False, description="强制全量刷新")

@router.post("/sync/trigger")
async def trigger_sync(
    request: SyncTriggerRequest,
    background_tasks: BackgroundTasks
) -> dict:
    """手动触发同步任务"""
    # 检查是否有正在运行的同步
    if sync_service.is_running():
        raise HTTPException(409, "同步任务已在运行中")

    # 后台执行同步
    background_tasks.add_task(
        sync_service.run_sync,
        days_back=request.days_back,
        chunk_days=request.chunk_days
    )
    return {"status": "sync_started", "days_back": request.days_back}
```

### 2. 自动同步 (Auto Sync)

**文件: `src/sync/scheduler.py`**

```python
class SyncScheduler:
    def __init__(self, config: SyncConfig, sync_service: SyncService):
        self.config = config
        self.sync_service = sync_service
        self._scheduler = None

    def start(self):
        """启动自动同步调度器"""
        if not self.config.auto_sync.enabled:
            logger.info("自动同步已禁用")
            return

        for time_str in self.config.auto_sync.schedule:
            schedule.every().day.at(time_str).do(self._sync_job)

        self._scheduler = threading.Thread(target=self._run_scheduler, daemon=True)
        self._scheduler.start()
        logger.info(f"自动同步已启动: {self.config.auto_sync.schedule}")

    def _sync_job(self):
        """执行同步任务"""
        # 重新加载配置 (支持运行时修改天数)
        self.config.reload()
        days_back = self.config.auto_sync.days_back
        self.sync_service.run_sync(days_back=days_back)
```

### 3. 同步天数配置 (Days to Sync)

**API 端点: `GET/PUT /api/sync/config`**

```python
@router.get("/sync/config")
async def get_sync_config() -> SyncConfigResponse:
    """获取当前同步配置"""
    return SyncConfigResponse(
        auto_sync_enabled=config.auto_sync.enabled,
        auto_sync_schedule=config.auto_sync.schedule,
        auto_sync_days=config.auto_sync.days_back,
        manual_sync_default_days=config.manual_sync.default_days
    )

@router.put("/sync/config")
async def update_sync_config(request: SyncConfigUpdateRequest):
    """更新同步配置"""
    if request.auto_sync_days:
        if not (1 <= request.auto_sync_days <= 365):
            raise HTTPException(400, "同步天数必须在 1-365 之间")
        config.auto_sync.days_back = request.auto_sync_days

    if request.auto_sync_enabled is not None:
        config.auto_sync.enabled = request.auto_sync_enabled

    config.save()
    return {"status": "config_updated"}
```

### 4. 同步进度追踪

**状态文件: `reports/sync_status.json`**

```json
{
  "status": "running",
  "phase": "read",
  "message": "正在读取生产订单...",
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

## 核心模块设计

### 1. 配置模块 (`src/config.py`)

```python
class Config(BaseSettings):
    # Kingdee API 配置
    kingdee_server_url: str
    kingdee_acct_id: str
    kingdee_user_name: str
    kingdee_app_id: str
    kingdee_app_sec: str

    # 数据库配置
    db_path: str = "data/quickpulse.db"

    # 同步配置
    sync_config_path: str = "sync_config.json"

    class Config:
        env_file = ".env"
```

### 2. Kingdee 客户端 (`src/kingdee/client.py`)

```python
class KingdeeClient:
    """K3Cloud SDK 封装"""

    async def query(
        self,
        form_id: str,
        field_keys: list[str],
        filter_string: str,
        limit: int = 2000
    ) -> list[dict]:
        """执行 Query API 调用"""

    async def query_by_date_range(
        self,
        form_id: str,
        field_keys: list[str],
        date_field: str,
        start_date: date,
        end_date: date
    ) -> list[dict]:
        """按日期范围查询"""
```

### 3. 数据读取器 (`src/readers/`)

| 读取器 | Form ID | 用途 |
|--------|---------|------|
| ProductionOrderReader | PRD_MO | 父项信息 (生产订单) |
| ProductionBOMReader | PRD_PPBOM | 子项列表 (物料清单) |
| ProductionReceiptReader | PRD_INSTOCK | 自制品入库 |
| PurchaseOrderReader | PUR_PurchaseOrder | 外购订单信息 |
| PurchaseReceiptReader | STK_InStock | 外购/委外入库 |
| SubcontractingOrderReader | SUB_POORDER | 委外订单信息 |
| MaterialPickingReader | PRD_PickMtrl | 领料记录 |
| SalesDeliveryReader | SAL_OUTSTOCK | 销售出库 |

### 4. 同步服务 (`src/sync/sync_service.py`)

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
        """执行数据同步"""
        async with self._lock:
            try:
                self.progress.start(days_back)

                # 计算日期范围
                end_date = date.today()
                start_date = end_date - timedelta(days=days_back)

                # 分块处理
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

## 数据库表结构

### 缓存表

```sql
-- 生产订单缓存
CREATE TABLE cached_production_orders (
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
CREATE INDEX idx_po_mto ON cached_production_orders(mto_number);
CREATE INDEX idx_po_synced ON cached_production_orders(synced_at);

-- 生产BOM缓存
CREATE TABLE cached_production_bom (
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
CREATE INDEX idx_bom_mo ON cached_production_bom(mo_bill_no);

-- 同步历史
CREATE TABLE sync_history (
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

## 前端同步控制界面

### 同步控制面板 (Alpine.js)

```html
<!-- 同步控制面板 -->
<div x-data="syncControl()" class="bg-white rounded-lg shadow p-4">
    <h3 class="text-lg font-semibold mb-4">数据同步</h3>

    <!-- 同步状态 -->
    <div class="mb-4">
        <span class="text-sm text-gray-500">状态:</span>
        <span :class="statusClass" x-text="status"></span>
    </div>

    <!-- 手动同步 -->
    <div class="mb-4">
        <label class="block text-sm text-gray-700 mb-2">同步天数</label>
        <input type="number" x-model="daysToSync" min="1" max="365"
               class="border rounded px-3 py-2 w-24">
        <button @click="triggerSync()" :disabled="isRunning"
                class="ml-2 bg-blue-500 text-white px-4 py-2 rounded">
            手动同步
        </button>
    </div>

    <!-- 自动同步设置 -->
    <div class="mb-4">
        <label class="flex items-center">
            <input type="checkbox" x-model="autoSyncEnabled">
            <span class="ml-2 text-sm">启用自动同步</span>
        </label>
        <div x-show="autoSyncEnabled" class="mt-2 ml-6">
            <span class="text-sm text-gray-500">
                每天 07:00, 12:00, 16:00, 18:00 自动同步 (共4次)
            </span>
        </div>
    </div>

    <!-- 进度条 -->
    <div x-show="isRunning" class="mt-4">
        <div class="text-sm text-gray-600 mb-1" x-text="progressMessage"></div>
        <div class="w-full bg-gray-200 rounded-full h-2">
            <div class="bg-blue-500 h-2 rounded-full"
                 :style="{ width: progressPercent + '%' }"></div>
        </div>
    </div>
</div>
```

---

## API 端点汇总

### 同步相关

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/api/sync/trigger` | 手动触发同步 |
| GET | `/api/sync/status` | 获取同步状态 |
| GET | `/api/sync/config` | 获取同步配置 |
| PUT | `/api/sync/config` | 更新同步配置 |
| GET | `/api/sync/history` | 获取同步历史 |
| GET | `/api/sync/logs` | 获取同步日志 |

### 数据查询

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/api/mto/{mto_number}` | 按MTO查询状态 |
| GET | `/api/search?q={query}` | 搜索MTO号 |
| GET | `/api/export/mto/{mto_number}` | 导出Excel |

---

## 验证计划

### 阶段1: 基础层完成标准
- [ ] `Config` 类能正确读取 `conf.ini`
- [ ] `KingdeeClient` 能查询 PRD_MO 数据
- [ ] SQLite 数据库正确创建

### 阶段2: 数据读取完成标准
- [ ] 8个 Reader 都能正确获取数据
- [ ] 数据能正确缓存到 SQLite

### 阶段3: 同步服务完成标准
- [ ] 手动同步 API 工作正常
- [ ] 自动同步调度器工作正常
- [ ] 同步天数可配置 (1-365天)
- [ ] 同步进度实时更新

### 阶段4: 前端完成标准
- [ ] 同步控制面板显示正确
- [ ] 手动同步按钮工作正常
- [ ] 自动同步开关工作正常
- [ ] MTO搜索显示完整数据

---

## 已确认配置

| 配置项 | 设置值 | 说明 |
|--------|--------|------|
| **自动同步时间** | 07:00, 12:00, 16:00, 18:00 | 每天4次同步 |
| **默认同步天数** | 90 天 | 覆盖近3个月数据 |
| **配置存储方式** | JSON 文件 | sync_config.json, 支持热更新 |
| **前端框架** | Alpine.js | 与现有前端保持一致 |

---

## Docker 容器部署

### 项目结构 (含 Docker)

```
quickpulse-v2/
├── docker/
│   ├── Dockerfile              # 主应用镜像
│   ├── Dockerfile.dev          # 开发环境镜像
│   └── nginx.conf              # Nginx 配置 (可选)
├── docker-compose.yml          # 容器编排
├── docker-compose.dev.yml      # 开发环境编排
├── .dockerignore               # Docker 忽略文件
├── src/
├── data/                       # 数据卷挂载点
│   └── quickpulse.db          # SQLite 数据库
├── reports/                    # 同步状态文件
│   ├── sync_status.json
│   └── sync_history.json
└── sync_config.json            # 同步配置
```

### Dockerfile (生产环境)

```dockerfile
# docker/Dockerfile
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY pyproject.toml ./

# 安装 Python 依赖
RUN pip install --no-cache-dir -e .

# 复制应用代码
COPY src/ ./src/
COPY conf.ini ./
COPY sync_config.json ./

# 创建数据目录
RUN mkdir -p /app/data /app/reports

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml (生产环境)

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
      # 数据持久化
      - ./data:/app/data
      - ./reports:/app/reports
      # 配置文件 (支持热更新)
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

  # 可选: Nginx 反向代理
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

volumes:
  quickpulse-data:
```

### docker-compose.dev.yml (开发环境)

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
      # 代码热重载
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

networks:
  default:
    name: quickpulse-dev
```

### Dockerfile.dev (开发环境)

```dockerfile
# docker/Dockerfile.dev
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

# 开发环境额外安装
RUN pip install watchfiles

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### Docker 部署命令

```bash
# 构建并启动 (生产)
docker-compose up -d --build

# 构建并启动 (开发)
docker-compose -f docker-compose.dev.yml up --build

# 查看日志
docker-compose logs -f quickpulse

# 停止服务
docker-compose down

# 重启服务
docker-compose restart quickpulse

# 进入容器调试
docker exec -it quickpulse-v2 bash

# 手动触发同步 (容器内)
docker exec quickpulse-v2 curl -X POST http://localhost:8000/api/sync/trigger
```

### Nginx 配置 (可选)

```nginx
# docker/nginx.conf
events {
    worker_connections 1024;
}

http {
    upstream quickpulse {
        server quickpulse:8000;
    }

    server {
        listen 80;
        server_name localhost;

        # 静态文件缓存
        location /static/ {
            alias /app/src/frontend/static/;
            expires 7d;
            add_header Cache-Control "public, immutable";
        }

        # API 代理
        location /api/ {
            proxy_pass http://quickpulse;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_read_timeout 300s;
        }

        # 前端页面
        location / {
            proxy_pass http://quickpulse;
            proxy_set_header Host $host;
        }
    }
}
```

### .dockerignore

```
# Git
.git
.gitignore

# Python
__pycache__
*.pyc
*.pyo
.pytest_cache
.mypy_cache
*.egg-info
.venv
venv

# IDE
.idea
.vscode
*.swp

# 本地数据 (使用卷挂载)
data/*.db
reports/*.json
reports/*.log

# 文档
docs/
*.md
!README.md

# 测试
tests/
```

---

## 详细模块说明

### 1. 配置模块 (`src/config.py`) - 详细说明

```python
"""
配置管理模块

职责:
1. 从 conf.ini 读取 Kingdee API 凭证
2. 从 sync_config.json 读取同步配置
3. 支持环境变量覆盖
4. 配置验证和默认值

使用示例:
    from src.config import Config
    config = Config()
    print(config.kingdee_server_url)
"""

from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
import configparser
import json


class KingdeeConfig(BaseSettings):
    """Kingdee K3Cloud API 配置"""
    server_url: str = Field(..., description="K3Cloud 服务器地址")
    acct_id: str = Field(..., description="账套ID")
    user_name: str = Field(..., description="用户名")
    app_id: str = Field(..., description="应用ID")
    app_sec: str = Field(..., description="应用密钥")
    lcid: int = Field(2052, description="语言ID (2052=中文)")
    connect_timeout: int = Field(15, description="连接超时(秒)")
    request_timeout: int = Field(30, description="请求超时(秒)")

    @classmethod
    def from_ini(cls, ini_path: str = "conf.ini") -> "KingdeeConfig":
        """从 INI 文件加载配置"""
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
    """自动同步配置"""
    enabled: bool = Field(True, description="是否启用自动同步")
    schedule: list[str] = Field(
        ["07:00", "12:00", "16:00", "18:00"],
        description="自动同步时间表 (HH:MM 格式)"
    )
    days_back: int = Field(90, ge=1, le=365, description="同步天数")

    @field_validator('schedule')
    def validate_schedule(cls, v):
        import re
        for time_str in v:
            if not re.match(r'^([01]?\d|2[0-3]):([0-5]\d)$', time_str):
                raise ValueError(f"无效的时间格式: {time_str}")
        return v


class ManualSyncConfig(BaseSettings):
    """手动同步配置"""
    default_days: int = Field(90, description="默认同步天数")
    max_days: int = Field(365, description="最大同步天数")
    min_days: int = Field(1, description="最小同步天数")


class PerformanceConfig(BaseSettings):
    """性能配置"""
    chunk_days: int = Field(7, ge=1, le=30, description="分块天数")
    batch_size: int = Field(1000, ge=100, le=10000, description="批量插入大小")
    parallel_chunks: int = Field(2, ge=1, le=4, description="并行分块数")
    retry_count: int = Field(3, ge=1, le=5, description="重试次数")


class SyncConfig(BaseSettings):
    """完整同步配置"""
    auto_sync: AutoSyncConfig = Field(default_factory=AutoSyncConfig)
    manual_sync: ManualSyncConfig = Field(default_factory=ManualSyncConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)

    _config_path: str = "sync_config.json"

    @classmethod
    def load(cls, path: str = "sync_config.json") -> "SyncConfig":
        """从 JSON 文件加载配置"""
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
        """保存配置到 JSON 文件"""
        with open(self._config_path, 'w', encoding='utf-8') as f:
            json.dump(self.model_dump(), f, indent=2, ensure_ascii=False)

    def reload(self):
        """重新加载配置 (用于自动同步时检测配置变更)"""
        new_config = SyncConfig.load(self._config_path)
        self.auto_sync = new_config.auto_sync
        self.manual_sync = new_config.manual_sync
        self.performance = new_config.performance


class Config:
    """主配置类 - 单例模式"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_config()
        return cls._instance

    def _init_config(self):
        self.kingdee = KingdeeConfig.from_ini()
        self.sync = SyncConfig.load()
        self.db_path = Path("data/quickpulse.db")
        self.reports_dir = Path("reports")

        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
```

### 2. Kingdee 客户端 (`src/kingdee/client.py`) - 详细说明

```python
"""
Kingdee K3Cloud API 客户端封装

职责:
1. 封装 K3Cloud SDK 调用
2. 统一错误处理和重试逻辑
3. 支持异步查询
4. 日期范围分块查询

依赖:
- kingdee.cdp.webapi.sdk (SDK wheel 包)

使用示例:
    client = KingdeeClient(config.kingdee)
    orders = await client.query(
        form_id="PRD_MO",
        field_keys=["FBillNo", "FMTONo"],
        filter_string="FMTONo='AK2510034'"
    )
"""

import asyncio
import logging
from datetime import date, timedelta
from typing import Optional
from kingdee.cdp.webapi.sdk import K3CloudApiSdk

logger = logging.getLogger(__name__)


class KingdeeError(Exception):
    """Kingdee API 错误基类"""
    pass


class KingdeeConnectionError(KingdeeError):
    """连接错误"""
    pass


class KingdeeQueryError(KingdeeError):
    """查询错误"""
    pass


class KingdeeClient:
    """K3Cloud SDK 封装"""

    def __init__(self, config: "KingdeeConfig"):
        self.config = config
        self._sdk: Optional[K3CloudApiSdk] = None
        self._lock = asyncio.Lock()

    async def _get_sdk(self) -> K3CloudApiSdk:
        """获取或创建 SDK 实例 (线程安全)"""
        async with self._lock:
            if self._sdk is None:
                self._sdk = K3CloudApiSdk(self.config.server_url)
                # 使用配置初始化
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
        执行 Query API 调用

        Args:
            form_id: 表单ID (如 PRD_MO, PRD_PPBOM)
            field_keys: 要返回的字段列表
            filter_string: 过滤条件 (SQL WHERE 格式)
            limit: 返回记录数上限
            start_row: 起始行号 (分页用)

        Returns:
            记录列表, 每条记录为字段名到值的字典

        Raises:
            KingdeeQueryError: 查询失败时抛出
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
            # 在线程池中执行同步 SDK 调用
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: sdk.ExecuteBillQuery(params)
            )

            if not response:
                return []

            # 将二维数组转换为字典列表
            return [
                dict(zip(field_keys, row))
                for row in response
            ]

        except Exception as e:
            logger.error(f"Kingdee 查询失败: {form_id}, 错误: {e}")
            raise KingdeeQueryError(f"查询 {form_id} 失败: {e}") from e

    async def query_all(
        self,
        form_id: str,
        field_keys: list[str],
        filter_string: str = "",
        page_size: int = 2000
    ) -> list[dict]:
        """
        分页查询所有记录

        自动处理分页, 返回所有匹配记录
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
                break  # 最后一页

            start_row += page_size

        logger.info(f"查询 {form_id}: 共 {len(all_records)} 条记录")
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
        按日期范围查询

        Args:
            date_field: 日期字段名 (如 FDate, FCreateDate)
            start_date: 开始日期 (包含)
            end_date: 结束日期 (包含)
            extra_filter: 额外过滤条件

        Returns:
            日期范围内的所有记录
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
        按 MTO 号查询

        Args:
            mto_field: MTO 字段名 (不同表单字段名不同)
            mto_number: 计划跟踪号

        Returns:
            匹配的记录列表
        """
        filter_string = f"{mto_field}='{mto_number}'"
        return await self.query_all(
            form_id=form_id,
            field_keys=field_keys,
            filter_string=filter_string
        )
```

### 3. 数据读取器基类 (`src/readers/base.py`) - 详细说明

```python
"""
数据读取器抽象基类

职责:
1. 定义读取器接口
2. 提供通用字段映射逻辑
3. 统一错误处理

每个读取器实现需要:
1. 定义 form_id (Kingdee 表单ID)
2. 定义 field_keys (需要查询的字段)
3. 定义 mto_field (MTO 字段名, 不同表单不同)
4. 实现 to_model() 方法 (原始数据 -> Pydantic 模型)
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic
from datetime import date
from pydantic import BaseModel

from src.kingdee.client import KingdeeClient

T = TypeVar('T', bound=BaseModel)


class BaseReader(ABC, Generic[T]):
    """数据读取器抽象基类"""

    def __init__(self, client: KingdeeClient):
        self.client = client

    @property
    @abstractmethod
    def form_id(self) -> str:
        """Kingdee 表单ID"""
        pass

    @property
    @abstractmethod
    def field_keys(self) -> list[str]:
        """需要查询的字段列表"""
        pass

    @property
    @abstractmethod
    def mto_field(self) -> str:
        """MTO 字段名 (计划跟踪号字段)"""
        pass

    @property
    def date_field(self) -> str:
        """日期字段名 (用于按日期范围查询)"""
        return "FDate"  # 默认值, 子类可覆盖

    @abstractmethod
    def to_model(self, raw_data: dict) -> T:
        """将原始数据转换为 Pydantic 模型"""
        pass

    async def fetch_by_mto(self, mto_number: str) -> list[T]:
        """按 MTO 号查询并转换为模型"""
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
        """按日期范围查询并转换为模型"""
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
        """按单据号查询"""
        raw_records = await self.client.query_all(
            form_id=self.form_id,
            field_keys=self.field_keys,
            filter_string=f"{bill_field}='{bill_no}'"
        )
        return [self.to_model(r) for r in raw_records]
```

### 4. 生产订单读取器示例 (`src/readers/production_order.py`)

```python
"""
生产订单读取器 (PRD_MO)

对应 Kingdee 表单: PRD_MO (生产订单)
用途: 获取父项信息
"""

from decimal import Decimal
from typing import Optional
from pydantic import BaseModel

from src.readers.base import BaseReader


class ProductionOrderModel(BaseModel):
    """生产订单模型 (父项)"""
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
    """生产订单读取器"""

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
        """原始数据 -> 模型"""
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

---

## 下一步行动

准备好后，可以开始在 **4个并行终端** 上开发：

**终端1** - 基础层:
```bash
# 创建 src/config.py, src/database/, src/kingdee/client.py
```

**终端2** - 数据读取器:
```bash
# 创建 src/readers/ 目录下的 8 个 Reader 类
```

**终端3** - 同步服务:
```bash
# 创建 src/sync/, src/api/routers/sync.py
```

**终端4** - 前端:
```bash
# 更新 src/frontend/ 添加同步控制面板
```
