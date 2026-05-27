# Plan: 销售订单关闭状态 (FCloseStatus) 接入 QuickPulse

## Status: Not Started

## Design Spec

### Problem
QuickPulse 目前没有展示销售订单的"关闭状态"。金蝶 ERP 的 `SAL_SaleOrder` 列表页有这列（截图为证：值 `正常 / 已关闭`），业务上一个已关闭的销售订单行不应再被追踪，但目前 dashboard 上"剩余未出"仍会显示这些已关闭的订单，造成误导。

### Solution

**核心规则（OR 语义）**：一个销售订单行视为"已关闭"，当且仅当下列任一条件成立：

| 字段 | 层级 | 关闭值 | 说明 |
|---|---|---|---|
| `FCloseStatus` | 单据头 | `B` | 整单关闭 |
| `FSaleOrderEntry_FMrpCloseStatus` | 行级 | `B` | MRP 关闭（业务流断开） |
| `FSaleOrderEntry_FMANUALROWCLOSE` | 行级 | `true` | 手工行关闭 |

合并成单一 `close_status: str` 字段存到 `SalesOrderModel` 和 `cached_sales_orders.close_status`，值为 `'A'`（正常）或 `'B'`（已关闭）。

**展示**：
- Dashboard 新增"关闭状态"列，默认显示 `正常`，已关闭显示红色徽章 `已关闭`
- 表格顶部新增"显示已关闭"toggle（默认关闭），状态存 localStorage
- 后端始终返回全集；前端基于 toggle 过滤行

### Architecture: 3-Tier Cache Consistency

按 CLAUDE.md Pre-Change Checklist，必须同步改 3 条路径：

```
Live path:  factory.py → SalesOrderModel.close_status
                                ▼
Sync path:  sync_service._upsert_sales_orders_no_commit (INSERT close_status)
                                ▼
Cache path: cache_reader.get_sales_orders SELECT close_status + _row_to_sales_order
                                ▼
Handler:    mto_handler 把 close_status 透传到 ChildItem (仅 07.xx 成品行)
                                ▼
Frontend:   columns[N] 新增 close_status 列 + show_closed toggle
```

### Files to Modify

| 文件 | 改动 |
|---|---|
| `src/readers/models.py` | `SalesOrderModel` 新增 `close_status: str = "A"` |
| `src/readers/factory.py` | `SALES_ORDER_CONFIG` 字段映射：拉取 `FCloseStatus` + `FSaleOrderEntry_FMrpCloseStatus` + `FSaleOrderEntry_FMANUALROWCLOSE`，**用 GenericReader 的 post-processor 合并成 close_status**（任一关闭 → `'B'`） |
| `src/database/schema.sql` | `cached_sales_orders` 新增 `close_status TEXT DEFAULT 'A'` |
| `src/database/migrations/017_add_close_status_to_sales_orders.sql` | 迁移脚本：`ALTER TABLE cached_sales_orders ADD COLUMN close_status TEXT DEFAULT 'A'` |
| `src/sync/sync_service.py` | `_upsert_sales_orders_no_commit` INSERT 加 `close_status` 列 |
| `src/query/cache_reader.py` | `get_sales_orders` SELECT 列表加 `close_status`；`_row_to_sales_order` 行解析加该列；更新 column index docstring |
| `src/query/mto_handler.py` | 把 `sales_order.close_status` 透传到 `ChildItem.close_status` for 07.xx 成品；其他物料行 `close_status = None`（不展示徽章） |
| `src/readers/models.py` (ChildItem) | 新增 `close_status: Optional[str] = None` |
| `src/frontend/static/js/dashboard.js` | `columns` 数组新增 `{key: 'close_status', label: '关闭状态', width: 80, visible: true, resizable: true}`；新增 `showClosedRows: false` 状态；filter computed 跳过 `close_status === 'B' && !showClosedRows` |
| `src/frontend/dashboard.html` | 表格新增 `<td>` 渲染徽章；筛选区新增 toggle 控件 |
| `tests/unit/test_cache_reader.py` | 测试 row tuple 加 `close_status` 字段（注意位置） |
| `tests/unit/test_sales_order_reader.py` | 测试 OR 合并逻辑（3 个字段任一关闭 → `B`） |

### Data Flow (具体)

