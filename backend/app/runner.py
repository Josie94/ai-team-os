"""单智能体执行器 → Phase 2 DAG 调度器：对话 → 任务 → 运行 → 步骤 → 审批断点 → 断点恢复。

Phase 2 把内部串行循环替换为自研 asyncio DAG 调度器：
- 节点依赖声明在 `Step.args["depends_on"]`（见 README §七 预留字段）；
- `execute_run(run_id, from_seq)` 入口签名与断点续跑语义保持不变（A2 定版）；
- 节点状态映射到 10 态，run 级保持单一状态（A1 定版）；
- 失败默认快速失败：任一节点失败 → run→failed（A1② 定版）；
- 并发槽 `runs.slots_used / slots_total` 由调度器消费（A3 定版）。

执行器跑在独立线程里（threading.Thread），DAG 并行用线程池实现——
同进程内共享 SQLAlchemy SessionLocal 与事件总线，避免引入 asyncio/DB 跨栈复杂度。
"""
import hashlib
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import dag as daglib
from .config import DELIVERABLE_DIR, RUN_ASYNC, STEP_DELAY
from .db import SessionLocal
from .events import publish
from .gateway import ModelGateway
from .models import Approval, AuditEvent, Deliverable, ModelProvider, Run, Step, Task, Tool
from .policy import requires_approval
from .skills import expand_skill, get_skill
from .state_machine import IllegalTransition, can, transit


def emit(run_id: str | None, event: str, data: dict) -> None:
    """落库后广播 SSE 事件；前端收到信号后按需刷新，SSE 不承载数据本身。"""
    payload = dict(data)
    if run_id:
        payload.setdefault("run_id", run_id)
    publish(event, payload)

WORK_RE = re.compile(
    "整理|汇总|生成|撰写|报告|扫描|核对|对比|分析|拆解|入库|清洗|周报|月报|白皮书|方案|审批|导出|对账|调研|复盘|取数|排查|监控|建模|发布"
)


def is_work_talk(text: str) -> bool:
    return bool(WORK_RE.search(text))


def _sid(prefix: str, n: int = 4) -> str:
    return f"{prefix}{uuid.uuid4().hex[:n]}"


def audit(db: Session, run_id: str, type_: str, payload: dict | None = None) -> AuditEvent:
    seq = (db.scalar(select(func.max(AuditEvent.seq)).where(AuditEvent.run_id == run_id)) or 0) + 1
    ev = AuditEvent(run_id=run_id, seq=seq, type=type_, payload=payload or {})
    db.add(ev)
    db.flush()
    return ev


def resolve_gateway(db: Session) -> ModelGateway:
    """优先用模型档案里的默认供应商，其次环境变量。"""
    p = db.scalar(select(ModelProvider).where(ModelProvider.is_default.is_(True)))
    if p:
        return ModelGateway(
            {"provider": p.provider, "model": p.model, "base_url": p.base_url, "api_key": p.api_key}
        )
    return ModelGateway()


def create_task(db: Session, goal: str, workspace: str = "默认工作区", title: str | None = None) -> tuple[Task, Run]:
    n = (db.scalar(select(func.count(Task.id))) or 0) + 101
    task = Task(
        id=f"T-{n}",
        workspace=workspace,
        title=title or goal.strip().split("\n")[0][:60] or "未命名任务",
        goal=goal.strip(),
        status="queued",
    )
    db.add(task)
    db.flush()

    run = Run(id=_sid("run_"), task_id=task.id, status="queued")
    db.add(run)
    db.flush()

    plan = resolve_gateway(db).plan(goal)
    for i, item in enumerate(plan, start=1):
        db.add(
            Step(
                run_id=run.id,
                seq=i,
                agent=item.get("agent") or "需求分析师",
                title=item.get("title") or f"步骤 {i}",
                tool=item.get("tool") or "llm.generate",
                args=item.get("args") or {},
            )
        )
    run.total_steps = len(plan)
    task.progress = 0
    audit(db, run.id, "run.created", {"task_id": task.id, "steps": len(plan)})
    db.commit()
    emit(run.id, "task.created", {"task_id": task.id, "title": task.title, "steps": len(plan)})

    if RUN_ASYNC:
        threading.Thread(target=execute_run, args=(run.id,), daemon=True).start()
    return task, run


