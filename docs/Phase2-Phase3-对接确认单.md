# Phase 2 / Phase 3 对接确认单（A 部分已定版）

> 发起：唐建淇（Phase 1 交付方）｜日期：2026-11-09｜**v1.1 更新：2026-11-09 15:42**
> 目的：把评审做成异步确认——R、FYR 各自核对与自己阶段相关的接口约定，**逐条回复“确认”或写异议**，11/11 前反馈。有异议的部分 Phase 1 还有 2 天窗口可以改，11/13 定版后改动走 changelog。
> 基准：《Phase1-数据模型与状态机定稿.md》（Baseline v1）＋ 已验收实现（资料库源码 zip）。

## 状态总览

| 部分 | 对象 | 状态 | 结论 |
|---|---|---|---|
| A1–A5 | R | ✅ **已定版（2026-11-09 14:28）** | R 回复「没问题」，全部按默认方案通过 |
| B1–B3 | FYR | ⏳ 等待反馈（截止 11/11 18:00） | 逾期未回复视为默认接受 |

**A 部分定版结论**（对 Phase 2 即刻生效，后续改动走 changelog）：
- A1①：DAG 部分节点挂审批时，run 级保持 `running`（step 粒度承载断点）
- A1②：失败策略默认**快速失败**（run→failed）
- A2–A5：`execute_run(run_id, from_seq)` 入口契约、并发槽 `slots_used/slots_total`、工具风险注册表字段、SSE 事件总线（Redis 多 worker）均按现状冻结

**真实模型验收决策（2026-11-09，当日两次更新）**：DeepSeek Key 欠费(402)后一度按「降级模式已验收」定案；**17:35 改接入智谱 GLM-4-Flash（OpenAI 兼容端点）并完成真实模型验收**——SSE 流式对话 + 审批闭环（含两次断点：中风险落盘 / 高风险外发）真实模型 6/6 步跑通，交付物 2705B 实质内容 + sha256。DeepSeek Key 保留模型中心可随时切回。

---

## A. 给 R：Phase 2 编排对接确认（5 条）

### A1. DAG 节点状态映射到 10 态

Phase 2 的 DAG 节点生命周期建议映射（映射表不引入新状态，避免前端/状态机双改）：

| DAG 概念 | 映射到 10 态 | 说明 |
|---|---|---|
| 节点入队 | `queued` | step 级沿用 |
| 节点执行中 | `running` | 多节点并行 = 多个 step 同时 running，run 仍单一状态 |
| 节点命中审批策略 | `awaiting_approval` | step 级挂起，其他就绪节点**继续调度**（run 级状态建议保持 running，由 step 粒度承载断点）|
| 节点失败 | `failed` | run 级策略：默认快速失败（run→failed），是否改成“跳过继续”由 Phase 2 定 |
| 全图完成 | `completed` | done_steps == total_steps 且无 pending |

**需确认**：① run 级在部分节点挂审批时保持 `running`（而非 `awaiting_approval`）是否接受？② 失败策略默认值选哪个？

### A2. 执行层入口契约（保持不变）

```
execute_run(run_id: str, from_seq: int = 1)
```
- 断点续跑语义：`from_seq` 起跑，`status == done` 的步骤跳过不重算；
- Phase 2 由 DAG 调度器替换内部串行循环，**签名与续跑语义不得变更**（对话、审批、REST/SSE 全链路依赖它）。

**需确认**：签名是否够用？若 DAG 需要按节点恢复而非 seq，请在本单回复，11/13 前可改。

### A3. 并发槽消费方式

`runs.slots_used / slots_total`（默认 1/16，原型口径 3/16 演示值）已落库。建议 Phase 2：调度器每个节点启动时 `slots_used += 1`、结束 `-= 1`，超槽排队；槽大小 = 节点数上限。

**需确认**：是否需要在 tools 表加 `slot_cost` 字段（重工具占多槽）？

### A4. 工具风险注册表扩容

Phase 2 你接管工具风险管控。当前 schema：`tools(name, label, risk, whitelist, description, enabled)`，审批判定入口 `policy.requires_approval(tool, args)`。新增工具**只插数据不改代码**——加字段（如 `approval_timeout`、`allowed_scopes`）提出来，我 11/13 前加。

**需确认**：现有字段是否覆盖 Phase 2 需求？

### A5. SSE 事件总线（已支持多 worker）

`REDIS_URL` 一配，各 worker 经 Redis 频道 `ai-team-os.events` 扇入本地队列。DAG 调度器只需在状态落库后 `events.publish(event, {...run_id...})`，前端零改动。事件清单见定稿文档 §二。

**需确认**：事件类型是否需要为 DAG 扩（如 `node.skipped`、`slot.exhausted`）？

---

## B. 给 FYR：Phase 3 前置确认（3 条）

### B1. 证据链挂 pgvector 的表设计（草案，供 Phase 3 评审起点）

```sql
CREATE TABLE kb_chunks (
  id          BIGSERIAL PRIMARY KEY,
  source_type VARCHAR(32) NOT NULL,   -- deliverable / audit / message
  source_id   VARCHAR(64) NOT NULL,   -- deliverables.filename / audit_events.seq / messages.id
  run_id      VARCHAR(24),
  chunk_text  TEXT NOT NULL,
  embedding   vector(1024),           -- 维度按 Phase 3 选型定
  meta        JSONB DEFAULT '{}'::jsonb,
  created_at  TIMESTAMP DEFAULT now()
);
CREATE INDEX ON kb_chunks USING hnsw (embedding vector_cosine_ops);
```

Phase 1 已保证：deliverables 带 `sha256` + 落盘路径；audit_events 带 `(run_id, seq)` 有序 + payload JSONB——两者就是召回源的“证据指针”。

**需确认**：source_type/source_id 这个指针粒度够不够做引用追溯？

### B2. audit payload 格式约定

当前 payload 是自由 JSONB，事件类型见定稿文档。若 Phase 3 要从 audit 直接做“行动轨迹召回”，建议 Phase 2 起约定：payload 统一包含 `step`（int）与 `run_id`（总线层已注入）。Phase 1 的 12 种事件均已带 `run_id`，`step` 在 step 级事件有、run 级无。

**需确认**：是否需要 run 级事件也强制带 step 快照（如 `done_steps`）？

### B3. 记忆流水线挂接点

Phase 1 的对话表 `messages(conversation_id, role, agent, content, run_id)` 可直接作为记忆候选源；人工确认环节复用**审批中心 UI 与 approvals 表**（status 加 `memory_candidate` 语义或独立表，Phase 3 定）。

**需确认**：复用审批交互还是独立记忆确认页？

---

## 反馈方式

直接在云端任务「Phase 1 MVP」对应评论下逐条回复（A1–A5 / B1–B3），格式：`A1 确认` 或 `A1 异议：…`。11/11 18:00 前反馈即可；不回复视为默认接受，11/13 定版。
