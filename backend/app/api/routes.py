"""REST API：Phase 1 五条主链路（对话 / 任务 / 运行 / 审批 / 模型）。"""
import asyncio
import json
import queue
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import events, runner
from ..db import SessionLocal, get_db
from ..gateway import ModelGateway
from ..models import (
    Approval,
    AuditEvent,
    Conversation,
    Deliverable,
    Message,
    ModelProvider,
    Run,
    Step,
    Task,
    Tool,
)
from ..policy import policy_snapshot
from ..state_machine import LABELS, STATES, transit

router = APIRouter(prefix="/api")

STEP_LABELS = {
    "queued": "待执行",
    "running": "执行中",
    "awaiting_approval": "等待审批",
    "awaiting_input": "等待输入",
    "done": "完成",
    "failed": "失败",
    "skipped": "跳过",
}


# ---------------- 序列化 ----------------
def step_dict(s: Step) -> dict:
    return {
        "id": s.id,
        "seq": s.seq,
        "agent": s.agent,
        "title": s.title,
        "tool": s.tool,
        "args": s.args or {},
        "status": s.status,
        "status_label": STEP_LABELS.get(s.status, s.status),
        "output": s.output,
        "duration_ms": s.duration_ms,
        "started_at": s.started_at.isoformat() if s.started_at else None,
    }


def run_dict(r: Run, with_steps: bool = False) -> dict:
    d = {
        "id": r.id,
        "task_id": r.task_id,
        "status": r.status,
        "status_label": LABELS.get(r.status, r.status),
        "total_steps": r.total_steps,
        "done_steps": r.done_steps,
        "tool_calls": r.tool_calls,
        "slots_used": r.slots_used,
        "slots_total": r.slots_total,
        "pending_approval_id": r.pending_approval_id,
        "error": r.error,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
    }
    if with_steps:
        d["steps"] = [step_dict(s) for s in r.steps]
    return d


def task_dict(t: Task) -> dict:
    latest = t.runs[-1] if t.runs else None
    return {
        "id": t.id,
        "title": t.title,
        "goal": t.goal,
        "workspace": t.workspace,
        "status": t.status,
        "status_label": LABELS.get(t.status, t.status),
        "progress": t.progress,
        "priority": t.priority,
        "owner": t.owner,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
        "run_id": latest.id if latest else None,
        "steps": f"{latest.done_steps} / {latest.total_steps}" if latest else "0 / 0",
    }


def approval_dict(a: Approval, db: Session) -> dict:
    run = db.get(Run, a.run_id)
    task = db.get(Task, run.task_id) if run else None
    return {
        "id": a.id,
        "run_id": a.run_id,
        "task_id": run.task_id if run else None,
        "task_title": task.title if task else "",
        "step_seq": a.step_seq,
        "risk": a.risk,
        "action": a.action,
        "summary": a.summary,
        "detail": a.detail or {},
        "status": a.status,
        "note": a.note,
        "decided_by": a.decided_by,
        "created_at": a.created_at.isoformat(),
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
        "wait_seconds": _wait(a),
    }


def _wait(a: Approval) -> int:
    from datetime import datetime

    end = a.decided_at or datetime.now()
    return max(0, int((end - a.created_at).total_seconds()))


# ---------------- 元信息 ----------------
@router.get("/health")
def health():
    return {"ok": True, "phase": "Phase 1 MVP", "states": STATES}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    pending = db.scalar(select(func.count(Approval.id)).where(Approval.status == "pending")) or 0
    tasks = db.scalar(select(func.count(Task.id))) or 0
    running = db.scalar(select(func.count(Run.id)).where(Run.status == "running")) or 0
    done = db.scalar(select(func.count(Task.id)).where(Task.status == "completed")) or 0
    return {"pending_approvals": pending, "tasks": tasks, "running": running, "completed": done}


# ---------------- 对话 ----------------
class ChatIn(BaseModel):
    conversation_id: str | None = None
    text: str
    workspace: str = "默认工作区"


class ConvoIn(BaseModel):
    title: str
    workspace: str = "默认工作区"


@router.get("/conversations")
def list_conversations(db: Session = Depends(get_db)):
    rows = db.scalars(select(Conversation).order_by(Conversation.updated_at.desc())).all()
    out = []
    for c in rows:
        last = db.scalar(
            select(Message).where(Message.conversation_id == c.id).order_by(Message.id.desc())
        )
        out.append(
            {
                "id": c.id,
                "title": c.title,
                "workspace": c.workspace,
                "subtitle": c.subtitle,
                "unread": c.unread,
                "preview": (last.content[:60] if last else ""),
                "updated_at": c.updated_at.isoformat(),
            }
        )
    return out


