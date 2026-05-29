# Plan: Dev 测试发现的 6 个问题修复

## Status: Complete (code + local browser verification done; NOT yet deployed to dev)

## Verification Results (2026-05-29, localhost:8011 against real 151MB DB)
- **Tests**: `3 failed, 1040 passed` — the 3 are PRE-EXISTING `test_mto_endpoints.py` use_cache drift (unrelated). +2 new over-pick tests.
- **A** ✓ one `init()` per load (was 2×).
- **B** ✓ over-pick enrichment on real DB: customer/delivery 5→**808/927**, material_name 5→**865/927** via COALESCE(PPBOM, purchase_orders). Names are correct COMPONENT names (开边袋/PE骨袋/鼻夹…), never finished-good. **Refinement beyond original plan**: added purchase_orders join (PPBOM-only was 145/927).
- **C** ✓ limit=1000, badge 超领(887), no false cap banner.
- **D** ✓ dropdown closes after 查询; parent banner visible.
- **E** ✓ no `loading is not defined`.
- **F** ✓ 合计=16; chip reads 按名称.
- **#7 BONUS (pre-existing, found during verify)**: searchResults x-for `:key="result.mto_number"` produced DUPLICATE keys (autocomplete returns 1 row/material, multiple per MTO) → "Duplicate key" + "reading 'after'" crash. Fixed via `:key="result.mto_number + '|' + index"`. NOT caused by Fix D (diff was @click.away only).

来源：2026-05-29 用 Chrome 实测 dev (`develop` @ `8848791`) 五个页面 + 6 个并行 root-cause agent 确认。

## 文件归属（并行无冲突分组）

| Agent | 拥有文件 | 修的问题 |
|-------|---------|---------|
| 1 后端 | `src/query/cache_reader.py`, `src/api/routers/alerts.py`, `tests/unit/test_cache_reader.py`, `tests/api/test_alerts_and_freshness_endpoints.py` | B, C-后端 |
| 2 Dashboard FE | `src/frontend/dashboard.html`, `src/frontend/static/js/dashboard.js` | A, D |
| 3 Alerts FE | `src/frontend/alerts.html` | C-前端 |
| 4 Inventory FE | `src/frontend/inventory.html` | E, F |

**契约**：C 的前后端通过响应字段 `total_count` 对齐（后端在两个 alert dict 里加，前端读 `data.total_count`）。

---

## A — Dashboard `init()` 双重执行 (medium)
**Problem**: `dashboard.html:27` 同时有 `x-data="mtoSearch()"` 和 `x-init="init()"`；Alpine 会自动调一次对象上的 `init()`，`x-init` 又调一次 → 每次加载 init 跑两遍（双份 `/api/agent-chat/status`、双份偏好加载、重复定时器）。
**Fix**: 删除 `dashboard.html:27` 的 `x-init="init()"`（保留 `x-data`，Alpine 仍会自动调 `init()`）。
**Verify**: Chrome 复测 dashboard，console 只出现一次 "Dashboard initialized"，`/api/agent-chat/status` 只发一次。

## B — 超领 enrichment 三列全空 (HIGH)
**Problem**: `cache_reader.py:1148-1157` 的 LEFT JOIN 用 `material_code` 关联 `cached_sales_orders`，但 picking 的 material_code 是组件码(03/05.xx)、SO 是成品码(07.xx)，命名空间不重叠 → customer/delivery/material_name 全 NULL→`""`。超发能填是因两边都用 07.xx。
**Fix** (`get_over_pick_alerts`)：拆成两个正确粒度的 JOIN：
- `customer_name` / `delivery_date`：`cached_sales_orders` 按 `mto_number` 聚合（MTO 粒度，超领告警本就是 MTO 级）。
- `material_name`：`cached_production_bom`（PPBOM）按 `(mto_number, material_code)` 聚合 —— 这才是**组件**名，**绝不能**用 SO 的成品名（会把 `03.17.001` 错标成"泳镜"，制造新的静默错数据）。
```sql
FROM cached_material_picking mp
LEFT JOIN (SELECT mto_number, MAX(customer_name) customer_name, MAX(delivery_date) delivery_date
           FROM cached_sales_orders GROUP BY mto_number) so
       ON so.mto_number = mp.mto_number
LEFT JOIN (SELECT mto_number, material_code, MAX(material_name) material_name
           FROM cached_production_bom GROUP BY mto_number, material_code) bom
       ON bom.mto_number = mp.mto_number AND bom.material_code = mp.material_code
WHERE mp.app_qty IS NOT NULL AND mp.actual_qty IS NOT NULL
GROUP BY mp.mto_number, mp.material_code
HAVING SUM(mp.actual_qty) - SUM(mp.app_qty) > 0
```
SELECT 输出对应改 `so.customer_name, so.delivery_date, bom.material_name`。
**Verify**: 单元测试断言超领行的 customer_name 非空（来自 SO）、material_name=组件名（来自 PPBOM，非成品名）；Chrome 复测超领 tab 三列有值。

