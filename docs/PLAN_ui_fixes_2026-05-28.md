# Plan: UI 审查发现 13 项修复（并行 subagent 派发）

## Status: Not Started

## 上下文

源于 `docs/UI_AUDIT_2026-05-28.md` 的 13 条发现。用 sonnet subagent 并行执行，按"文件所有权不重叠"原则切 wave。

## 关键约束（来自 CLAUDE.md）

- 同一 wave 内两个 agent **不能改同一个文件**
- 每个 wave 结束必须 **commit 后**再开下一 wave（防 worktree 清理丢改动）
- 每个 wave 之后跑测试 `pytest --ignore=tests/e2e --ignore=tests/integration`
- 表头模板重构（#9）高风险，单独最后一个 wave

## 文件 → 修复项 倒排索引

| 文件 | 涉及修复 |
|------|---------|
| `src/frontend/dashboard.html` | #1, #3, #4, #7, #8(部分), #9, #10, #11 |
| `src/frontend/inventory.html` | #5, #6(badge map), #11, #12 |
| `src/frontend/static/css/main.css` | #6 (设计 token) |
| `src/frontend/static/js/dashboard.js` | #8 (chip default state), #9 (列定义辅助) |
| 两 HTML head | #2, #13 (cache-buster) |

---

## Wave 1 — 4 路真并行（不同文件，零冲突）

每个 agent 用 `model: sonnet`，无 worktree 隔离（文件不重叠）。

### A1 — Inventory 视觉清理
- **Files**: `src/frontend/inventory.html` (modify)
- **Fixes**: #5 底部图例（参考 dashboard:781-797 的 4 色图例样式），#12 搜索框宽度统一为 `max-w-md`（向 dashboard 看齐）
- **Success**:
  - inventory.html 渲染时底部出现 5 色（外购/自制/委外/虚拟件/成品）图例
  - search input 容器 class 含 `max-w-md`

### A2 — Dashboard 功能 / 视觉小修
- **Files**: `src/frontend/dashboard.html` (modify)
- **Fixes**:
  - #1 用户菜单加 `<a href="/inventory.html">物料库存查询</a>`（在"同步管理"上方）
  - #3 F11 提示位置 `right-[400px]` → `right-[392px]`（chat 384 + 8gap）
  - #4 `toggleFullScreen()` 调用前若 chatOpen 先关闭（或全屏时让 chat push 失效，二选一以最小改动为准）
  - #7 📷 emoji → `<i data-lucide="image" class="w-4 h-4"></i>`（两处：line 177、line 810）
  - #10 ⚠ → `<i data-lucide="alert-triangle" class="w-3 h-3 text-amber-400"></i>`
- **Success**: 各改动定位明确，不改其他逻辑

### A3 — CSS 设计 token
- **Files**: `src/frontend/static/css/main.css` (modify)
- **Fixes**: #6 part 1 — 在 `:root` 加 5 个 ERP 类别语义 token：
  ```css
  --erp-finished: var(--violet-400);      /* ErpClass 9 成品 */
  --erp-self-made: var(--emerald-400);    /* ErpClass 2 自制 */
  --erp-purchased: var(--sky-400);        /* ErpClass 1 外购 */
  --erp-subcontract: var(--amber-400);    /* ErpClass 3 委外 */
  --erp-virtual: var(--slate-500);        /* ErpClass 4 虚拟件 */
  ```
  并把 `.badge-finished` 等已有 badge class 内的硬编码颜色改成引用这些 token。
- **Success**: `grep "var(--violet-400)" main.css` 仅出现在 token 定义和 badge class 内

### A4 — Filter chip 默认 inactive
- **Files**: `src/frontend/static/js/dashboard.js` (modify, 仅 `materialTypes` 初值)
- **Fixes**: #8 默认全 false（用户主动点才生效），同时 `toggleMaterialType` 行为保持，但 `hasActiveFilters()` 逻辑确认 —— 如果"4 个全 false"语义上等于"全选"，要在 `getSortedItems()` 里调整：4 个全 false ⇒ 不筛选；任一 true ⇒ 只显示选中类型
- **Success**: 初次进页面，4 个 chip 都是 inactive 样式，表格显示全部物料

**Wave 1 检查点**:
- Read 每个 agent diff，确认只改预期文件
- `git status` 看 4 个文件都 modified
- 提交：`feat(ui): wave 1 — independent visual + state cleanups (5+ fixes)`

---

## Wave 2 — Header 重构（顺序执行）

