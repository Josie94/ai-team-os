# Phase 2 编排 · 交付报告

> 负责人：R ｜ 实现日期：2026-11-12 ｜ 阶段：Phase 2 编排（DAG 多智能体并行调度 / 技能系统 / 工具风险注册）
> 基准：《Phase1-数据模型与状态机定稿.md》（Baseline v1）+《Phase2-Phase3-对接确认单》A 部分（A1–A5 已定版）
> 仓库：`Josie94/ai-team-os`（分支 main）

---

## 一、交付内容

### 新增文件

| 文件 | 职责 |
|---|---|
| `backend/app/dag.py` | DAG 图模型：依赖解析、拓扑排序（Kahn）、环检测、就绪集计算、下游闭包 |
| `backend/app/skills.py` | 技能系统 v1：`Skill` 模型、默认技能、注册/启停、展开进节点参数 |
| `backend/tests/test_dag.py` | Phase 2 DAG 场景测试 11 条 |
| `frontend/src/components/DagView.tsx` | DAG 执行图组件（按拓扑层级展示并行节点） |

### 修改文件

| 文件 | 改动 |
|---|---|
| `backend/app/runner.py` | 串行循环 → DAG 调度器；审批断点改为 step 粒度；新增幂等审批、防环检测、断点续跑范围计算 |
| `backend/app/gateway.py` | 规划器支持 `depends_on` / `node_id` / `skill` 输出；离线计划改为带依赖的并行结构 |
| `backend/app/models.py` | 未改动（10 态状态机与既有表结构冻结） |
| `backend/app/seed.py` | 种子数据接入技能注册表 |
| `backend/app/api/routes.py` | 新增 `/api/skills`、`/api/skills/{name}/toggle`；`/api/runs/{id}` 追加 `dag` 字段 |
| `backend/migrations/init.sql` | 新增 `skills` 表 |
| `backend/tests/test_flow.py` | 断点断言改为 Phase 2 语义（run 保持 running） |
| `frontend/src/types.ts` | 新增 `DagNode` / `DagInfo` 类型 |
| `frontend/src/pages/Run.tsx` | 运行详情页接入 DAG 图面板 |
| `frontend/src/styles/extra.css` | DAG 视图样式 |
| `README.md` | 新增「Phase 2 · DAG 编排」章节 |

---

## 二、A1–A5 契约逐条落实

| 契约 | 要求 | 实现 | 验证 |
|---|---|---|---|
| A1① | 节点挂审批时 run 保持 `running` | 断点由 step 粒度承载，run 不迁移状态 | `test_approval_breakpoint_siblings_continue` |
| A1② | 失败默认快速失败 | 任一节点失败 → `run→failed` | `test_fail_fast` |
| A1 总则 | 节点状态映射 10 态，不新增状态 | step 用既有 6 态子集，未加任何状态 | 全量测试无状态枚举变更 |
| A2 | `execute_run(run_id, from_seq)` 签名与语义不变 | 签名未改；断点续跑跳过 done 步骤 | `test_approval_idempotent_and_resume` |
| A3 | 并发槽 `slots_used/slots_total` | 节点启停 ±1，超槽排队 | `test_slot_limit_queues_nodes` |
| A4 | `tools` 表字段冻结 | 未改表结构、未改 `policy.requires_approval` | diff 核对无 tools 变更 |
| A5 | SSE 总线零改动 | 仅新增 `publish` 调用点 | 无 events.py 结构性改动 |

---

## 三、实现要点与设计决策

### 1. 依赖声明位置

沿用 README §七 预留的 `Step.args["depends_on"]`，不新增 `steps` 表字段（避免改动 Phase 1 冻结结构）：

```json
{"node_id": "n2", "depends_on": ["n1"], "skill": "research.summary"}
```

`node_id` 缺省回落 `seq-{seq}`；`depends_on` 支持 `node_id` 或 seq 数字。

### 2. 线性回退（关键兼容决策）

**全图都未声明依赖时，自动按 `seq` 串成链。**

原因：Phase 1 的规划器产出的是线性步骤，若不处理，全部节点会同时就绪 → Phase 1 的串行任务被并行化，行为回归。加回退后，Phase 1 任务与 DAG 任务共用同一套调度器，串行语义完全等价（回归测试通过）。