# ---------------- 执行 ----------------
def execute_run(run_id: str, from_seq: int = 1):
    """唯一执行入口（A2 定版）：DAG 调度器替换了 Phase 1 的串行循环。

    from_seq 语义保持：断点续跑时只从该 seq 起跑，`status == done` 的步骤跳过不重算。
    """
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        if not run:
            return
        task = db.get(Task, run.task_id)
        if run.status in ("queued",):
            transit(run, "running")
        elif run.status in ("awaiting_approval", "awaiting_input", "paused"):
            transit(run, "running")
        elif run.status != "running":
            # 已是 running（DAG 断点期续跑）→ 同态迁移不合法，跳过
            pass
        if task.status in ("queued", "awaiting_approval", "awaiting_input", "paused"):
            transit(task, "running")
        run.pending_approval_id = None
        audit(db, run.id, "run.started", {"from_seq": from_seq})
        db.commit()
        emit(run.id, "run.started", {"from_seq": from_seq})

        gateway = resolve_gateway(db)
        # 取全量步骤构建图：DAG 里 seq 顺序 ≠ 依赖顺序，
        # 若只取 seq >= from_seq，会漏掉"seq 更小但仍是断点下游"的待执行节点。
        all_steps = db.scalars(
            select(Step).where(Step.run_id == run_id).order_by(Step.seq)
        ).all()

        nodes, deps = daglib.build_graph(all_steps)
        daglib.validate_graph(deps)  # 成环 → 直接失败，不进调度

        # 断点续跑范围：seq >= from_seq 的节点 + 其全部下游（依赖链上的后续节点）
        resume_keys = {k for k, n in nodes.items() if n.seq >= from_seq}
        for k in list(resume_keys):
            resume_keys |= daglib.downstream(deps, k)

        _schedule_dag(db, run, task, nodes, deps, gateway, resume_keys)
    except Exception as exc:  # 失败也要落库，前端才能看到原因
        db.rollback()
        run = db.get(Run, run_id)
        if run:
            run.error = str(exc)
            run.status = "failed"
            task = db.get(Task, run.task_id)
            if task:
                task.status = "failed"
            audit(db, run.id, "run.failed", {"error": str(exc)})
            db.commit()
            emit(run.id, "run.failed", {"error": str(exc)})
    finally:
        db.close()


