# Plan: 物料库存查询 (Inventory Search)

## Status: Not Started

## Design Spec

### Problem
现有 QuickPulse 全部围绕 MTO（计划跟踪号）查询：必须先知道 MTO 才能看到物料 / 收发 / 库存。
业务方场景缺口：拿到一个**物料编码 / 名称关键词 / 规格型号关键词**，想立刻知道
"这玩意儿仓库还有多少、分在哪几个仓、不同批次/颜色各多少"——和具体 MTO 无关。

### Solution

**架构定位**: 实时直查金蝶，不进 SQLite cache，不动 sync_service。这是一条
**独立的物料-枢轴数据路径**，与现有 MTO-枢轴数据路径正交。

**数据流**:

```
用户输入: "GT38" 或 "07.01.001" 或 "潜水镜"
    │
    ▼
[Step A] BD_MATERIAL 模糊搜索        ← 缩小物料候选集 (cap 50)
    │   filter: FName LIKE / FSpecification LIKE / FNumber LIKE
    │   filter: FForbidStatus = 'A' (排除已禁用)
    ▼
返回: [{code, name, spec, erp_class}, ...]
    │
    │  (用户选中具体物料后调下一步)
    ▼
[Step B] STK_Inventory 按物料查库存   ← 实时即时库存
    │   filter: FMaterialId.FNumber = '<code>' AND FBaseQty <> 0
    │   field: FStockId.FNumber, FStockId.FName, FAuxPropId,
    │          FLot.FNumber, FBaseQty, FStockOrgId.FName
    ▼
[Step C] BD_FLEXSITEMDETAILV 解析辅助属性 (批量)
    │   filter: FID IN (<aux_ids>)
    │   field: FF100001 (规格), FF100002.FName (颜色)
    ▼
返回: 按 (仓库 × 批号 × 辅助属性) 拆分的库存明细
```

**为什么用两步查询而不是直接 STK_Inventory 模糊搜索**:
- STK_Inventory 行数 = 物料数 × 仓库数 × 批号 × 辅助属性，量级远大于 BD_MATERIAL
- 模糊搜索走 BD_MATERIAL 拿到精确 FNumber 列表，再用 `IN (...)` 走 STK_Inventory 索引，
  比直接在 STK_Inventory 上做 `FMaterialId.FName LIKE` 快一个数量级
- 用户体验也更好：先看候选物料列表，确认是不是自己要的再展开库存

### Files to Modify / Create

**Backend (新增)**:
```
src/models/inventory.py              (create)  — Pydantic 数据模型
src/readers/inventory.py             (create)  — Kingdee 查询逻辑
src/api/routers/inventory.py         (create)  — FastAPI endpoints
src/main.py                          (modify)  — 注册路由 + /inventory 页面
```

**Frontend (新增)**:
```
src/frontend/inventory.html          (create)  — 独立查询页面
```

**Tests (新增)**:
```
tests/unit/test_inventory_reader.py  (create)  — Mock SDK，验证 Kingdee 调用
tests/unit/test_inventory_router.py  (create)  — 验证 auth / 限流 / 响应结构
tests/unit/test_inventory_models.py  (create)  — Pydantic 序列化测试
```

**Documentation (更新)**:
```
CLAUDE.md                            (modify)  — Project Structure 段补 inventory 路径
memory/MEMORY.md                     (modify)  — Architecture 段加一句"物料-枢轴次路径"
```

### API Contract

#### `GET /api/inventory/search`
**Query params**:
- `q`: string, min_length=2, max_length=50 (URL-encoded, supports CJK)
- `limit`: int, default=20, max=50

**Response** (200):
```json
{
  "query": "GT38",
  "total": 3,
  "items": [
    {
      "material_code": "07.01.001",
      "material_name": "潜水镜",
      "specification": "GT38-BLK",
      "erp_class": "9",
      "erp_class_label": "成品"
    }
  ]
}
```

**Errors**:
- 400: q too short / contains illegal chars (e.g. `'`, `;`)
- 502: Kingdee unreachable
- 429: rate limit exceeded

#### `GET /api/inventory/material/{material_code}`
**Path params**:
- `material_code`: e.g. `07.01.001` (pattern `^[A-Za-z0-9\.\-]+$`)

**Query params**:
- `include_zero`: bool, default=false (是否包含 0 库存的仓库行)

**Response** (200):
```json
{
  "material_code": "07.01.001",
  "material_name": "潜水镜",
  "specification": "GT38-BLK",
  "erp_class": "9",
  "erp_class_label": "成品",
  "total_qty": 1234.0,
  "warehouse_count": 4,
  "rows": [
    {
      "warehouse_code": "01.01",
      "warehouse_name": "外销成品仓",
      "lot_number": "L20260512",
      "aux_id": 12345,
      "aux_desc": "GT38 / 黑色",
      "base_qty": 800.0,
      "stock_org": "福伦特"
    }
  ]
}
```

### Filter String Sanitization (security)

User-provided `q` flows into Kingdee `FilterString`. Required handling in
`src/readers/inventory.py::sanitize_query`:
```python
def sanitize_query(q: str) -> str:
    # Allow CJK, ASCII letters/digits, dot, dash, underscore, space
    # Reject: quotes, semicolon, parens, equals
    if not re.match(r"^[\w\s一-鿿\.\-]{2,50}$", q):
        raise ValueError("Invalid characters in query")
    return q.replace("'", "''")  # SQL standard escape, just in case
```
**Why both regex + escape**: defense in depth — regex blocks obvious injection,
escape covers edge cases (apostrophes in legitimate Chinese punctuation).

