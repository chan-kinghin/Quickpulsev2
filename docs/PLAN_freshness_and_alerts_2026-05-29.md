# Plan: 数据新鲜度仪表 + 静默失败修复 (QW-1) + 超领/超发预警中心 (QW-2)

## Status: Deployed to dev + prod ✓ (2026-05-29)

> Merged to `main` (FF), CD-deployed **dev and prod** (both verified: `/alerts.html` 200, freshness/over-pick/over-ship return real data).
>
> **Follow-on fixes shipped same day:**
> - `authGuard` fail-open (`ef7faea`) — a flaky `/api/auth/verify` 503 used to blank every protected page; now shows the page on transient failures (verified on dev under a forced 503).
> - **nginx**: `/api/auth/verify` was bucketed under `zone=login` (5r/m) in the shared ops-nginx → normal browsing 503'd. Moved to `zone=api` (10r/s) via a `location = /api/auth/verify` exact-match in `20-quickpulse.conf` + `40-subdomains.conf` (dev+prod), `nginx -t` + reload OK. Verify now 15/15 200 on both envs. Backups: `*.bak-verify-20260529-105619`. See [[cvm-nginx-verify-ratelimited-as-login]].
>
> **Resolved (the freshness card earned its keep)**: the `cached_sales_orders` staleness was NOT a sync-cadence quirk — it was a silent regression from the close-status feature (`SAL_SaleOrder` queried the non-existent field `FSaleOrderEntry_FMrpCloseStatus` → Kingdee failed the whole query → 0 sales orders in sync AND live, fleet-wide, for ~2 days). Fixed in `f10632d` (bare field names `FMrpCloseStatus`/`FMANUALROWCLOSE` + regression guard), deployed dev+prod, re-synced both (sales_orders 5346→~7600 rows, stale_count=0), live MTO query restored (customer/delivery/order qty back). See bug-patterns.md Pattern 12.


> 3 阶段全部落地,新增 21 个测试全绿(`1010 passed`)。真数据 smoke(`data/quickpulse.db`)验证:超领 927 条、超发 487 条(榜首=第一大客户刀刀超发 +64,736)、9 表新鲜度正常。
> ⚠️ 发现 **预先存在**的 3 个红测试(`tests/api/test_mto_endpoints.py` 的 use_cache 默认值 test-vs-code 漂移),在 baseline `7f081a8` 上即失败,与本次改动无关——待用户决定是否单独处理。

> 来源: `docs/` 下 feature-ideation workflow 产出的 roadmap。本计划只覆盖第一波 Quick Wins —— **零信任债、数据现成、顺手修掉 3 条活着的静默失败 bug**。
> 原则: 全部停在 `mto + material` 或整单/整表粒度的**确定性硬数字**,**绝不下钻 aux**(规避历史 silent fallback)。
> 不在本计划范围: 企业微信推送(`src/notify/wecom.py`)—— v1 用结构化 WARNING 日志接 Loki/Grafana 告警即可,推送留到 S-5。

---

## 已核实的证据(全部回源码确认 file:line)

| 现象 | 位置 | 验证结论 |
|---|---|---|
| 同步 1~50% chunk 失败仍记 `status="success"` | `sync_service.py:127→234`、`run_sync:136` | ✅ `_sync_date_range` 仅在 `fail_ratio>0.5` 抛异常;否则 `run_sync` 一律记 success。`SyncResult` 只有 success/error 两态,**无 partial**。 |
| 定时同步 fire-and-forget,future 无回收 | `scheduler.py:65` | ✅ `run_coroutine_threadsafe(...)` 返回的 future 被丢弃,无 `add_done_callback` —— 后台同步崩了无人知。 |
| `check_freshness` 是 per-MTO + `LIKE ?`,无表级新鲜度 | `cache_reader.py:1043-1075` | ✅ 9 表 UNION 但每条带 `WHERE mto_number LIKE ?`。表级新鲜度需**新方法**(不带 mto 过滤、不用 LIKE)。 |
| 超领口径 | `metrics.py:216 _compute_over_pick` | ✅ `over = picking - demand`,`>0` 即 warning。SQL 口径复用此定义。 |
| 三张表列名 | `schema.sql` | ✅ `cached_material_picking(app_qty, actual_qty)`、`cached_sales_delivery(real_qty, must_qty)`、`cached_sales_orders(qty, customer_name, delivery_date, close_status, material_group_name)`。`sync_history.status` 是自由 TEXT(加 `partial` **零迁移**)。 |

---

## Design Spec