@router.post("/conversations")
def create_conversation(payload: ConvoIn, db: Session = Depends(get_db)):
    c = Conversation(id=runner._sid("c_", 6), title=payload.title, workspace=payload.workspace)
    db.add(c)
    db.commit()
    return {"id": c.id, "title": c.title}


@router.get("/conversations/{cid}/messages")
def list_messages(cid: str, db: Session = Depends(get_db)):
    if not db.get(Conversation, cid):
        raise HTTPException(404, "会话不存在")
    rows = db.scalars(select(Message).where(Message.conversation_id == cid).order_by(Message.id)).all()
    return [
        {
            "id": m.id,
            "role": m.role,
            "agent": m.agent,
            "content": m.content,
            "run_id": m.run_id,
            "attachment": m.attachment,
            "created_at": m.created_at.isoformat(),
        }
        for m in rows
    ]


@router.post("/chat")
def chat(payload: ChatIn, db: Session = Depends(get_db)):
    text = payload.text.strip()
    if not text:
        raise HTTPException(400, "消息不能为空")

    convo = db.get(Conversation, payload.conversation_id) if payload.conversation_id else None
    if convo is None:
        convo = Conversation(
            id=runner._sid("c_", 6), title=text[:20], workspace=payload.workspace
        )
        db.add(convo)
        db.flush()

    db.add(Message(conversation_id=convo.id, role="user", content=text))
    db.flush()

    if runner.is_work_talk(text):
        task, run = runner.create_task(db, text, workspace=convo.workspace)
        reply = (
            f"已转为任务 {task.id}，我按 {run.total_steps} 步执行。"
            "涉及外发的步骤会挂起审批，其余先跑起来；完成后把交付物和 sha256 一起发你。"
        )
        assistant = Message(
            conversation_id=convo.id,
            role="assistant",
            agent="需求分析师 · 已组队",
            content=reply,
            run_id=run.id,
        )
        db.add(assistant)
        convo.subtitle = "自动组队 1 位 · 单智能体执行"
        db.commit()
        return {
            "conversation_id": convo.id,
            "reply": reply,
            "task_id": task.id,
            "run_id": run.id,
            "message_id": assistant.id,
        }

    gateway = runner.resolve_gateway(db)
    reply = gateway.chat([{"role": "user", "content": text}], temperature=0.6, max_tokens=600)
    assistant = Message(conversation_id=convo.id, role="assistant", agent="AI 助手", content=reply)
    db.add(assistant)
    db.commit()
    return {"conversation_id": convo.id, "reply": reply, "task_id": None, "run_id": None, "message_id": assistant.id}


# ---------------- SSE 事件流 ----------------
SSE_HEADERS = {"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"}


async def _stream_events(q: "queue.Queue", rid: str | None):
    """按订阅过滤推送：rid 为 None 推全部（全局流），否则只推该 run 的事件。"""
    try:
        while True:
            try:
                ev, msg = await asyncio.to_thread(q.get, True, 15)
            except queue.Empty:
                yield b": keepalive\n\n"  # 心跳，防止代理层断开空闲连接
                continue
            if rid is not None:
                try:
                    if json.loads(msg).get("run_id") != rid:
                        continue
                except json.JSONDecodeError:
                    continue
            yield events.sse_frame(ev, msg)
    finally:
        events.unsubscribe(q)


