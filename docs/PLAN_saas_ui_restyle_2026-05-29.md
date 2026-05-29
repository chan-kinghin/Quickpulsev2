# Plan: 前端改成简约 SaaS 风格（明亮白底 + 去花哨）

## Status: ✅ Complete (branch `feat/saas-ui-restyle`, 2 commits 44507b1 + 69fc698) — NOT pushed/merged/deployed, 等用户验收

### 验收结果 (2026-05-29)
- 6 页 Playwright 截图确认为亮色 SaaS 风(login/dashboard+data/alerts/sync/admin/inventory)
- WCAG AA 对比度:除提示层外全部 AA 通过;`slate-500` 提示层 #79838f = AA-large(3.85),`slate-400` 标签 = AA(4.76);400>500 对比排序已修正
- e2e:工作区失败集合与「改动前基线」**逐项相同**(20败/37过/9跳)→ 零回归。20 个失败全为历史遗留(8 个 `*_live` 需真实后端;其余为导航统一前的结构漂移)
- 单测:本机临时 venv 缺金蝶 SDK(`k3cloud_webapi_sdk`)无法跑;前端改动不涉及 Python
- 仅提交 9 个 `src/frontend/*` 文件;工作区里并存的 MTO 订单类型后端改动(mto_handler/alerts/mto_status/ontology/seed_data + 多个 test)**未触碰、未提交**(非本次工作)
- dashboard.html 内含一处**预存**的 MTO 业务线·订单类型徽标(并发工作所加,非本次撰写),已原样保留

## 背景

用户反馈：当前 UI「太花哨」，希望「更像 SaaS、简约一点」。
经审计（6 页全量 + 共享 CSS），花哨来源已量化：

- **5 种饱和强调色装饰化滥用**：emerald(89) 是合法品牌色，但 rose(45)/amber(32)/sky(13)/violet(5) 被当装饰用 —— 徽章、筛选 chip、列底色条、树节点边框、状态点、数字、表头全在上色。
- **近纯黑底 `#0a0a0b` + 霓虹强调** 的组合本身就「亮」，且需要发光/重阴影来分层，进一步放大花哨感。
- Dashboard 单页就背了 **17 个动画类 + 4 阴影 + 4 ring**（含常驻脉冲点、shimmer 骨架、shake）。

**已确认决策（2026-05-29，用户选择）**：
1. **方向 = 明亮白底（Light，Stripe/Notion/飞书 感）**
2. **范围 = 仅视觉降噪**（不改布局、不改交互、不改数据逻辑、不动信息架构）

---

## Design Spec

### 核心设计原则（一条规则解决 ~90% 问题）

> **颜色承担含义，灰阶承担结构。**

- **emerald 翠绿** = 唯一品牌/交互色 → 只用于：主按钮、当前 nav tab、聚焦环、链接、选中态。每屏 ≤ 3 处。
- **amber 琥珀** = 仅「警示」（数据滞后、同步中、真正的 warning）。
- **rose 玫红** = 仅「破坏性 / 超量 / 真错误」（超领超发数值、清缓存确认、错误条、5xx）。
- **violet 紫 + sky 蓝 = 整体删除**（重映射为中性灰）。
- 一切「数字、分类徽章、列分组、健康/空闲/2xx 默认态」→ 中性灰。颜色只在「用户需要行动时」出现。

### 关键技术约束（必须遵守，否则静默失效）

> 这是本计划最重要的一节。审计 + 实测共同确认。

1. **`tailwind.min.css` 是预编译裁剪包（23KB / 249 selectors）**。`bg-white`、`bg-slate-100/200`、`text-slate-800/900`、`shadow-sm/md`、`rounded-md`、`ring-1`、新增的 `hover:`/`focus:` 变体 **全部不在包里**，写进 HTML 会**静默无效**（项目 memory `frontend-tailwind-precompiled-missing-classes.md` 记录在案；HTML line 627/888 也有注释自证）。
2. **编译出的 utility 是硬编码 RGB，不是 CSS 变量**：
   `.bg-slate-900{background-color:rgb(15 23 42/var(--tw-bg-opacity,1))}`
   → 改 `:root` 里的 `--slate-900` **对内联 `bg-slate-900` 完全无效**。纯「token 反转」方案不可行。
