"""Task → Run → Step 三级结构 + 审批 / 工具注册表 / 模型档案 / 审计事件。

字段命名与前端原型（前端页面设计.html）中的展示字段一一对应。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # T-131
    workspace: Mapped[str] = mapped_column(String(64), default="默认工作区")
    title: Mapped[str] = mapped_column(String(200))
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    priority: Mapped[str] = mapped_column(String(8), default="P0")
    owner: Mapped[str] = mapped_column(String(64), default="我")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    runs: Mapped[list["Run"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # run_8f3a
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    done_steps: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    slots_used: Mapped[int] = mapped_column(Integer, default=1)
    slots_total: Mapped[int] = mapped_column(Integer, default=16)
    pending_approval_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    task: Mapped[Task] = relationship(back_populates="runs")
    steps: Mapped[list["Step"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Step.seq"
    )


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    agent: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    tool: Mapped[str] = mapped_column(String(64), default="llm.generate")
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped[Run] = relationship(back_populates="steps")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # approval_02c1
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    step_id: Mapped[int] = mapped_column(Integer)
    step_seq: Mapped[int] = mapped_column(Integer)
    risk: Mapped[str] = mapped_column(String(16))  # high / mid / low
    action: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    idem_key: Mapped[str] = mapped_column(String(160), unique=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Tool(Base):
    __tablename__ = "tools"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(64))
    risk: Mapped[str] = mapped_column(String(16))  # low / mid / high
    whitelist: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(default=True)


class ModelProvider(Base):
    __tablename__ = "model_providers"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    base_url: Mapped[str] = mapped_column(String(200))
    api_key: Mapped[str] = mapped_column(Text, default="")  # 服务端存储，接口只返回是否已配置
    is_default: Mapped[bool] = mapped_column(default=False)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(24), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(48))  # run.started / step.completed / approval.requested
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Deliverable(Base):
    __tablename__ = "deliverables"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(24), index=True)
    task_id: Mapped[str] = mapped_column(String(24), index=True)
    filename: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(String(400))
    size: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    workspace: Mapped[str] = mapped_column(String(64), default="默认工作区")
    title: Mapped[str] = mapped_column(String(200))
    subtitle: Mapped[str] = mapped_column(String(200), default="")
    unread: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user / assistant / system
    agent: Mapped[str] = mapped_column(String(64), default="")
    content: Mapped[str] = mapped_column(Text)
    run_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    attachment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
