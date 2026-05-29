# Plan: 计划跟踪号订单类型 — build-now 功能实现

## Status: 待批准 (Not Started)

> 依据 `docs/MTO_ORDER_TYPE_AND_SKU_READINESS_2026-05-29.md` 的已验证结论。
> **只实现评审认定 build-now、零雷区的一档**。spike 档(出口三件套桥)与 park 档(号码配对/孤儿稽核/chat agent 接线)**本方案明确不做**——它们卡在未铺管道或依赖被推翻的假设,盲做会制造回归。

## Design Spec

### Problem
1. 超领/超发预警里混入了**样品单(Y 类,AY/DY)**噪声(实测约 40 条),稀释信号——**存量 bug**。
2. 看板对**内销单**会显示"06 层全失败"的假阴性(出口的 06↔07 桥不适用内销),误导用户。
3. 知识库 `ontology.py`/`seed_data.py` 断言**"AK 是固定前缀"是错的**(实际 S/K/Y + A/D/W 体系)。
4. 缺一个统一的订单类型解析地基,后续功能都要复用。

### Solution(4 个增量,严格按序、每步跑全量测试)
- **S0 地基**:新建 `src/query/mto_classifier.py` — 纯函数 `classify_mto(mto_number)` → 业务线(A外销/D内销/W瑞弧)+ 订单类型(S完整/K备货/Y样品)+ 子单后缀;健壮处理脏数据(strip/空/未知→未分类)。**TDD**。
- **S1 预警剔样品**(后端,修存量 bug):`cache_reader` 的 over-pick/over-ship 默认剔除 Y 样品;新增 `include_samples=False` 开关 + 响应带 `excluded_sample_count`(防止过滤本身变成新的静默失败)。
- **S2 知识库纠错**:把 `ontology.py`/`seed_data.py` 的"AK 固定前缀"改成正确的 S/K/Y + A/D/W 体系(纯内容修正;注:`knowledge_search` 当前是死代码未接入 agent,本步只修正错误事实、不假装接线)。
- **S3 接口+徽标**:MTO 响应增加 `business_line_label`/`order_type_label`/`is_sample`(handler 按 mto_number 算,纯增量);`dashboard.html` 加小徽标"外销·完整订单"。**前端最后做、最小改动、不动列索引、我逐行审 diff**。

### Files to Modify
| 阶段 | 文件 | 动作 |
|---|---|---|
| S0 | `src/query/mto_classifier.py` (create), `tests/unit/test_mto_classifier.py` (create) | 地基+测试 |
| S1 | `src/query/cache_reader.py`(仅 over-pick/over-ship), `src/api/routers/alerts.py`, `tests/api/test_alerts_and_freshness_endpoints.py`, `tests/unit/test_cache_reader.py` | 剔样品 |
| S2 | `src/agents/knowledge/ontology.py`, `src/agents/knowledge/seed_data.py`, `tests/unit/test_knowledge_store.py`(若有断言) | 纠错 |
| S3 | `src/models/mto_status.py`, `src/query/mto_handler.py`, `src/frontend/dashboard.html`, `tests/unit/test_mto_handler.py` | 接口+徽标 |

### 执行方式(受控,非 fire-and-forget)
- S0 先做并验证绿;之后 S1/S2/S3 文件互斥,**可用 subagent 单波并行,但波结束我复核每个 diff + 跑全量快速套件(`pytest tests/unit tests/api --ignore=e2e --ignore=integration`)**,绿了才算过。
- 前端(S3)我必看 diff。全程**不 commit / 不 push**。

## Test Cases
### Unit
- [ ] `classify_mto`: AS/AK/AY2604007(出口 完整/备货/样品)、DS262027S/DK251003S(内销,尾缀S)、WS2510004、子单 AS2604001-1、前导空格、空/None、未知前缀。
- [ ] over-pick/over-ship: 含 AY/DY 样品行 → 默认剔除且 `excluded_sample_count` 正确;`include_samples=True` 保留。
- [ ] MTO handler: AS/AK/AY 各一例,断言 `business_line_label`/`order_type_label`/`is_sample`。
- [ ] 知识库: 断言不再出现"AK 是固定前缀",出现 S/K/Y 正确描述。
### 回归
- [ ] 现有 718 单测全绿(每阶段后跑)。

## Acceptance Criteria
- [ ] 4 阶段全部完成,快速单测套件 0 失败。
- [ ] 超领/超发预警默认不含样品单,且能查到剔除条数。
- [ ] 看板能显示业务线·订单类型徽标。
- [ ] 知识库不再有"AK 固定前缀"错误表述。
- [ ] 未触碰 spike/park 档任何功能;无 commit/push。
