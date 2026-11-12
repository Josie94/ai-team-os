# AI Team OS · Phase 1 MVP → Phase 2 编排

企业内网 AI 多智能体协作平台。Phase 1 交付「对话 → 单智能体执行 → 审批断点 → 断点续跑」最小闭环；
**Phase 2 把内部串行循环替换为自研 asyncio DAG 调度器**，支持多智能体并行调度、技能系统与工具风险注册。

前端视觉与信息架构来自 `mmmm` 的前端原型（项目资产《前端页面设计.html》），样式与图标直接复用原型，未重画。

## 一、闭环长什么样

```
用户在对话里提需求
  → 命中"工作型"意图 → 创建 Task + Run + Step 计划
  → DAG 调度器按依赖关系并行执行（并发槽受限）
  → 遇到 feishu.message（高风险）→ 创建 Approval，节点挂起（run 保持 running，兄弟节点继续）
  → 审批中心「通过并继续」→ 从落库的 step 断点继续，不重算已完成步骤
  → completed + 交付物（Markdown，带 sha256 证据链）+ audit 事件流
```

状态机 10 态：`queued / running / awaiting_approval / awaiting_input / paused / completed / failed / cancelled / rejected / archived`。
**状态只由后端迁移**，非法迁移抛 `IllegalTransition`（`backend/app/state_machine.py`）。

## 二、目录

```
ai-team-os/
├─ backend/
│  ├─ app/
│  │  ├─ models.py          Task / Run / Step / Approval / Tool / ModelProvider / AuditEvent / Deliverable / Conversation / Message
│  │  ├─ state_machine.py   10 态状态机（服务端强约束）
│  │  ├─ policy.py          工具风险注册表 + 白/灰名单判定
│  │  ├─ gateway.py         Model Gateway（OpenAI 兼容，无 key 自动降级）
│  │  ├─ dag.py             Phase 2：DAG 图模型 / 拓扑排序 / 环检测 / 就绪集
│  │  ├─ skills.py          Phase 2：技能系统 v1（模板 + 工具组合 + 参数预设）
│  │  ├─ runner.py          DAG 调度器 + 审批断点 + 断点续跑
│  │  ├─ api/routes.py      REST API
│  │  └─ seed.py            工具/技能/模型档案/示例会话/示例任务
│  ├─ migrations/init.sql   Postgres 16 + pgvector 建表
│  └─ tests/
│     ├─ test_flow.py       Phase 1 闭环回归（5 条）
│     └─ test_dag.py        Phase 2 DAG 场景（11 条）
├─ frontend/
│  └─ src/
│     ├─ styles/app.css     从原型抽取的完整设计系统（两段 style 合并）
│     ├─ components/        Sprite（原型图标）/ StatusPill / DagView
│     └─ pages/             Chat / Tasks / Run / Approvals / Models / Placeholder
└─ docker-compose.yml       Postgres 16 + pgvector / Redis 7
```

## 三、Phase 2 · DAG 编排

### 依赖声明

在 `Step.args` 里声明依赖（README §七 预留的 `depends_on` 字段）：

```json
{"node_id": "n2", "depends_on": ["n1"], "skill": "research.summary"}
```

- `node_id`：图内节点标识，缺省回落 `seq-{seq}`；
- `depends_on`：上游节点（`node_id` 或 seq 数字皆可）；
- **全图都没有依赖声明时自动按 `seq` 串成链** —— 与 Phase 1 串行行为完全等价。

### 调度语义（对齐 A1–A5 定版）

| 契约 | 实现 |
|---|---|
| A1① 挂审批时 run 保持 `running` | 断点由 step 粒度承载，兄弟节点继续调度 |
| A1② 失败默认快速失败 | 任一节点失败 → `run→failed` |
| A2 入口不变 | `execute_run(run_id, from_seq)` 签名与续跑语义保持 |
| A3 并发槽 | 每节点启动 `slots_used += 1`、结束 `-= 1`，超槽排队 |
| A4 工具风险 | `tools` 表字段冻结，新增工具只插数据 |
| A5 事件总线 | 落库后 `publish`，Redis 多 worker 零改动 |

### 技能系统 v1

技能 = **提示词模板 + 工具组合 + 参数预设**，存 `skills` 表，节点用 `args.skill` 引用：

```sql
SELECT name, label, tools FROM skills WHERE enabled;
```

执行前自动展开进 `step.args`（注入 `prompt`）。技能被禁用 → 相关节点明确报错。
技能市场（浏览/分享/安装）属 P2 迭代，`GET /api/skills` 已预留消费接口。

### 新增接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/skills` | 技能清单 |
| POST | `/api/skills/{name}/toggle` | 启停技能 |
| GET | `/api/runs/{id}` | 追加 `dag` 字段：节点/依赖边/拓扑序/最大并行宽度 |

## 四、本地跑起来

> 界面预览（实际运行截图）：`docs/screenshots/01-chat.png` … `05-models.png`

```bash
# 1) 后端（默认 SQLite，零依赖启动）
cd backend
python3 -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# 接口文档 http://localhost:8000/docs

# 2) 前端
cd frontend
pnpm install
pnpm dev            # http://localhost:5173 ，/api 已代理到 8000
```

接真实模型（可选）：