@router.get("/events")
async def sse_events(request: Request):
    """全局事件流：审批挂起、审批决策、任务创建等，驱动审批中心与导航徽章实时刷新。"""
    q = events.subscribe()
    return StreamingResponse(_stream_events(q, None), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/runs/{rid}/stream")
async def sse_run_stream(rid: str, request: Request):
    """单条运行的事件流：run/step 状态变化即推送，运行详情页由轮询改为被动刷新。"""
    q = events.subscribe()
    return StreamingResponse(_stream_events(q, rid), media_type="text/event-stream", headers=SSE_HEADERS)


def _sse(event: str, data: dict) -> bytes:
    return events.sse_frame(event, json.dumps(data, ensure_ascii=False))


@router.post("/chat/stream")
def chat_stream(payload: ChatIn):
    """对话流式接口：meta（会话/任务信息）→ delta×N（逐段文本）→ done。"""
    text = payload.text.strip()
    if not text:
        raise HTTPException(400, "消息不能为空")

    def gen():
        db = SessionLocal()
        try:
            convo = db.get(Conversation, payload.conversation_id) if payload.conversation_id else None
            if convo is None:
                convo = Conversation(id=runner._sid("c_", 6), title=text[:20], workspace=payload.workspace)
                db.add(convo)
                db.flush()
            db.add(Message(conversation_id=convo.id, role="user", content=text))
            db.commit()
            yield _sse("meta", {"conversation_id": convo.id, "task_id": None, "run_id": None})

            if runner.is_work_talk(text):
                task, run = runner.create_task(db, text, workspace=convo.workspace)
                task_id_out = task.id
                reply = (
                    f"已转为任务 {task.id}，我按 {run.total_steps} 步执行。"
                    "涉及外发的步骤会挂起审批，其余先跑起来；完成后把交付物和 sha256 一起发你。"
                )
                assistant = Message(
                    conversation_id=convo.id,
                    role="assistant",
                    agent="需求分析师 · 已组队",
                    content=reply,
                    run_id=run.id,
                )
                db.add(assistant)
                convo.subtitle = "自动组队 1 位 · 单智能体执行"
                db.commit()
                yield _sse("meta", {"conversation_id": convo.id, "task_id": task.id, "run_id": run.id})
                for i in range(0, len(reply), 10):
                    yield _sse("delta", {"text": reply[i : i + 10]})
                    time.sleep(0.05)
            else:
                gateway = runner.resolve_gateway(db)
                pieces: list[str] = []
                for piece in gateway.chat_stream(
                    [{"role": "user", "content": text}], temperature=0.6, max_tokens=600
                ):
                    pieces.append(piece)
                    yield _sse("delta", {"text": piece})
                    if not gateway.live:  # 离线切块的演示节奏；真实流式不再额外加延迟
                        time.sleep(0.03)
                task_id_out = None
                reply = "".join(pieces)
                assistant = Message(
                    conversation_id=convo.id, role="assistant", agent="AI 助手", content=reply
                )
                db.add(assistant)
                db.commit()
            yield _sse(
                "done",
                {
                    "conversation_id": convo.id,
                    "task_id": task_id_out,
                    "run_id": assistant.run_id,
                    "message_id": assistant.id,
                },
            )
        finally:
            db.close()

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


# ---------------- 任务 ----------------
@router.get("/tasks")
def list_tasks(status: str | None = None, db: Session = Depends(get_db)):
    q = select(Task).order_by(Task.updated_at.desc())
    if status and status != "all":
        if status == "wait":
            q = q.where(Task.status.in_(["awaiting_approval", "awaiting_input"]))
        elif status == "running":
            q = q.where(Task.status == "running")
        elif status == "done":
            q = q.where(Task.status == "completed")
        else:
            q = q.where(Task.status == status)
    return [task_dict(t) for t in db.scalars(q).all()]


@router.get("/tasks/{tid}")
def get_task(tid: str, db: Session = Depends(get_db)):
    t = db.get(Task, tid)
    if not t:
        raise HTTPException(404, "任务不存在")
    d = task_dict(t)
    d["runs"] = [run_dict(r) for r in t.runs]
    return d


class TaskIn(BaseModel):
    goal: str = Field(min_length=2)
    workspace: str = "默认工作区"
    title: str | None = None


@router.post("/tasks")
def create_task(payload: TaskIn, db: Session = Depends(get_db)):
    task, run = runner.create_task(db, payload.goal, payload.workspace, payload.title)
    return {"task": task_dict(task), "run": run_dict(run)}


# ---------------- 运行 ----------------
@router.get("/runs/{rid}")
def get_run(rid: str, db: Session = Depends(get_db)):
    r = db.get(Run, rid)
    if not r:
        raise HTTPException(404, "运行不存在")
    task = db.get(Task, r.task_id)
    events = db.scalars(
        select(AuditEvent).where(AuditEvent.run_id == rid).order_by(AuditEvent.seq)
    ).all()
    deliverables = db.scalars(select(Deliverable).where(Deliverable.run_id == rid)).all()
    d = run_dict(r, with_steps=True)
    d["task"] = task_dict(task) if task else None
    d["events"] = [
        {"seq": e.seq, "type": e.type, "payload": e.payload, "at": e.created_at.isoformat()}
        for e in events
    ]
    d["deliverables"] = [
        {"filename": x.filename, "size": x.size, "sha256": x.sha256, "path": x.path}
        for x in deliverables
    ]
    ap = db.get(Approval, r.pending_approval_id) if r.pending_approval_id else None
    d["pending_approval"] = approval_dict(ap, db) if ap else None
    return d


@router.post("/runs/{rid}/pause")
def pause_run(rid: str, db: Session = Depends(get_db)):
    r = db.get(Run, rid)
    if not r:
        raise HTTPException(404, "运行不存在")
    transit(r, "paused")
    db.commit()
    return run_dict(r)


@router.post("/runs/{rid}/cancel")
def cancel_run(rid: str, db: Session = Depends(get_db)):
    r = db.get(Run, rid)
    if not r:
        raise HTTPException(404, "运行不存在")
    task = db.get(Task, r.task_id)
    transit(r, "cancelled")
    transit(task, "cancelled")
    runner.audit(db, r.id, "run.cancelled", {})
    db.commit()
    return run_dict(r)


class InputIn(BaseModel):
    text: str


@router.post("/runs/{rid}/input")
def run_input(rid: str, payload: InputIn, db: Session = Depends(get_db)):
    r = db.get(Run, rid)
    if not r:
        raise HTTPException(404, "运行不存在")
    res = runner.provide_input(db, r, payload.text)
    if not res["ok"]:
        raise HTTPException(400, res["error"])
    return res


# ---------------- 审批 ----------------
@router.get("/approvals")
def list_approvals(status: str = "pending", db: Session = Depends(get_db)):
    q = select(Approval).order_by(Approval.created_at.desc())
    if status != "all":
        q = q.where(Approval.status == status)
    return [approval_dict(a, db) for a in db.scalars(q).all()]


class DecisionIn(BaseModel):
    decision: str  # approve / reject / revise
    note: str | None = None
    by: str = "我"


@router.post("/approvals/{aid}/decision")
def decide(aid: str, payload: DecisionIn, db: Session = Depends(get_db)):
    a = db.get(Approval, aid)
    if not a:
        raise HTTPException(404, "审批不存在")
    res = runner.decide(db, a, payload.decision, payload.note, payload.by)
    if not res.get("ok"):
        raise HTTPException(409, res.get("error", "决策失败"))
    return res


@router.get("/policy")
def get_policy(db: Session = Depends(get_db)):
    tools = db.scalars(select(Tool).order_by(Tool.risk)).all()
    return policy_snapshot(tools)


# ---------------- 模型 ----------------
def provider_dict(p: ModelProvider) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "provider": p.provider,
        "model": p.model,
        "base_url": p.base_url,
        "has_key": bool(p.api_key),
        "key_hint": f"key_{p.id[-2:]}" if p.api_key else "未配置",
        "is_default": p.is_default,
        "enabled": p.enabled,
    }