3. **`main.css` 在 `tailwind.min.css` 之后加载**（line 19 > line 11）。Tailwind utility 是单类特异性，所以在 `main.css` 里**重写同名 utility 类，靠源码顺序即可覆盖，无需 `!important`**。
4. **结论 = 采用「Light 皮肤覆盖层」方案（不引入构建工具）**：在 `main.css` 追加一段覆盖层，重写「用到的」中性 slate utility（暗→亮反转）+ 修正保留强调色的白底 AA 对比 + sky/violet 重映射为灰 + 组件类覆盖。装饰性强调色的「按元素去除」走 HTML sweep。
   - **不重建 bundle**（Node 虽可用，但无 config/package.json，全量重建会改变 249-selector 集合，风险高于「仅视觉/最低风险」诉求）。重建 bundle 列为未来技术债，不在本次范围。

### 明亮白底 token 表（最终值；已修正对比度顺序）

中性 slate 阶梯（在 `main.css` 重写 utility 值，**保持原暗色主题的对比度排序**）：

| Utility（保持类名不变） | 暗色原值 | → 白底新值 | 用途 |
|---|---|---|---|
| `bg-slate-950` | #0a0a0b | **#ffffff** | 页面底 |
| `bg-slate-900` | #111113 | **#f8fafc** | 卡片/面板 |
| `bg-slate-800` | #1e1e21 | **#f1f5f9** | hover 面/下拉/面板头 |
| `bg-slate-700` | #2d2d31 | **#e2e8f0** | 填充 chip / 分隔 |
| `bg-slate-600` | #4a4a50 | **#cbd5e1** | 较强填充 |
| `border-slate-800` | — | **#e7ebf0** | 发丝级边框（主力） |
| `border-slate-700` | — | **#e2e8f0** | 默认 1px 边框 |
| `border-slate-600` | — | **#cbd5e1** | hover/强调边框 |
| `text-slate-50` | #f8fafc | **#0f172a** | 标题/最高对比数据 |
| `text-slate-200` | #e2e8f0 | **#334155** | 强正文/合计/数值 |
| `text-slate-300` | #c9cdd4 | **#475569** | 次正文/下拉项 |
| `text-slate-400` | #9ca3af | **#64748b** | 标签/列头/次要（最常用 108×，AA on white） |
| `text-slate-500` | #6b7280 | **#94a3b8** | 提示/占位/更弱（注意：比 400 更浅，保持原排序） |
| `text-slate-600` | #4a4a50 | **#cbd5e1** | 极弱/禁用 |

> ⚠ **对比度修正点**：设计 agent 自动生成的表把 400/500 顺序弄反了（会让 108 处标签在白底过淡）。本表已按「实际使用语义」修正：`slate-400` 比 `slate-500` 更深更可读。实现时用 Playwright + 对比度检查复核。

强调色（白底 AA 修正 + 删除装饰色）：