def _schedule_dag(
    db: Session,
    run: Run,
    task: Task,
    nodes: dict,
    deps: dict,
    gateway: ModelGateway,
    resume_keys: set[str] | None = None,
):
    """DAG 调度主循环：就绪集 → 并发执行（受并发槽约束）→ 重新计算就绪集。

    - 审批断点：节点命中策略 → step 置 awaiting_approval，run 保持 running（A1①），
      其他就绪节点继续调度；本轮调度在该节点处挂起但不终止整图。
    - 失败：任一节点失败 → 快速失败，run→failed（A1②）。
    - 槽位：每节点启动 slots_used += 1、结束 -= 1，超槽排队（A3）。
    - resume_keys：限定本轮可调度节点（断点续跑范围）；None = 全图。
    """
    done: set[str] = set()
    blocked: set[str] = set()          # 挂审批 / 失败的节点
    failed = False
    scope = set(nodes.keys()) if resume_keys is None else set(resume_keys)

    # 已完成的步骤（续跑时不重算）直接计入 done
    for key, node in nodes.items():
        st = db.scalar(select(Step.status).where(Step.run_id == run.id, Step.seq == node.seq))
        if st == "done":
            done.add(key)

    max_workers = max(1, int(run.slots_total or 1))
    pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dag")
    pending: dict = {}  # future -> key

    try:
        while True:
            # 1) 收集就绪节点（上游全完成且自身未 done/未阻塞，且在调度范围内）
            ready = [
                k for k in daglib.ready_nodes(deps, done)
                if k not in blocked and k not in pending and k in scope
            ]
            if not ready and not pending:
                break

            # 2) 填满并发槽
            while ready and len(pending) < max_workers:
                key = ready.pop(0)
                node = nodes[key]
                run.slots_used += 1
                db.commit()
                fut = pool.submit(_execute_node, run.id, node.seq, gateway)
                pending[fut] = key

            if not pending:
                break

            # 3) 等任一节点完成
            finished = _wait_any(pending)
            for fut in finished:
                key = pending.pop(fut)
                node = nodes[key]
                run.slots_used = max(0, run.slots_used - 1)
                outcome = fut.result()
                if outcome == "done":
                    done.add(key)
                elif outcome == "awaiting_approval":
                    blocked.add(key)
                elif outcome == "failed":
                    failed = True
                    blocked.add(key)
                db.commit()

            if failed:
                # 快速失败：整图终止（A1②）
                break

        # 4) 收口：全图完成 / 有节点挂审批
        if failed:
            return

        pending_approvals = db.scalars(
            select(Approval).where(Approval.run_id == run.id, Approval.status == "pending")
        ).all()

        if pending_approvals:
            # 有节点挂审批：run 保持 running（A1①），等审批后从断点续跑
            db.commit()
            return

        unfinished = [k for k in nodes if k not in done and k not in blocked and k in scope]
        if unfinished:
            # 剩余节点全部因上游阻塞而无法推进（理论上不该发生，留审计）
            audit(db, run.id, "run.stalled", {"nodes": unfinished})
            db.commit()
            return

        # 整图完成：所有 step 都必须是 done（范围外的节点此前已完成）
        all_done = all(
            db.scalar(select(Step.status).where(Step.run_id == run.id, Step.seq == n.seq)) == "done"
            for n in nodes.values()
        )
        if not all_done:
            audit(db, run.id, "run.stalled", {"reason": "仍有未完成步骤"})
            db.commit()
            return

        run.finished_at = datetime.now().replace(microsecond=0)
        run.pending_approval_id = None
        transit(run, "completed")
        transit(task, "completed")
        task.progress = 100
        audit(db, run.id, "run.completed", {"steps": run.total_steps})
        db.commit()
        emit(run.id, "run.completed", {"steps": run.total_steps, "task_id": task.id})
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _wait_any(pending: dict) -> list:
    """等待任一 future 完成，返回已完成列表。"""
    from concurrent.futures import FIRST_COMPLETED, wait

    done_futs, _ = wait(list(pending.keys()), return_when=FIRST_COMPLETED)
    return list(done_futs)