class ProviderIn(BaseModel):
    name: str
    provider: str = "openai-compatible"
    model: str
    base_url: str
    api_key: str = ""
    is_default: bool = False


@router.get("/models")
def list_models(db: Session = Depends(get_db)):
    rows = db.scalars(select(ModelProvider).order_by(ModelProvider.created_at)).all()
    tools = db.scalars(select(Tool)).all()
    return {
        "providers": [provider_dict(p) for p in rows],
        "tools": [
            {"name": t.name, "label": t.label, "risk": t.risk, "whitelist": t.whitelist}
            for t in tools
        ],
    }


@router.post("/models")
def create_model(payload: ProviderIn, db: Session = Depends(get_db)):
    n = (db.scalar(select(func.count(ModelProvider.id))) or 0) + 1
    if payload.is_default:
        for p in db.scalars(select(ModelProvider)):
            p.is_default = False
    p = ModelProvider(
        id=f"mp_{n}",
        name=payload.name,
        provider=payload.provider,
        model=payload.model,
        base_url=payload.base_url.rstrip("/"),
        api_key=payload.api_key,
        is_default=payload.is_default,
    )
    db.add(p)
    db.commit()
    return provider_dict(p)


@router.post("/models/{pid}/default")
def set_default(pid: str, db: Session = Depends(get_db)):
    p = db.get(ModelProvider, pid)
    if not p:
        raise HTTPException(404, "模型不存在")
    for x in db.scalars(select(ModelProvider)):
        x.is_default = x.id == pid
    db.commit()
    return provider_dict(p)


@router.post("/models/{pid}/test")
def test_model(pid: str, db: Session = Depends(get_db)):
    p = db.get(ModelProvider, pid)
    if not p:
        raise HTTPException(404, "模型不存在")
    gw = ModelGateway({"provider": p.provider, "model": p.model, "base_url": p.base_url, "api_key": p.api_key})
    reply = gw.chat([{"role": "user", "content": "回复两个字：可用"}], max_tokens=16)
    return {"ok": gw.last_error is None, "live": gw.live, "reply": reply[:80], "error": gw.last_error}