| Utility | 处理 |
|---|---|
| `text-emerald-400` (#34d399) | 白底不可读 → 重写为 **#047857**（链接/active）；但**数据数字上的 emerald 一律 HTML sweep 改成 `text-slate-200`**（见下） |
| `bg-emerald-500` / `bg-emerald-600` | 主按钮 → 统一 **#059669**（hover `bg-emerald-500`→#10b981，包内已有） |
| `text-amber-400` (#fbbf24) | 白底 → **#b45309**（仅警示值） |
| `bg-amber-500` 等 | 状态点/进度 → **#d97706** |
| `text-rose-400` (#fb7185) | 白底 → **#b91c1c**（仅超量/错误值） |
| `bg-rose-500` / tints | 错误条/确认 → **#dc2626** + 浅 tint |
| `text-sky-400` / `bg-sky-*` / `text-violet-400` / `bg-violet-*` | **重写为中性灰**（#475569 / #64748b / #e2e8f0），装饰色消失，无需改 HTML |
| `--erp-finished/self-made/purchased/subcontract` | 全部 → **#64748b**（单一灰点）；`--erp-virtual` → **#94a3b8** |

阴影 / 圆角（2 级）：

- `--shadow-1: 0 1px 2px 0 rgb(15 23 42 / .04)`（静置卡片/输入）
- `--shadow-2: 0 4px 12px -2px rgb(15 23 42 / .10)`（浮层：下拉/搜索历史/模态/chat 侧栏）
- 删除所有 `0 0 6px` 发光、`-4px 0 24px` 侧栏重影、`shadow-lg/shadow-xl`、`glow-emerald` 4px 双环。
- `--radius-sm: 4px`（徽章/chip/输入）、`--radius-md: 6px`（按钮/卡片/下拉）。`rounded-xl`/`rounded-full`（chip）降到 `--radius-md`；`rounded-full` 仅留头像/状态点。

### 组件类覆盖（写在 main.css，全 6 页生效）

| 组件 | 改动 |
|---|---|
| `.badge-*`（5 色）| 统一中性：bg `#f1f5f9` / text `#64748b` / border `#e2e8f0` / radius sm；可选 6px 左灰点保留扫读 |
| `.filter-chip-*`（含 4 个 per-type）| active 统一中性：bg `#f1f5f9` / text `#0f172a` / border `#cbd5e1` |
| `.nav-tab-active` | 安静：text emerald-600 + bg `#ecfdf5`（薄荷洗）或 2px 下边框，去掉饱和 pill |
| `.glow-emerald:focus` / `.filter-search input:focus` | 单环：border emerald-500 + `box-shadow:0 0 0 3px rgb(16 185 129/.15)`，删 slate-950 偏移环 |
| `.dropdown-menu` / `.search-history` / `.chat-sidebar` | 仅用 `--shadow-2`；chat 侧栏去重影、靠左边框 |
| `.skeleton` | 去 shimmer keyframe，改静态 `background:#f1f5f9` |
| `.resize-handle` / `.resize-guide-line` | 去 emerald 渐变 + sky 发光，改中性灰 1px |
| `.tree-node/.tree-root/.tree-sales/-production/-purchase` | 统一 `#f8fafc` 面 + `#e2e8f0` 边；root 去发光（用 `#cbd5e1` 边） |

### 按页 HTML sweep（仅去装饰性强调色，不动结构；定位来自审计）

> 这些是「数字/分类上的颜色」类，无法在 utility 层处理（否则会连带改到链接/按钮），必须按元素改。

- **dashboard.html + dashboard.js**：删列底色条 `bg-emerald-950/10`/`bg-sky-950/10`；表头/合计/排序箭头 emerald/sky → slate；header 颜色 map（dashboard.js:38-46）→ 中性；borderClasses 去彩色；新鲜度点去 `animate-pulse`、文字去 per-state 上色；FAB `bg-emerald-600 rounded-full shadow-lg` → `bg-slate-800 border rounded shadow-sm`（仅外观，不改功能）；缩略图选中 `ring-emerald-500` → `ring-slate-400`；状态 chip rose 误用（隐藏已关闭）→ 中性；删常驻 F11/ESC 浮窗 pill 背景（保留文字提示）；手绘 SVG → lucide；去 `tracking-wide`。
- **inventory.html**：5 色徽章靠组件层已变灰 → 删底部颜色图例；match-source chip（violet/amber）→ 中性；数量/合计/数量表头 emerald → slate；ErpClass 筛选按钮 active emerald → 中性；面板头去填充/图标；`结果较多` amber → 纯灰文字。
- **alerts.html**：tab active 双色（amber/rose）→ 单一中性下划线；header alert-triangle 去色或灰；rose/amber 整块 tint banner → 中性面 + 仅图标着色；MTO 号 emerald → slate mono；超量数值保留单色（值上色、表头中性）；空态 64px emerald 盾 → 小灰图标；spinner 中性；ⓘ → lucide；去 `tracking-wide`。
- **sync.html + sync.js**：空闲点/文字去 emerald（空闲=灰、运行=amber 才脉冲）；`glow-emerald` 已组件层修；清缓存按钮默认中性 ghost、仅确认步 rose；warm-cache amber → 中性；命中率数字 emerald → slate；新鲜度健康态去庆祝色；per-table 点：fresh=灰、stale=amber；进度条 emerald 收敛；历史状态徽章（statusBadgeClass）成功态→中性、仅失败/运行着色；去 `tracking-wide`。
- **admin.html**：5 个 KPI 数字 emerald → slate-50；时间范围 active pill emerald → 中性；`rounded-xl` → `rounded-lg`；排序箭头 emerald → slate；HTTP method chip sky → 中性 mono；状态码 4 色 → 仅 4xx/5xx 着色；时间线条 emerald → 灰/低饱和；spinner 中性；去单卡 globe 图标不一致；30s 自动刷新改静默（不触发全页 spinner）；去 `tracking-wide`。
- **index.html**：`glow-emerald` 已组件层修；登录按钮 emerald 收敛（组件层 + 可选）；删 dead `bg-dots` 类；wordmark 去 `tracking-wide`、缩小；错误条 rose 收敛（组件层）。

### Files to Modify

```
src/frontend/static/css/main.css        (foundation — 皮肤覆盖层 + 组件覆盖)   [Wave 0]
src/frontend/dashboard.html             (sweep)                               [Wave 1]
src/frontend/static/js/dashboard.js     (header/border color maps)            [Wave 1]
src/frontend/inventory.html             (sweep)                               [Wave 1]
src/frontend/alerts.html                (sweep)                               [Wave 1]
src/frontend/sync.html                  (sweep)                               [Wave 1]
src/frontend/static/js/sync.js          (statusBadgeClass)                    [Wave 1]
src/frontend/admin.html                 (sweep)                               [Wave 1]
src/frontend/index.html                 (sweep)                               [Wave 1]
+ cache-buster `?v=` 全部刷新为 20260529
+ main.css 顶部加大段注释，解释「皮肤覆盖层 / 类名语义不变值变亮」给后续开发者
```

### 实施波次（文件所有权不重叠，逐波 commit；可用 Workflow 并行 Wave 1）

- **Wave 0（单 owner，基础层）**：`main.css` 皮肤覆盖层 + 组件覆盖。**必须先 commit**，页面才会整体变亮。
- **Wave 1（6 路并行，每文件一 agent，零重叠）**：6 个 HTML（+ dashboard.js / sync.js 各归属对应页 agent）做装饰色 sweep。
- **Wave 2（验证）**：Playwright 逐页截图 + 对比度检查 + 单测全绿 + grep 校验。

---

## Test Cases

### 自动化 / 静态校验
- [ ] `pytest --ignore=tests/e2e --ignore=tests/integration` 全绿（不应受 UI 影响；注意 main 上已有 3 个 **预存** red：`test_mto_endpoints.py` use_cache 漂移，与本次无关）。
- [ ] `grep -rE '(text|bg|border)-(violet|sky)-' src/frontend/*.html` → 装饰用 sky/violet 已清零或仅余被组件层中性化的（结果记录）。
- [ ] `grep -c 'animate-pulse' dashboard.html sync.html` → 空闲/健康态脉冲已移除。
- [ ] 不得新增 bundle 外的 Tailwind 类：sweep 后 `grep -rE '(rounded-md|shadow-sm|shadow-md|ring-1|bg-white|bg-slate-100)' src/frontend/*.html` 命中数 = 0。

### Playwright（项目规定用 Playwright，非 Chrome MCP）
- [ ] 6 页逐页截图（dashboard 含展开一个真实 MTO、inventory 含一次搜索、alerts 两个 tab、sync 含新鲜度卡、admin、index）。
- [ ] WCAG AA 对比度检查：正文/标签文字 vs 白底 ≥ 4.5:1（重点验 `text-slate-400` 标签与 `text-slate-500` 提示，防对比度反转）。
- [ ] 交互无回归：搜索、筛选、列设置、排序、列宽拖拽、导出、照片灯箱、chat 开合、同步触发。

### 人工验收（给用户看）
1. 本地 `uvicorn src.main:app --port 8000` 起服务。
2. 截图发给用户对比「改前 vs 改后」，确认「不花哨 / 像 SaaS」达标。
3. 用户确认后再合并 / 部署。

---

## Acceptance Criteria

- [ ] 全站明亮白底，emerald 为唯一强调色，sky/violet 装饰色消失，amber/rose 仅状态用。
- [ ] 无发光、无渐变（功能性骨架除外且静态）、阴影 ≤ 2 级、圆角统一。
- [ ] 数据数字/分类徽章/列分组/健康态 = 中性灰；颜色只标异常。
- [ ] 所有原功能与布局不变（仅视觉）。
- [ ] 单测全绿（除预存无关 red）；Playwright 6 页通过 + AA 对比度达标。
- [ ] `main.css` 顶部有清晰注释解释覆盖层策略；cache-buster 已统一刷新。

---

## 不做的事（范围边界）

- ❌ 不改信息架构（不收按钮进 … 菜单、不做 Filters 弹层、保留现有控件布局）—— 用户选「仅视觉降噪」。
- ❌ 不重建 `tailwind.min.css` / 不引入 Tailwind 构建链（列为未来技术债）。
- ❌ 不改后端 / SQL / 数据层 / `factory.py`（当前工作区那处 `M factory.py` 与本次无关，不纳入）。
- ❌ 不改 `columns[]` 数组结构（CLAUDE.md 标记的高风险索引坑）。

---

## 分支 / 工作树建议

- 建议在 worktree 隔离：`git worktree add ../Quickpulsev2-saas-ui -b feat/saas-ui-restyle`（从 main 切出；当前未提交的 `factory.py` 留在主工作区，不带入）。
- 逐波 commit；Wave 0 先合（基础层），再起 Wave 1 的 6 个并行 agent；每波后跑测试（遵守 CLAUDE.md 子代理波次门禁）。

---

## ⛔ 待批准

请回复明确字样（**yes / approved / 确认 / 同意 / 继续**）后我开始实施。
同时请确认：**(a) 分支名 `feat/saas-ui-restyle` + worktree 是否 OK**（或你想直接在当前分支做）；**(b) 是否要我用 Workflow 并行跑 Wave 1 的 6 个 agent**（ultracode 已开，默认会）。