def _execute_node(run_id: str, seq: int, gateway: ModelGateway) -> str:
    """在独立线程里执行一个节点（独立 Session，避免跨线程共享 Session）。

    返回：done / awaiting_approval / failed
    """
    db = SessionLocal()
    try:
        run = db.get(Run, run_id)
        task = db.get(Task, run.task_id)
        step = db.scalar(select(Step).where(Step.run_id == run_id, Step.seq == seq))
        if not run or not step or step.status == "done":
            return "done"

        # 技能展开（Phase 2 技能系统 v1）
        skill_name = (step.args or {}).get("skill")
        if skill_name:
            skill = get_skill(db, skill_name)
            if skill is None or not skill.enabled:
                raise RuntimeError(f"技能不可用: {skill_name}")
            step.args, _ = expand_skill(skill, step.args, task.goal, step.title)
            db.commit()

        # 审批断点：先判策略，需要审批就挂起，不执行
        tool = db.get(Tool, step.tool)
        already_approved = db.scalar(
            select(Approval).where(
                Approval.run_id == run.id,
                Approval.step_id == step.id,
                Approval.status == "approved",
            )
        )
        need, risk = (False, "low") if already_approved else requires_approval(tool, step.args or {})
        if need:
            # 幂等：同一 (run_id, step_seq, tool) 只允许一条审批。
            # 并行场景下多节点可能同时命中审批，这里先查后建，避免 UNIQUE 冲突。
            existing = db.scalar(
                select(Approval).where(Approval.idem_key == f"{run.id}:{step.seq}:{step.tool}")
            )
            if existing is not None:
                step.status = "awaiting_approval"
                db.commit()
                emit(run.id, "approval.requested", {
                    "approval_id": existing.id, "risk": existing.risk,
                    "step": step.seq, "action": step.tool,
                })
                return "awaiting_approval"

            ap = Approval(
                id=_sid("approval_", 6),
                run_id=run.id,
                step_id=step.id,
                step_seq=step.seq,
                risk=risk,
                action=step.tool,
                summary=f"{step.title}（{step.agent}）",
                detail={
                    "动作": step.tool,
                    "参数": step.args or {},
                    "影响": "对外可见，不可撤回" if risk == "high" else "写入外部系统，可回滚",
                    "阶段": f"step {step.seq} / {run.total_steps}",
                },
                status="pending",
                idem_key=f"{run.id}:{step.seq}:{step.tool}",
            )
            db.add(ap)
            run.pending_approval_id = ap.id
            step.status = "awaiting_approval"
            # run 级保持 running（A1①）：不断言 run 状态，只承载 step 粒度断点
            audit(db, run.id, "approval.requested", {"approval_id": ap.id, "risk": risk, "step": step.seq})
            db.commit()
            emit(run.id, "approval.requested", {"approval_id": ap.id, "risk": risk, "step": step.seq, "action": step.tool})
            return "awaiting_approval"

        _run_step(db, run, task, step, gateway)
        db.commit()
        emit(run.id, "step.completed", {"step": step.seq, "title": step.title, "agent": step.agent})
        return "done"
    except Exception as exc:
        db.rollback()
        run = db.get(Run, run_id)
        if run:
            run.error = str(exc)
            run.status = "failed"
            task = db.get(Task, run.task_id)
            if task:
                task.status = "failed"
            audit(db, run.id, "run.failed", {"error": str(exc), "step": seq})
            db.commit()
            emit(run.id, "run.failed", {"error": str(exc), "step": seq})
        return "failed"
    finally:
        db.close()


def _run_step(db: Session, run: Run, task: Task, step: Step, gateway: ModelGateway):
    step.status = "running"
    step.started_at = datetime.now().replace(microsecond=0)
    audit(db, run.id, "step.started", {"step": step.seq, "agent": step.agent, "tool": step.tool})
    db.commit()
    emit(run.id, "step.started", {"step": step.seq, "agent": step.agent, "tool": step.tool})

    t0 = time.time()
    time.sleep(STEP_DELAY)  # 演示节奏；真实执行由工具耗时决定
    output, extra = _exec_tool(db, run, task, step, gateway)
    step.output = output
    step.duration_ms = int((time.time() - t0) * 1000)
    step.status = "done"
    step.finished_at = datetime.now().replace(microsecond=0)

    run.done_steps += 1
    run.tool_calls += 1
    if run.total_steps:
        task.progress = int(run.done_steps / run.total_steps * 100)
    audit(db, run.id, "step.completed", {"step": step.seq, "output": output, **extra})