### 问题
1. **静默失败**: 部分 chunk 失败/某张表停更,系统对外仍"绿"。运营每天靠 dashboard 答客户交期,发货表悄悄停更会直接误报发货进度,无人发现(migration 008 同款家族,曾静默 52 天)。
2. **看不见的钱漏**: 包材/静电膜**超领**(月度报告里单 MTO `DS25C318S` 超领 1.1 万)和出口**超发**(报关数量不符、应收坏账)目前只有月度静态脚本,没有实时看板,装柜/开票前无法拦截。

### 解决方案

#### QW-1 — 数据新鲜度仪表 + 静默失败修复

**后端**
- `SyncResult` 增加 `status="partial"` 支持 + `failed_chunks: int` 字段;`_sync_date_range` 返回 `(records_synced, failed_indices)`,`run_sync` 据此记 `status="partial"`(<50% 失败)并把失败 chunk 数写入 `error_message`(无需 schema 迁移)。
- `_sync_date_range` 在有部分失败时发结构化 WARNING:`sync_partial` 日志行(对齐现有 `mto_fallback_telemetry` 风格,Loki 可告警)。
- `scheduler.py:65` 给 future 挂 `add_done_callback`,捕获并 `logger.error` 后台同步异常。
- `cache_reader.py` 新增 `table_freshness() -> list[TableFreshness]`:对 9 张 `cached_*` 表各跑 `SELECT MAX(synced_at), COUNT(*)`(**全表、无 mto 过滤、无 LIKE**),按真实同步窗口(07/12/16/18 UTC?需按 `config.auto_sync.schedule` 实际值)判定 fresh/stale/empty。
- `src/api/routers/sync.py` 新增 `GET /api/sync/freshness` 返回每表 `{table, last_synced_at, row_count, verdict}` + 整体 `oldest`。任一表 stale/empty 时发 `freshness_alert` WARNING。

**前端**
- `sync.html`: 9 表新鲜度健康卡(最后同步时间 + 行数 + 绿/黄/红 badge)。`synced_at` 是 UTC naive,展示按本地时区换算。
- `dashboard.html`: header 加紧凑新鲜度徽标(取最旧表),点击跳 `sync.html`;数据陈旧时变黄/红。

#### QW-2 — 超领/超发预警中心

**后端**
- `cache_reader.py` 新增:
  - `get_over_pick_alerts()`: `cached_material_picking` `GROUP BY mto_number, material_code HAVING SUM(actual_qty)-SUM(app_qty)>0`;LEFT JOIN `cached_sales_orders` 带出 `customer_name/delivery_date`;单列标记 `SUM(app_qty)=0 AND SUM(actual_qty)>0` 为"未申请直接发料"严重档。**NULL 的 app_qty/actual_qty 行显式跳过 + WARNING,绝不当 0。**
  - `get_over_ship_alerts()`: `SUM(cached_sales_delivery.real_qty) - SUM(cached_sales_orders.qty) > 0`,按 `mto_number+material_code` 子查询相减,JOIN 客户;**排除 `close_status='B'`**。
- 新建 `src/api/routers/alerts.py`:`GET /api/alerts/over-pick`、`GET /api/alerts/over-ship`(rate limit 比照 mto 端点 30/min);`main.py:307` 后 `app.include_router(alerts.router)`。

**前端**
- 新建 `src/frontend/alerts.html`(复用 `inventory.html` 列表/卡片骨架),两 tab(超领/超发),行点击下钻跳 `dashboard.html?mto=`。`main.py` 加 `@app.get("/alerts.html")` FileResponse。nav 加入口(参考 wave-2 nav tabs)。

### Files to Modify / Create

```
src/sync/sync_service.py            (modify) — SyncResult partial 态 + 部分失败上报
src/sync/scheduler.py               (modify) — future done_callback
src/query/cache_reader.py           (modify) — table_freshness() + over_pick/over_ship 聚合
src/api/routers/sync.py             (modify) — GET /api/sync/freshness
src/api/routers/alerts.py           (create) — over-pick / over-ship 端点
src/main.py                         (modify) — include alerts.router + /alerts.html 路由
src/frontend/sync.html              (modify) — 新鲜度健康卡
src/frontend/dashboard.html         (modify) — header 新鲜度徽标
src/frontend/alerts.html            (create) — 预警中心页
src/frontend/inventory.html / dashboard.html nav (modify) — 加预警入口
tests/unit/test_cache_reader.py     (modify) — freshness/over-pick/over-ship 单测
tests/unit/test_sync_service.py     (modify/create) — partial 状态单测
```

---