### Performance Budget

| Step | Expected latency | Cap |
|---|---|---|
| BD_MATERIAL 搜索 | 0.5-1.5s | LIMIT 50 候选 |
| STK_Inventory 单物料 | 0.3-1.0s | (单物料行数通常 <100) |
| BD_FLEXSITEMDETAILV 批量 | 0.2-0.5s | 一次最多 200 个 aux_id |
| **End-to-end** | **1-3s** | rate limit `20/min/user` |

如果某个物料涉及 >50 个仓库行（极端情况），分页或限制返回数量。

## Test Cases

### Unit Tests

**`test_inventory_reader.py`**:
- [ ] `test_search_material_by_code_exact` — 输入 `07.01.001` → 1 个结果
- [ ] `test_search_material_by_name_fuzzy` — 输入 `潜水镜` → ≥1 个结果
- [ ] `test_search_material_by_spec` — 输入 `GT38` → 返回的物料 specification 都包含 GT38
- [ ] `test_search_excludes_forbidden_materials` — 验证 filter 含 `FForbidStatus = 'A'`
- [ ] `test_search_rejects_sql_injection` — 输入 `'; DROP TABLE` → ValueError
- [ ] `test_search_rejects_too_short` — 输入 `a` → ValueError
- [ ] `test_get_inventory_returns_per_warehouse_rows` — 单物料返回多仓库
- [ ] `test_get_inventory_filters_zero_by_default` — 默认 `FBaseQty <> 0`
- [ ] `test_get_inventory_includes_zero_when_flag` — `include_zero=true` 时去掉过滤
- [ ] `test_aux_resolution_batches_by_200` — >200 个 aux_id 时分批查询
- [ ] `test_aux_id_zero_skipped` — aux_id=0 不查 BD_FLEXSITEMDETAILV

**`test_inventory_router.py`**:
- [ ] `test_search_requires_auth` — 无 token → 401
- [ ] `test_search_rate_limited` — 21 次/min → 429
- [ ] `test_search_returns_x_total_count` — 响应头含 total
- [ ] `test_get_material_404_on_nonexistent` — 不存在的编码 → 404
- [ ] `test_get_material_502_on_kingdee_down` — Kingdee 异常 → 502
- [ ] `test_get_material_path_validation` — 路径含非法字符 → 422

**`test_inventory_models.py`**:
- [ ] `test_inventory_row_serialization` — Pydantic dump 字段名正确
- [ ] `test_erp_class_label_mapping` — `1→外购, 2→自制, 3→委外, 4→虚拟件, 9→成品`

### Integration Tests
- [ ] `test_inventory_search_live_smoke` (manual gate) — 真实 Kingdee 环境跑一次搜 `潜水镜`，确认返回非空
- [ ] `test_inventory_material_live_smoke` (manual gate) — 真实 Kingdee 查一个已知物料，对照金蝶 web UI

### Manual Verification
1. 打开 `/inventory`，搜索 `GT38` → 看到至少 1 个候选物料
2. 点击候选物料 → 看到按仓库拆分的库存表格
3. 搜索框输入 `'` → 前端报"非法字符"或后端 400
4. 连续点击 25 次 → 看到 429 限流提示
5. 在 Kingdee web UI 找同一物料的"即时库存查询"，对照数字（总量必须匹配）

## Acceptance Criteria

- [ ] `/inventory` 独立页面可访问，UI 与现有 dashboard 风格一致
- [ ] 三种搜索方式都能工作：物料编码、物料名称、物料规格
- [ ] 结果按仓库 × 批号 × 辅助属性拆分展示
- [ ] 实时直查金蝶，无缓存（每次请求都打 Kingdee）
- [ ] 所有新测试通过 (`pytest tests/unit/test_inventory_*.py`)
- [ ] 限流生效，单用户 20 次/分钟
- [ ] 注入测试通过，单引号 / 分号 / 引号被拦截
- [ ] CLAUDE.md + memory/MEMORY.md 已更新，描述新数据路径
- [ ] CVM dev 环境验证：访问 `https://dev.fltpulse.szfluent.cn/inventory`，搜索一次成功

## Out of Scope (本期不做)

- ❌ 库存历史变动趋势（按时间轴看进出库）
- ❌ 跨物料的"用这一批可以做多少 MTO"反查
- ❌ 库存预警 / 安全库存提示
- ❌ 缓存层（虽然你选了实时，但如果以后觉得慢，再加 60s TTL 短缓存）
- ❌ 导出 Excel（先把查询做好，导出可以下一期）

## Risks & Open Questions

1. **大库存物料**: 如果某个物料在 30+ 仓库都有库存，UI 表格会很长。是否需要"只显示有货的仓库"开关？(已经默认 `FBaseQty <> 0`，应该够)
2. **多组织**: 你们金蝶里有几个 `FStockOrgId`？如果只有"福伦特"一个，可以不展示这列；如果多个，必须分开。**待你确认**。
3. **权限**: 现在 `get_current_user` 只验证登录，不分角色。库存数据要不要限制到某些用户？(默认全员可见)
