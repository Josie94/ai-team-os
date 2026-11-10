# AI Team OS 前端原型分析 · Phase 1 开工拆解

> 依据：项目网盘《前端页面设计.html》（288KB，4329 行，单文件高保真原型，纯静态 + 原生 JS 模拟交互）
> Phase 1 范围（P0）：对话 → 单智能体执行 → 审批断点闭环 + Model Gateway，11/06–11/13

## 一、原型整体结构

- **技术形态**：单个 HTML 文件，内联 `<style>`（CSS variables 主题）+ 一段原生 JS（约 1500 行），无任何框架/依赖
- **交互模拟**：`go(page)` 页面切换、tab 容器、开关、toast、聊天 appendMessage（含 `WORK_RE` 正则判断"工作型对话"）、审批决策 mock
- **设计语言**：纸质米色系主题（`--paper` 等 CSS 变量）、Instrument Serif + Be Vietnam Pro 字体、中文界面
- **共 11 个页面**（`<section class="page">`），左侧 7 项主导航 + 隐藏页

## 二、页面清单与 Phase 1 范围映射

| # | 页面 | id | 内容 | Phase 1 优先级 |
|---|------|-----|------|------|
| 1 | 对话 | pageChat | 会话列表（按工作区分组）+ 消息流 + 交付物分享卡 + composer + **转为任务** | **P0 核心** |
| 2 | 任务 | pageTasks | Task 列表/看板双视图，状态筛选、时间范围（近2/7/30天）、定时任务按钮 | **P0** |
| 3 | 运行详情 | pageRun | Run 概要统计、12 步骤表、事件流、断点提示条、暂停/取消 | **P0** |
| 4 | 审批中心 | pageApprovals | 待审/已处理双 tab，风险分级卡片、审批策略面板、统计 | **P0** |
| 5 | 模型 | pageModels | 模型档案（DeepSeek V3 / 内网 / Ollama）、默认模型、生成参数、内置工具、MCP | **P0（Model Gateway）** |
| 6 | 工作台 | pageHome | 项目/组别/待办汇总 | P1，可先静态 |
| 7 | 员工 | pageEmployees | 13 位智能体卡片、组别筛选 | Phase 1 仅需 1 个默认 agent，可简化 |
| 8 | 项目 | pageProjects | 项目与交付物归档 | P2 占位 |
| 9 | 技能 | pageSkills | 提示词模板+工具编排 | P2 占位（Phase 2） |
| 10 | 知识库 | pageKb | 文档/规则入库 | P2 占位（Phase 3） |
| 11 | 记忆 | pageMemory | 记忆候选→确认→召回 | P2 占位（Phase 3） |

**结论：Phase 1 落地 5 个路由（chat / tasks / run / approvals / models），其余 6 个做占位页。**

## 三、原型内嵌的领域语义（可直接进建表/API 设计）

### 1. Task → Run → Step 三级结构
- 页面头标注 **"Tasks · 10 states"**，状态**只由后端状态机改变**（原型明确写了这条约束）
- 已展示的状态：`排队 / 执行中 / 等待审批 / 等待输入 / 已完成 / 已通过验收`（10 态完整定义在 mmmm 的规划文档里，**需要拿到**）
- Task 卡片字段：id（T-131）、项目 tag、标题、进度条、参与员工头像栈、步骤数、更新时间
- Run 概要字段：运行状态（如 `awaiting_approval`）、工具调用次数、步骤进度（5/12）、耗时、**并发占用（3/16 槽）**
- Step 表字段：`id(s1) / 执行员工 / 描述 / 工具调用(web.search ×3) / 产出(对比表 1 份) / 状态 / 耗时`
- 事件流：`step.started`、`step.completed` + 序号（#41）→ 即 audit/observability 事件表

### 2. 审批断点机制
- 审批对象字段：`approval_02c1` id、风险等级、动作类型 tag、关联 run + step、负责人、等待时长、影响说明
- 决策动作：**通过并继续 / 拒绝 / 请求修改**，原型注明"同一 action 仅挂起一次，重复请求幂等"
- 策略三级（右侧面板原文）：
  - **高风险：必须人工**——外发消息、删除文件、写外部系统，一律挂起
  - **中风险：白名单内免审**——项目交付物目录内写入、指定 Base 表写入
  - **低风险：直接执行**——搜索、抓取、读取项目内文件