def _exec_tool(db: Session, run: Run, task: Task, step: Step, gateway: ModelGateway) -> tuple[str, dict]:
    tool = step.tool
    args = step.args or {}

    if tool == "llm.generate":
        return f"已拆解为 {run.total_steps} 个步骤，依赖关系已登记", {"tokens": 812}

    if tool in ("web.search", "web.fetch"):
        q = args.get("q") or task.title
        return f"检索「{q}」命中 9 条，去重后 6 条，来源已登记", {"sources": 6}

    if tool == "fs.read":
        return "读取项目上下文 3 份，口径字段校验通过", {"files": 3}

    if tool == "fs.hash":
        d = db.scalar(
            select(Deliverable).where(Deliverable.run_id == run.id).order_by(Deliverable.id.desc())
        )
        h = (d.sha256 if d else hashlib.sha256(task.goal.encode()).hexdigest())
        return f"证据链校验通过 sha256 {h[:8]}…{h[-4:]}", {"sha256": h}

    if tool == "fs.write_project":
        return _write_deliverable(db, run, task, step, gateway)

    if tool == "feishu.message":
        to = args.get("to") or "3 位评审人"
        return f"已发送给 {to}（审批留痕 audit）", {"recipients": to}

    if tool == "feishu.base.batch_create":
        return "写入 12 条记录，冲突 0 条，批次 id 已保留", {"rows": 12}

    return "已执行", {}


def _write_deliverable(db: Session, run: Run, task: Task, step: Step, gateway: ModelGateway) -> tuple[str, dict]:
    if gateway.live:
        body = gateway.chat(
            [
                {"role": "system", "content": "你是企业内网 AI 团队的报告撰写，输出 Markdown 正文，结构清晰、不编造数据。"},
                {"role": "user", "content": f"任务目标：{task.goal}\n请输出一份可交付的初稿（含结论、证据、风险、下一步）。"},
            ],
            temperature=0.5,
            max_tokens=1600,
        )
    else:
        body = _offline_draft(task.goal)

    filename = f"{task.id}_{step.seq}_初稿.md"
    path = Path(DELIVERABLE_DIR) / filename
    content = f"# {task.title}\n\n> 任务 {task.id} · run {run.id} · step {step.seq}\n\n{body}\n"
    path.write_text(content, encoding="utf-8")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

    db.add(
        Deliverable(
            run_id=run.id,
            task_id=task.id,
            filename=filename,
            path=str(path),
            size=len(content.encode("utf-8")),
            sha256=digest,
        )
    )
    db.flush()
    step.args = {**(step.args or {}), "saved": str(path)}
    return f"初稿已生成 {filename}（{len(content.encode('utf-8')) // 1024 or 1} KB）", {"sha256": digest}


def _offline_draft(goal: str) -> str:
    return f"""## 一、结论

围绕「{goal}」，本轮已完成资料检索、口径核对与初稿撰写。核心判断：先收敛口径，再产出交付物；对外动作一律经审批后执行。

## 二、证据与来源

| 编号 | 来源类型 | 用途 | 状态 |
|---|---|---|---|
| E1 | 项目内文档 | 口径基线 | 已校验 |
| E2 | 公开资料 | 行业背景 | 已去重 |
| E3 | 历史任务 | 复用结论 | 已引用 |

## 三、关键风险

1. 数据口径不一致可能导致结论偏差，已在 step 3 完成校验。
2. 外发动作不可撤回，已挂起审批断点，等待人工确认。
3. 模型输出需人工复核，不作为唯一决策依据。

## 四、下一步

- 评审人确认后从断点继续，不重算已完成步骤；
- 修订版保留 sha256 证据链，可追溯；
- 归档至项目交付物目录，供后续任务召回。
"""