### 3. 断点续跑范围（A2 语义的 DAG 化）

Phase 1 用 `seq >= from_seq` 过滤续跑步骤。在 DAG 里 **seq 顺序 ≠ 依赖顺序**——断点节点的下游可能 seq 更小，会被漏掉导致永不执行。

实现：取全量步骤建图，续跑范围 = `seq >= from_seq` 的节点 ∪ 其全部下游（传递闭包）。

### 4. 并行下的审批幂等

Phase 1 串行时每个 run 同时只有一个断点；并行时多个节点可能同时命中审批。实现按 `idem_key` 先查后建，避免 `approvals.idem_key` UNIQUE 约束冲突（并行场景实测触发过该缺陷，已修复）。

### 5. 状态机矩阵未改动，但发现一处契约张力 ⚠️

**Baseline v1 的迁移矩阵中 `rejected` 只从 `awaiting_approval` 可达**，而 A1① 要求断点期 run 保持 `running` —— 两者在"驳回"路径上互斥：`running` 没有直达 `rejected` 的合法边。

处理方式（**未改状态机矩阵**，走合法两步迁移）：

```
running → awaiting_approval → rejected
```

中间态仅为状态机要求的过桥；A1① 约束的是"节点挂审批**期间**run 保持 running"，审批决策完成后 run 迁移不违反该约束。

**建议**：若后续认为该过桥不优雅，可在 Baseline v1 changelog 中给矩阵补一条 `running → rejected` 边，由唐建淇同步 `state_machine.py` / `init.sql` / 前端 `StatusPill`。

### 6. 技能系统 v1 边界

本期只做**技能定义与被节点引用**；技能市场（浏览/分享/安装）属 FYR 的 P2 迭代，已通过 `GET /api/skills` 预留消费接口。

技能禁用后，引用它的节点明确报错（"技能不可用: xxx"），不静默降级。

---

## 四、验收结果

| 验收项 | 结果 |
|---|---|
| Phase 1 五条回归全绿（串行路径零回归） | ✅ |
| DAG 场景 11 条全绿 | ✅ |
| 随机顺序执行稳定（连跑 3 轮 ×16 条） | ✅ |
| 前端 `tsc -b && vite build` 通过 | ✅ |
| 含并行/汇聚的 DAG 端到端跑通 | ✅ |
| 并发槽约束生效（峰值不超槽） | ✅ |
| 节点级审批：挂起时兄弟节点继续、run 保持 running | ✅ |
| 批准后续跑不重算（已完成步骤 duration 不变） | ✅ |
| 幂等：重复审批决策返回 409 | ✅ |
| 快速失败：节点失败 → run→failed | ✅ |
| 技能：定义/引用/展开/禁用报错 | ✅ |
| 环检测：成环图被拒绝 | ✅ |
| 状态机矩阵未改动 | ✅ |

**测试命令**：
```bash
cd backend && python3 -m pytest tests/ -q     # 16 passed
cd frontend && pnpm build                       # 通过
```

---

## 五、待办与交接

### 交给唐建淇的事项

1. **Baseline v1 changelog**：`running → rejected` 迁移边是否补（见第三节第 5 点）；
2. `migrations/init.sql` 新增的 `skills` 表需在 Postgres 环境同步执行（已有 `CREATE TABLE IF NOT EXISTS`，可重复执行）；
3. FYR 的 B2（audit payload 约定）：本期 audit payload 已统一携带 `run_id` + `step`（step 级事件），run 级事件未强制带 step 快照。

### 留给 Phase 3 / P2 迭代的接口

- `GET /api/skills` —— 技能清单，FYR 做技能市场时的消费入口；
- `GET /api/runs/{id}` 的 `dag` 字段 —— 节点 / 依赖边 / 拓扑序 / 最大并行宽度，前端可直接渲染图。

### 未纳入本期（已在任务梳理中列为待决）

- 失败策略的"跳过继续"配置（A1② 定版为快速失败，本期未做）；
- `tools.slot_cost`（A3 定版为不加）；
- `node.skipped` / `slot.exhausted` 新事件类型（前端靠重拉，可晚加）；
- 完整智能体池管理（本期节点绑定 agent 仍为角色 profile 轻量实现）。