- 关键约束：**"权限校验在服务端完成，提示词不是安全边界；所有决定写入 audit"**
- 决定后从落库的 Run/Step **断点继续**（不重算已完成步骤）

### 3. Model Gateway
- 模型档案三例：DeepSeek V3（默认，`https://api.deepseek.com`，key 加密引用）、内网 OpenAI 兼容（`https://llm.intra/v1`）、本地 Ollama（`127.0.0.1:11434/v1` 无 key）
- 配置字段：`provider / model / base_url / key 引用（服务端加密存储）` + 生成参数（按任务覆盖生效）
- 原型约束：**"适配层按 OpenAI 兼容协议实现，新增供应商只需填 base_url / model / key 引用，不改执行引擎"**
- 内置工具 4 个 + MCP 服务器 3 个（客户端形态）——MCP 是 Phase 3，Phase 1 只做内置工具风险注册表

### 4. 对话语义
- 会话按**工作区**分组（白皮书 2.0 / 行业情报 / 客户洞察 / 内部运营）
- 原型用 `WORK_RE` 正则区分"简单问题直接回答 / 工作型自动组队"——Phase 1 简化为：简单问题直接回答，工作型转单智能体执行
- 消息结构：员工头像+组别、bubble 正文、交付物分享卡（文件名 / 大小 / sha256 / 来源条数）
- **`chatToTask`（转为任务按钮）是对话→任务闭环的关键链路**，必须实现

## 四、React 18 + TS + Vite 拆分建议

### 路由与模块
```
src/
├─ routes/        Chat / Tasks / Run / Approvals / Models / Placeholder(其余6页)
├─ components/    通用：Avatar(av/tone-*)、StatusPill、Tag、Modal、Toast、Tabs、Switch
├─ modules/chat/  ConvoList、ChatHead、MessageList、MessageBubble、ShareCard、Composer
├─ modules/tasks/ TaskList、TaskBoard、TaskCard、TaskRow
├─ modules/run/   RunHeader、RunStats、StepTable、EventStream、BreakpointBar
├─ modules/approvals/ ApprovalCard、PolicyPanel、ApprovalTabs
├─ modules/models/ ModelProfile、ModelForm、ToolRegistry
└─ api/           REST + SSE/WebSocket（对话流式、审批挂起推送）
```

### 样式迁移
- 原型单文件 `<style>` 可整体迁为 `global.css`，CSS variables 主题原样保留；无 Tailwind 等依赖，迁移成本低
- 字体走 Google Fonts，内网部署需本地托管字体文件

### 交互升级点（原型是 mock，真实实现需要）
1. **对话流式输出**（SSE 或 WebSocket），原型是 setTimeout 假回复
2. **审批挂起实时通知**：Run 执行到断点 → 审批中心 + 导航徽标（navApBadge）实时更新
3. **状态轮询/订阅**：原型明确"状态只由后端状态机改变"，前端不本地推导状态

## 五、Phase 1 建表草案（对应原型字段）

| 表 | 关键字段（源自原型展示） |
|----|----|
| conversations | 工作区 workspace、名称、摘要、未读数 |
| messages | 会话 id、角色/员工、正文、附件（文件名/大小/sha256/来源数） |
| tasks | 编号、标题、项目 tag、状态、进度、参与员工、时间 |
| runs | run_id、task_id、状态（10 态）、工具调用数、耗时、并发槽 |
| steps | 序号、run_id、执行 agent、描述、工具调用、产出、状态、耗时 |
| approvals | approval_id、run_id、step_id、风险等级、动作、参数、决策、幂等键 |
| tools | 工具名、风险等级（注册表）、白名单范围 |
| model_providers | provider、model、base_url、key 引用（加密）、是否默认 |
| audit_events | 事件类型（step.started/completed…）、序号、时间、上下文 |

## 六、开工前仍缺的材料与风险

1. **mmmm 的完整规划文档**（建表 SQL、10 态状态机定义、状态机图）——页面只展示了部分状态，建表前必须拿到
2. 并发槽（3/16）语义：16 槽的定义与调度策略需要确认（Phase 2 DAG 的伏笔，Phase 1 单 agent 可先固定 1 槽）
3. 原型聊天里的"自动组队"是 Phase 2 能力，Phase 1 用**固定单 agent**跑通闭环即可，避免超期
4. DeepSeek API Key / 内网模型地址需要今天配好，Model Gateway 联调不能等