## C — 预警静默截断 (medium)
**Problem**: 前端硬编码 `?limit=500`(alerts.html:213)，实际 967 条超领只显示 497，无"共 N 条"提示；后端不返回总数。
**Fix-后端** (`cache_reader.py` 两个函数)：在主查询前加一个 `COUNT(*)`（同 WHERE/HAVING、无 LIMIT 的合格集计数），返回 dict 增加 `"total_count": <int>`。`_filter_samples` 不动 total_count，自动透传，router 无需改。
**Fix-前端** (`alerts.html`)：limit 500→1000；存 `data.total_count`；仅当**确实触顶**时显示横幅（`rawReturned = alerts.length + excluded_sample_count; capped = rawReturned >= limitUsed`），文案如"显示前 N 条，共约 M 条超领记录，请缩小范围或导出"。角标维持显示当前条数。
**Verify**: 后端测试断言 total_count ≥ len(alerts)；Chrome 看 limit=1000 时不再丢数据。

## D — 搜索下拉卡住/遮挡/误显"未找到" (medium)
**Problem**: `dashboard.html:140` 查询按钮没 reset `showSearchResults`；下拉 div(110,131) 无 `@click.away`；`dashboard.js` 防抖 300ms 在 blur 后又把下拉打开。
**Fix**:
- `dashboard.html:140` 按钮改 `@click="showSearchResults=false; showSearchHistory=false; search()"`
- 两个下拉 div 加 `@click.away="showSearchResults=false"`
- `dashboard.js` `search()` 开头(guard 后)加 `this.showSearchResults=false; this.showSearchHistory=false;` 并清掉 pending 防抖 timer
**Verify**: Chrome 查询后下拉自动关、点外部关、不再误显"未找到相关结果"。

## E — 库存页 `loading is not defined` (medium)
**Problem**: `inventory.html:371` 的 `aria-live` sr-only div 写在了 `inventorySearch()` 组件 `</div>`(368) **外面**，落到 `authGuard()` 作用域（无 `loading/errorMsg`）→ 每次 Alpine effect 抛 ReferenceError。
**Fix**: 把该 div 移到 `inventorySearch()` 闭合 `</div>`(368) **之前**（成为组件最后一个子元素，对齐 alerts.html 的正确写法），删除原 370-373 重复块。
**Verify**: Chrome 库存页 console 无 ReferenceError。

## F — 库存小问题 (low)
**Problem**: (1) 合计显示 `-`：`base_qty` 是 Pydantic v2 `Decimal`→JSON 字符串 `"2.00"`，`reduce` 字符串拼接→`isNaN`→`-`(inventory.html:345)。(2) 结果卡上孤零零"名称"标签：match-source 芯片文案是裸名词(inventory.html:165)。
**Fix**: (1) `inventory.html:345` reduce 里 `s + (Number(r.base_qty)||0)`。(2) 芯片映射改 `{name:'按名称', aux:'按辅助属性', customer:'按客户'}`。
**Verify**: Chrome 看合计=16，芯片显示"按名称"。

---

## Acceptance Criteria
- [ ] `pytest tests/unit/test_cache_reader.py tests/api/test_alerts_and_freshness_endpoints.py` 全绿
- [ ] `pytest --ignore=tests/e2e --ignore=tests/integration` 不新增 red（B 的 pre-existing red 除外）
- [ ] Chrome 复测：超领三列有值且 material_name=组件名；dashboard 单次 init；下拉正常关；库存无 console 报错、合计=16
- [ ] 不引入新的静默错数据（B 的 material_name 来自 PPBOM 而非 SO）

## 部署
代码改完 + 本地验证后，**部署到 dev 是单独一步**（需另行确认），因 dev 跑 `develop`、本地在 `feat/saas-ui-restyle`，需先合并/推送再 deploy。