# ---------------- 审批决策 ----------------
def decide(db: Session, approval: Approval, decision: str, note: str | None, by: str = "我") -> dict:
    run = db.get(Run, approval.run_id)
    task = db.get(Task, run.task_id)
    step = db.get(Step, approval.step_id)

    if approval.status != "pending":
        return {"ok": False, "error": "该审批已处理（幂等：同一 action 仅挂起一次）"}

    approval.decided_at = datetime.now().replace(microsecond=0)
    approval.decided_by = by
    approval.note = note

    if decision == "approve":
        approval.status = "approved"
        step.status = "queued"
        # run 在 DAG 断点期已是 running（A1①），同态迁移不合法 → 仅在需要时迁移
        if run.status != "running":
            transit(run, "running")
        if task.status != "running":
            transit(task, "running")
        run.pending_approval_id = None
        audit(db, run.id, "approval.approved", {"approval_id": approval.id, "step": approval.step_seq})
        db.commit()
        emit(run.id, "approval.approved", {"approval_id": approval.id, "step": approval.step_seq})
        threading.Thread(target=execute_run, args=(run.id, approval.step_seq), daemon=True).start()
        return {"ok": True, "status": "approved", "run_id": run.id}

    if decision == "reject":
        approval.status = "rejected"
        step.status = "failed"
        step.output = f"审批驳回：{note or '未说明原因'}"
        _reject_run(run, task)
        run.finished_at = datetime.now().replace(microsecond=0)
        run.pending_approval_id = None
        audit(db, run.id, "approval.rejected", {"approval_id": approval.id, "note": note})
        db.commit()
        emit(run.id, "approval.rejected", {"approval_id": approval.id, "step": approval.step_seq})
        return {"ok": True, "status": "rejected", "run_id": run.id}

    if decision == "revise":
        approval.status = "revise"
        approval.decided_at = None
        _revise_run(run, task)
        step.status = "awaiting_input"
        audit(db, run.id, "approval.revise_requested", {"approval_id": approval.id, "note": note})
        db.commit()
        emit(run.id, "approval.revise_requested", {"approval_id": approval.id, "step": approval.step_seq})
        return {"ok": True, "status": "revise", "run_id": run.id}

    return {"ok": False, "error": f"未知决策: {decision}"}


def _reject_run(run: Run, task: Task) -> None:
    """驳回 → 运行终止。

    Baseline v1 的迁移矩阵里 `rejected` 只从 `awaiting_approval` 可达；
    而 Phase 2 的 DAG 语义下 run 在断点期保持 `running`（A1① 定版），
    `running` 没有直达 `rejected` 的合法边。

    解决方式（不改状态机矩阵，走合法两步迁移）：
        running → awaiting_approval → rejected
    中间态只是状态机要求的过桥，不代表断点期把 run 挂在 awaiting_approval
    （A1① 约束的是"节点挂审批期间 run 保持 running"，此刻审批已决策完毕）。
    """
    if can(run.status, "rejected"):
        transit(run, "rejected")
    else:
        # running → awaiting_approval → rejected
        if not can(run.status, "awaiting_approval"):
            raise IllegalTransition(run.status, "rejected")
        transit(run, "awaiting_approval")
        transit(run, "rejected")
    if can(task.status, "rejected"):
        transit(task, "rejected")


def _revise_run(run: Run, task: Task) -> None:
    """请求修改 → 等待人工补充输入。

    同理：`awaiting_input` 在 Baseline v1 里只从 `running` 可达，
    DAG 断点期 run 已是 running；若 run 停在 awaiting_approval 则直接迁移。
    """
    if can(run.status, "awaiting_input"):
        transit(run, "awaiting_input")
    elif run.status == "awaiting_approval":
        transit(run, "running")
        transit(run, "awaiting_input")
    if can(task.status, "awaiting_input"):
        transit(task, "awaiting_input")


def provide_input(db: Session, run: Run, text: str) -> dict:
    """等待输入 → 重新执行当前步骤。"""
    task = db.get(Task, run.task_id)
    step = db.scalar(
        select(Step).where(Step.run_id == run.id, Step.status == "awaiting_input").order_by(Step.seq)
    )
    if not step:
        return {"ok": False, "error": "该运行不在等待输入状态"}
    step.args = {**(step.args or {}), "user_input": text}
    step.status = "queued"
    for ap in db.scalars(select(Approval).where(Approval.run_id == run.id, Approval.status == "revise")):
        ap.status = "superseded"
    if run.status != "running":
        transit(run, "running")
    if task.status != "running":
        transit(task, "running")
    audit(db, run.id, "run.input_provided", {"step": step.seq, "text": text[:200]})
    db.commit()
    emit(run.id, "run.input_provided", {"step": step.seq})
    threading.Thread(target=execute_run, args=(run.id, step.seq), daemon=True).start()
    return {"ok": True, "run_id": run.id}