### A5 — Nav tabs 替换 user dropdown
- **Files**: `src/frontend/dashboard.html`, `src/frontend/inventory.html` (modify)
- **Fixes**: #11 —— 把两页 header 的 user dropdown 改成 horizontal nav tabs：
  ```
  [QuickPulse] | MTO 查询 · 库存查询 · 同步 · 分析    [用户名 ▾ 退出]
  ```
- **Success**:
  - 两页 header 视觉一致
  - 当前页 tab 高亮（用 emerald 下划线）
  - "用户"按钮简化为头像 + 退出
  - Inventory 死路问题（#1）随之解决，但 A2 里已经先加了 fallback link，留着不会冲突

### A6 — Badge map 统一到 token
- **Files**: `src/frontend/inventory.html` (modify `getErpClassBadge`), `src/frontend/dashboard.html` (修 `.filter-chip-*` 类引用 if 需要)
- **Fixes**: #6 part 2 —— 把 inventory.html line 466-475 的硬编码颜色 map 改用 A3 加的 token，并补 Dashboard chip 同步
- **Success**: 两页同概念同色

### A7 — Cache-buster 同步
- **Files**: `src/frontend/dashboard.html`, `src/frontend/inventory.html`, `src/frontend/sync.html`, `src/frontend/admin.html` (修 head + 底部 script src 的 `?v=` 参数)
- **Fixes**: #2 + #13 —— 全部刷成 `?v=20260528`（今天日期）。**不引入**构建步骤（最小改动），只统一当前值，留 TODO 注释指向"未来用构建脚本注入"
- **Success**: `grep -r "?v=" src/frontend/*.html` 只出现 `20260528`

**Wave 2 检查点**:
- A5 + A6 顺序跑（都改 inventory.html）
- A7 在 A5/A6 之后跑（改 4 个 HTML，但只改 link/script 标签，不改 header）
- 实际上 A7 可以和 A5 并行，但保守起见全顺序
- 提交：`refactor(ui): wave 2 — nav tabs + design token unification + cache-buster sync`

---

## Wave 3 — 表头模板抽取（高风险，单 agent）

### A8 — Sortable th 模板抽取
- **Files**: `src/frontend/dashboard.html` (modify), `src/frontend/static/js/dashboard.js` (modify — 加 sortableColumns 计算属性)
- **Fixes**: #9 —— 把 dashboard.html line 357-548 的 10 个重复 sortable th 抽成一个 `<template x-for="col in sortableColumns">`，依据 `columns[]` 数组动态生成
- **风险预案**:
  - **不**改动 `columns[]` 数组结构（避免触发 CLAUDE.md 警告的索引坑）
  - 只是把 th 模板抽出来，每个 th 仍引用 `col.key`、`colVisible(col.key)`、`getColumnStyle(col.key)`
  - **保留**所有 ARIA 属性、resize handle、排序图标的 emoji-or-icon 完整渲染
  - 不动 `<td>` 模板（td 已经在循环里了，这次只重构 thead）
- **Success**:
  - dashboard.html 行数减少 ~150 行
  - 全部 sortable column 视觉/交互无回归
  - `pytest --ignore=tests/e2e --ignore=tests/integration` 全绿
  - 手动验证：4 个物料类型列排序、resize、列设置 toggle 均工作

**Wave 3 检查点**:
- 单独 commit：`refactor(dashboard): wave 3 — extract sortable column header template (#9)`

---

## 不做的事

- **不**改 `columns[]` 数组结构 / 顺序 / key（CLAUDE.md 警告高风险）
- **不**引入构建工具（vite/esbuild 等）—— 超出范围
- **不**改后端 / SQL / 数据层
- **不**改 `sync.html` / `admin.html` 的功能（仅 #13 cache-buster 顺手刷）

---

## 测试 / 验证

- **Wave 1 后**: `pytest --ignore=tests/e2e --ignore=tests/integration`，检查无单元测试回归
- **Wave 2 后**: 同上
- **Wave 3 后**: 同上 + Read dashboard.html 确认行数减少且模板渲染正确
- **全部完成后**: 启 `uvicorn src.main:app --port 8000`，手动验证 dashboard / inventory 两页所有原功能（搜索、筛选、列设置、导出、照片、chat）

## Acceptance Criteria

- [ ] 13 条 audit 发现全部 close
- [ ] 单元测试 全绿
- [ ] 3 次 commit，每个 wave 一次
- [ ] 无文件冲突 / 无 worktree 残留

---

## 待确认

请回 **"yes / approved / 确认"** 之类的明确字样后我开始派发 Wave 1 的 4 个 sonnet agent。