```bash
export LLM_API_KEY=sk-xxx
export LLM_BASE_URL=https://api.deepseek.com
export LLM_MODEL=deepseek-chat
```

不配 key 也能跑完整闭环——Model Gateway 自动降级为本地规则生成，只是文案非模型产出。

切生产依赖（PostgreSQL 16 + pgvector / Redis，**已实测验证**）：

```bash
docker compose up -d          # pgvector/pgvector:pg16 + redis:7，init.sql 自动执行
export DATABASE_URL="postgresql+psycopg2://ai_team:ai_team@localhost:5432/ai_team_os"
export REDIS_URL="redis://localhost:6379/0"   # 可选：启用 SSE 事件总线跨进程通道
uvicorn app.main:app --port 8000
```

- 两种数据库可无缝切换，同一套 ORM/建表脚本（`migrations/init.sql` 与 `models.py` 字段级对齐）；
- `REDIS_URL` 留空 = 单进程内存队列；设置后 publish 同步上 Redis 频道、每进程一个订阅线程扇回本地——多 worker 部署直接可用，业务代码零改动；
- Redis 故障不阻塞主流程（publish 失败静默降级为本地广播）。

## 四、接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/chat` | 发消息；工作型意图自动建任务并起 Run |
| GET | `/api/conversations` · `/api/conversations/{id}/messages` | 会话与消息 |
| GET | `/api/tasks?status=` | 任务列表（all / running / wait / done） |
| POST | `/api/tasks` | 直接建任务 |
| GET | `/api/runs/{id}` | Run + Steps + 事件流 + 交付物 + 待审审批 |
| POST | `/api/runs/{id}/pause` `/cancel` `/input` | 暂停 / 取消 / 补充输入后续跑 |
| GET | `/api/approvals?status=` | 审批列表 |
| POST | `/api/approvals/{id}/decision` | `approve` / `reject` / `revise`（幂等） |
| GET | `/api/policy` | 三级策略快照 |
| GET/POST | `/api/models` | 模型档案 |
| POST | `/api/models/{id}/test` `/default` | 连通性测试 / 设默认 |

**SSE 流式（已完成）**

| 路径 | 说明 |
|---|---|
| POST `/api/chat/stream` | 对话流式：`meta`（会话/任务信息）→ `delta×N`（逐段文本）→ `done`；真实模型走 OpenAI 流式协议，无 key 时切块模拟 |
| GET `/api/events` | 全局事件流：`task.created` / `approval.requested` / `approval.approved` / `run.completed`…，审批中心、任务页、导航徽章由它驱动实时刷新 |
| GET `/api/runs/{id}/stream` | 单运行事件流：`run.started` / `step.started` / `step.completed`…，运行详情页被动刷新 |

事件由执行器在**每次落库后**经内存总线广播（`app/events.py`，线程安全队列）；前端 EventSource 收到事件后按需重拉数据——SSE 只做信号，不承载数据，避免双写。断线由浏览器自动重连，15 秒无事件发心跳注释帧。Phase 2 多 worker 部署时把总线换 Redis pub/sub，接口不变。

## 五、验收清单（对应 Phase 1 P0）

- [x] 对话能建任务，工作型与闲聊分流
- [x] Task → Run → Step 三级结构落库，状态机 10 态服务端校验
- [x] 高风险动作（外发消息）必挂审批，断点不执行
- [x] 审批通过后从断点续跑，已完成步骤不重算
- [x] 驳回终止运行、请求修改转 `awaiting_input`
- [x] 交付物落盘 + sha256 证据链
- [x] audit 事件流（run.created / step.started / approval.requested / …）
- [x] Model Gateway：OpenAI 兼容、多供应商、无 key 降级
- [x] 五个 P0 页面（对话 / 任务 / 运行 / 审批 / 模型）对接真实接口
- [x] 流式输出：对话逐段渲染（打字光标）+ 运行/审批/任务/徽章全部改为 SSE 事件驱动，无轮询
- [x] 生产依赖切换：PostgreSQL 16 + pgvector（闭环 E2E 实测通过）；Redis pub/sub 事件总线通道已启用（REDIS_URL 可选）
- [ ] 多角色组队（Phase 2）

## 六、测试

```bash
cd backend && python3 -m pytest tests/ -q
```

- `tests/test_flow.py`（5 条，Phase 1 闭环回归）：对话建任务、闲聊不建任务、审批断点与续跑、幂等决策、驳回终止、非法状态迁移；
- `tests/test_dag.py`（11 条，Phase 2 DAG 场景）：拓扑排序、环检测、线性回退串行、并行分支与汇聚、并行耗时验证、快速失败、未注册工具挂审批、审批挂起时兄弟节点继续、审批幂等与断点续跑不重算、并发槽排队、技能展开与禁用报错。

## 七、与后续阶段的接口约定

- `execute_run(run_id, from_seq)` 是唯一执行入口，DAG 调度器替换其内部实现，API 不变
- `slots_used / slots_total` 由调度器消费（当前 1/16）
- `Step.args` 里的 `depends_on` 承载 DAG 依赖；`Step.args` 里的 `skill` 引用技能
- `GET /api/skills` 为技能市场（P2 迭代）预留消费接口
- 知识库/记忆页已留路由占位，P2 直接填实现