```
Kingdee API
  ├─ FCloseStatus = 'A'
  ├─ FSaleOrderEntry_FMrpCloseStatus = 'B'         ← any one 'B' or true wins
  └─ FSaleOrderEntry_FMANUALROWCLOSE = false
                ▼ factory post-processor
        close_status = 'B'
                ▼ sync writer
        cached_sales_orders.close_status = 'B'
                ▼ cache_reader._row_to_sales_order
        SalesOrderModel(close_status='B', ...)
                ▼ mto_handler (07.xx finished good)
        ChildItem(close_status='B', ...)
                ▼ FastAPI response
        {"close_status": "B"}
                ▼ Dashboard JS
        <span class="badge-rose">已关闭</span>
        (hidden by default unless showClosedRows toggle on)
```

### Why this design

- **OR 合成 + 单列存储**：业务只关心"这行还要不要追"，不关心是头关还是行关；落地成单列让查询/过滤简单。需要追溯时 `raw_data` 还在。
- **前端过滤而非后端**：已关闭行 << 总行数，payload 影响小；后端少分支逻辑；toggle 切换无需重新请求。
- **后向兼容**：`close_status` 默认 `'A'`（正常），旧数据 NULL 视为正常 → 行为等价于"该字段不存在"时的现状。

### 部署影响

- 需要在 prod + dev 各跑一次 **7 天 catch-up sync**（不需要 365 天全量），把新字段灌进来。预计 25-30s/env。
- Schema migration 自动在 app 启动时运行（按现有 migration runner 约定）。
- localStorage `prefs.columns` 会自动注入新列，旧用户首次刷新看到新列出现（默认 visible），不影响其他列宽度。

## Test Cases

### Unit Tests
- [ ] `tests/unit/test_sales_order_reader.py::test_close_status_all_a_returns_a` — 3 字段全正常 → `'A'`
- [ ] `tests/unit/test_sales_order_reader.py::test_close_status_header_closed` — `FCloseStatus='B'` → `'B'`
- [ ] `tests/unit/test_sales_order_reader.py::test_close_status_row_mrp_closed` — `FMrpCloseStatus='B'` → `'B'`
- [ ] `tests/unit/test_sales_order_reader.py::test_close_status_manual_row_close` — `FMANUALROWCLOSE=true` → `'B'`
- [ ] `tests/unit/test_cache_reader.py::test_get_sales_orders_returns_close_status` — row tuple 含 close_status，模型字段正确填充
- [ ] `tests/unit/test_cache_reader.py::test_get_sales_orders_legacy_null_close_status` — NULL → 默认 `'A'`

### Integration Tests
- [ ] 用一个已知有关闭行的 MTO（手动找一个，prod 上跑 `kingdee-query` 验证）→ API 返回 close_status='B'
- [ ] 同 MTO 加 `?show_closed=false`（前端默认）→ 该行在 DOM 中被 `x-show` 隐藏

### Manual Verification
1. 跑 dev sync 7 天 catch-up
2. 浏览器打开 dev dashboard，查一个有关闭行的 MTO
3. 确认表头有"关闭状态"列
4. 确认已关闭行**默认不显示**
5. 打开"显示已关闭"toggle → 关闭行出现，徽章为红色"已关闭"
6. 关闭 toggle → 行重新隐藏
7. 刷新页面 → toggle 状态保持（localStorage）
8. 对照金蝶 ERP UI，确认 QuickPulse 和金蝶展示一致

## Acceptance Criteria

- [ ] 单元测试全通过：`pytest tests/unit/test_sales_order_reader.py tests/unit/test_cache_reader.py -v`
- [ ] 全部测试通过：`pytest --ignore=tests/e2e --ignore=tests/integration` 718+ 测试全绿
- [ ] dev 环境 7 天 catch-up sync 成功，无 schema 错误
- [ ] 截图里的金蝶销售订单列表"正常 / 已关闭"行为在 QuickPulse 上 1:1 重现（人工对照至少 3 个 MTO）
- [ ] 不破坏既有 MTO 查询：随机抽 5 个 MTO，对比改动前后的 `剩余未出数量 / 累计出库`，应完全一致

## Out of Scope

- 不实现"关闭后自动从查询里删除"——只做展示 + 默认隐藏
- 不接 `FCloseDate / FCloserId`（关闭时间/关闭人）——如需追溯走 `raw_data`
- 不改 `kingdee-query` CLI 脚本（那个是独立工具）

## Estimated Scope

- 代码改动：~150 行（含 migration + tests）
- 部署：dev + prod 各一次 7 天 catch-up sync
- 时间：30-45 分钟编码 + 15 分钟测试 + 部署