## 分阶段执行(按文件所有权切,避免并行冲突)

### Stage 1 — 后端数据层(纯逻辑,无 UI)
**Goal**: cache_reader 三个新方法 + sync 部分失败修复 + scheduler callback
**Files**: `sync_service.py`, `scheduler.py`, `cache_reader.py`
**Tests**: over-pick 聚合(含 NULL 跳过)、over-ship 聚合(含 close_status 排除)、table_freshness、partial 状态
**Success**: `pytest --ignore=tests/e2e --ignore=tests/integration` 全绿

### Stage 2 — API 层
**Goal**: `/api/sync/freshness` + `/api/alerts/*` + 路由注册
**Files**: `sync.py`, `alerts.py` (create), `main.py`
**Depends on**: Stage 1
**Success**: 三个端点本地 curl 返回结构正确;rate limit 生效

### Stage 3 — 前端
**Goal**: 新鲜度卡 + header 徽标 + alerts.html + nav 入口
**Files**: `sync.html`, `dashboard.html`, `alerts.html` (create), nav
**Depends on**: Stage 2
**Success**: 三页渲染正常,下钻跳转 OK,陈旧数据变黄/红;cache-buster `?v=` 同步刷新

---

## Test Cases

### Unit
- [ ] `get_over_pick_alerts`: 构造 actual>app 的行 → 返回;app=0&actual>0 → 标严重;actual==app → 不返回。
- [ ] `get_over_pick_alerts`: `app_qty=NULL` 或 `actual_qty=NULL` 的行 → **跳过且 log WARNING**,不计入(不当 0)。
- [ ] `get_over_pick_alerts`: 同 mto+material 跨多张领料单 → 先 SUM 再比较(单单据不误报)。
- [ ] `get_over_ship_alerts`: delivery.real_qty 之和 > order.qty 之和 → 返回;`close_status='B'` 的订单行 → 排除。
- [ ] `table_freshness`: 空表 → verdict=empty;旧 synced_at → stale;新 → fresh。**断言不含 `LIKE` 子句**(防回退到 per-MTO 查询)。
- [ ] `run_sync`: mock `_sync_date_range` 返回部分失败 → `SyncResult.status=="partial"` 且 error_message 含失败数(用真实历史/旧数据可触发,而非永远过不了的断言)。

### Manual Verification
1. `GET /api/sync/freshness` → 9 表各有 last_synced_at + row_count + verdict。
2. `GET /api/alerts/over-pick` → 拿一个已知超领 MTO(`DS25C318S`)核对金额与月度报告一致。
3. `GET /api/alerts/over-ship` → 抽一个出口客户 MTO 人工核对。
4. sync.html 新鲜度卡 / dashboard 徽标 / alerts.html 下钻全链路点一遍。

---

## 硬约束(信任债护栏 —— 验收门槛,不是建议)

1. **全部停在 `mto+material`/整单/整表粒度,绝不 JOIN aux、绝不用精确履约率** —— 规避 `get_mto_bom_joined` 的 aux 三层 silent fallback。
2. **NULL/缺失数量行显式跳过 + WARNING,绝不当 0** —— 否则把"没同步上"误判成"没超领/没超发"(MEMORY 点名的 cache 盲点 bug 家族)。
3. **跨表关联只用精确 `mto_number` 等值,绝不用 `LIKE` 前缀** —— `check_freshness` 现存的 `LIKE` 是仓库里活着的反面教材(bug-patterns #5 cross-MTO 污染)。
4. **`freshness_alert` / `sync_partial` 日志发送/写入失败必须本地兜底 log** —— 否则告警通道自己静默失败 = 复演同款 bug。
5. **超发 v1 标注"含辅助属性差异,需人工核"** —— 不强行 aux 精配。
6. **新鲜度阈值按 `config.auto_sync.schedule` 真实窗口设**,避免夜间无同步窗口误报。

---

## Acceptance Criteria

- [ ] 部分 chunk 失败时 `sync_history.status='partial'`(不再假绿),且 Loki 能查到 `sync_partial` 行。
- [ ] 后台定时同步抛异常时 `scheduler` 有 `logger.error`(不再 fire-and-forget 吞掉)。
- [ ] `/api/sync/freshness` 表级新鲜度查询**不含 `LIKE`**。
- [ ] 超领看板金额与 `docs/超领异常报告_20260130.md` 对得上(口径一致)。
- [ ] 全部端点绕开 aux;NULL 行有跳过日志。
- [ ] `pytest --ignore=tests/e2e --ignore=tests/integration` 全绿;前端 cache-buster 已同步刷新。
