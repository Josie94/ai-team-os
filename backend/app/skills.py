"""技能系统 v1：技能 = 提示词模板 + 工具组合 + 参数预设。

Phase 2 只做"技能定义与被节点引用"；技能市场（浏览/分享/安装）属 FYR 的 P2 迭代，
这里预留查询接口与 schema 文档，消费侧按 skill 名引用即可。

设计原则沿用 Phase 1 的"插数据不改代码"：技能存表、启停用 enabled 字段，
执行器在节点执行前把技能展开进 step.args。
"""
from sqlalchemy import JSON, Boolean, DateTime, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import now


class Skill(Base):
    """技能定义表。"""

    __tablename__ = "skills"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    # 提示词模板：{goal} / {input} / {title} 占位
    prompt_template: Mapped[str] = mapped_column(Text, default="")
    # 允许调用的工具白名单（空 = 不限制）
    tools: Mapped[list] = mapped_column(JSON, default=list)
    # 参数预设：合并进 step.args
    args_preset: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=now)


DEFAULT_SKILLS = [
    {
        "name": "research.summary",
        "label": "调研摘要",
        "description": "检索资料并归并为要点列表",
        "prompt_template": "围绕「{goal}」检索并归并要点，输出可核验的摘要。",
        "tools": ["web.search", "web.fetch"],
        "args_preset": {},
    },
    {
        "name": "report.draft",
        "label": "报告撰写",
        "description": "撰写带结论/证据/风险/下一步的交付物初稿",
        "prompt_template": "为「{goal}」撰写交付物初稿：结论、证据、风险、下一步。",
        "tools": ["llm.generate", "fs.write_project"],
        "args_preset": {},
    },
    {
        "name": "evidence.hash",
        "label": "证据链校验",
        "description": "计算交付物 sha256 并回写",
        "prompt_template": "对已产出交付物做 sha256 证据链校验。",
        "tools": ["fs.hash"],
        "args_preset": {},
    },
    {
        "name": "notify.review",
        "label": "评审通知",
        "description": "外发评审通知（高风险，需审批）",
        "prompt_template": "将「{title}」送评审，列出结论与待确认项。",
        "tools": ["feishu.message"],
        "args_preset": {},
    },
]


def seed_skills(db) -> None:
    """首次启动写入默认技能（幂等）。"""
    from sqlalchemy import func

    if db.scalar(select(func.count(Skill.name))):
        return
    for s in DEFAULT_SKILLS:
        db.add(Skill(**s))
    db.commit()


def get_skill(db, name: str) -> Skill | None:
    if not name:
        return None
    return db.get(Skill, name)


def skill_catalog(db) -> list[dict]:
    """技能清单（给前端技能页 / FYR 的技能市场消费）。"""
    rows = db.scalars(select(Skill).order_by(Skill.name)).all()
    return [
        {
            "name": s.name,
            "label": s.label,
            "description": s.description,
            "tools": s.tools or [],
            "args_preset": s.args_preset or {},
            "enabled": s.enabled,
        }
        for s in rows
    ]


def expand_skill(skill: Skill | None, step_args: dict, goal: str, title: str) -> tuple[dict, str | None]:
    """把技能展开进节点参数。

    返回 (合并后的 args, 提示词模板)。技能不存在或已禁用 → 报错由调用方处理。
    """
    args = dict(step_args or {})
    if skill is None:
        return args, None
    preset = dict(skill.args_preset or {})
    for k, v in preset.items():
        args.setdefault(k, v)
    template = skill.prompt_template or ""
    if template:
        args.setdefault(
            "prompt",
            template.format(
                goal=goal or "",
                title=title or "",
                input=args.get("user_input", "") or args.get("input", "") or "",
            ),
        )
    return args, template
