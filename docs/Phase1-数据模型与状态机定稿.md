# Phase 1 数据模型与 10 态状态机 · 定稿

> 状态：**基准版（Baseline v1）**，2026-11-09 定稿
> 依据：前端原型《前端页面设计.html》（Tasks · 10 states）+ Phase 1 已验收实现
> 说明：mmmm 的完整规划文档至今未交付，本文件按原型与实现**先行定稿**，作为 Phase 2 对接的唯一基准。规划文档到位后做一次 diff，仅采纳与原型语义一致的差异。

---

## 一、10 态状态机

### 1.1 状态定义

| 状态 | 中文 | 语义 | 允许迁出 |
|---|---|---|---|
| `queued` | 排队 | 已创建待调度；Step 层复用同语义表示"已批准待重跑" | running / cancelled / archived |
| `running` | 执行中 | 执行器持有中（Phase 1 单智能体串行；Phase 2 由 DAG 调度器接管） | awaiting_approval / awaiting_input / paused / completed / failed / cancelled |
| `awaiting_approval` | 等待审批 | 命中审批策略挂起，**断点不执行**；断点信息落库（step_id/seq） | running / rejected / cancelled / failed |
| `awaiting_input` | 等待输入 | 审批"请求修改"转入；补充输入后从当前步骤续跑 | running / cancelled / failed |
| `paused` | 已暂停 | 人工暂停；恢复从断点继续，不重算 | running / cancelled / archived |
| `completed` | 已完成 | 全部步骤 done，交付物+sha256 归档 | archived |
| `failed` | 失败 | 执行异常，error 落库可见 | archived / queued（重试） |
| `cancelled` | 已取消 | 人工取消 | archived |
| `rejected` | 已驳回 | 审批驳回，运行终止（区别于 failed：由人决策产生） | archived |
| `archived` | 已归档 | 终态，可回填归档 | —（无迁出） |

**硬约束**：
1. 状态**只能由服务端状态机迁移**（`app/state_machine.py::transit`），非法迁移抛 `IllegalTransition`，前端不允许本地推导状态；
2. Task 与 Run 共用此状态机（Task 状态跟随其最新 Run 联动迁移）；
3. Step 层使用子集：`queued / running / awaiting_approval / awaiting_input / done / failed / skipped`（Step 无 paused/cancelled 等运行级状态）。

### 1.2 迁移矩阵（行=当前，列=目标，✓=合法）

| | running | await_appr | await_input | paused | completed | failed | cancelled | rejected | archived |
|---|---|---|---|---|---|---|---|---|---|
| **queued** | ✓ | | | | | | ✓ | | ✓ |
| **running** | | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| **awaiting_approval** | ✓ | | | | | ✓ | ✓ | ✓ | |
| **awaiting_input** | ✓ | | | | | ✓ | ✓ | | |
| **paused** | ✓ | | | | | | ✓ | | ✓ |
| **completed** | | | | | | | | | ✓ |
| **failed** | ✓(经queued) | | | | | | | | ✓ |
| **cancelled** | | | | | | | | | ✓ |
| **rejected** | | | | | | | | | ✓ |
| **archived** | | | | | | | | | |

> 注：`failed → queued → running` 为重试路径（failed 不可直接迁 running）。

### 1.3 关键状态迁移触发（审批闭环）

```
running --命中高风险/白名单外工具--> awaiting_approval   (创建 Approval, idem_key 幂等)
awaiting_approval --approve--> running                  (从落库断点 step 断点续跑，不重算)
awaiting_approval --reject--> rejected                  (运行终止, audit 留痕)
awaiting_approval --revise--> awaiting_input            (转人工补充输入)
awaiting_input --provide_input--> running               (当前步骤重新排队执行)
```

**幂等规则**：同一 `(run_id, step_seq, tool)` 仅允许一条 pending 审批（`approvals.idem_key` UNIQUE）；重复决策返回 409。

---

## 二、数据模型（PostgreSQL 16）

完整 DDL 见仓库 `backend/migrations/init.sql`（与 ORM `app/models.py` 字段级对齐，本地开发 SQLite 自动建表，切 Postgres 先跑此文件）。要点：

| 表 | 职责 | 关键字段/约束 |
|---|---|---|
| `tasks` | 任务 | `status` 走 10 态；`progress` 0-100 |
| `runs` | 执行实例 | `pending_approval_id` 指向当前断点；`slots_used/slots_total`（3/16 并发槽，为 Phase 2 DAG 预留） |
| `steps` | 步骤 | `(run_id, seq)` 有序；`args JSONB` 含断点续跑上下文（user_input、saved 路径） |
| `approvals` | 审批断点 | `idem_key` UNIQUE（幂等）；`risk` high/mid/low；`detail JSONB` |
| `tools` | 工具风险注册表 | `risk` 分级 + `whitelist JSONB`（中风险白名单内免审） |
| `model_providers` | Model Gateway 供应商档案 | OpenAI 兼容 `base_url`/`model`/`api_key`；`is_default` |
| `audit_events` | 审计事件流 | `(run_id, seq)` 有序；type 见下 |
| `deliverables` | 交付物 | `sha256` 证据链；落盘路径 |
| `conversations` / `messages` | 对话 | `messages.run_id` 关联"转为任务"的运行 |

### 审计事件类型（audit_events.type）

`run.created` / `run.started` / `run.completed` / `run.failed` / `run.cancelled` / `run.input_provided`
`step.started` / `step.completed`
`approval.requested` / `approval.approved` / `approval.rejected` / `approval.revise_requested`

（SSE 总线 `app/events.py` 在上述事件**落库后**广播同名信号；前端收到信号后重拉数据，SSE 不承载数据。）

---

## 三、与 Phase 2 的接口约定

1. **执行层入口不变**：`execute_run(run_id, from_seq)` 是唯一执行入口；DAG 调度器替换内部实现（串行→并行编排），签名与断点续跑语义保持；
2. **并发槽**：`runs.slots_used / slots_total` 已落库，Phase 2 调度器直接消费；
3. **事件总线**：单进程内存队列（`app/events.py`）；多 worker 部署换 Redis pub/sub，`publish/subscribe` 接口签名不变；
4. **状态机为唯一事实源**：DAG 节点状态映射到 10 态，不允许旁路写 `status` 字段；
5. **审批断点协议**：DAG 图中任何节点命中工具风险策略时，同样落 `approvals` 表（幂等键规则不变），从节点断点恢复。

---

## 四、变更流程

- 本文件 = Phase 1 交付的**基准版**；
- mmmm 规划文档到位后：逐条 diff 状态名/字段名/迁移边，**仅接受与原型语义一致或明显更优的差异**，修订需在本文件追加 changelog 并同步 `state_machine.py` / `init.sql` / 前端 `StatusPill`；
- Phase 2（R）开工前以本文件为准建 DAG 状态映射，避免口头约定。
