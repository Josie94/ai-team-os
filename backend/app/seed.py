"""初始化数据：工具注册表、模型档案、示例会话与一条跑到审批断点的任务。"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import runner
from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from .models import Conversation, Message, ModelProvider, Tool
from .policy import DEFAULT_TOOLS


def seed_tools(db: Session):
    if db.scalar(select(func.count(Tool.name))):
        return
    for t in DEFAULT_TOOLS:
        db.add(Tool(**t))
    db.commit()


def seed_providers(db: Session):
    if db.scalar(select(func.count(ModelProvider.id))):
        return
    db.add_all(
        [
            ModelProvider(
                id="mp_1",
                name="DeepSeek V3",
                provider="deepseek",
                model=LLM_MODEL,
                base_url=LLM_BASE_URL,
                api_key=LLM_API_KEY,
                is_default=True,
            ),
            ModelProvider(
                id="mp_2",
                name="内网兼容模型",
                provider="openai-compatible",
                model="intra-chat",
                base_url="https://llm.intra/v1",
                api_key="",
            ),
            ModelProvider(
                id="mp_3",
                name="本地 Ollama",
                provider="ollama",
                model="qwen2.5:14b",
                base_url="http://127.0.0.1:11434/v1",
                api_key="",
            ),
        ]
    )
    db.commit()


CONVOS = [
    (
        "白皮书 2.0",
        "白皮书 2.0 · 初稿",
        "自动组队 1 位 · 单智能体执行",
        [
            ("assistant", "报告撰写 · 研究组", "白皮书初稿已生成，12 个步骤完成 5 个。第 5 步需要把初稿外发评审，我在审批中心挂起了，等你确认后继续。", {"filename": "白皮书_初稿_v1.md", "size": "48 KB", "note": "sha256 3f9a1c88…e2b7 · 来源 18 条"}),
            ("user", "我", "外发先别发，把「团队协作」那一章的 DAG 图补进去，再一起评审。", None),
            ("assistant", "产品经理 · 产品组", "DAG 图我按运行详情里的依赖关系重画，顺手加了一次失败注入示例，这样「可恢复」就不是口号了。", {"filename": "DAG_示意图_v2.svg", "size": "运行 run_8f3a · 12 节点 / 4 层", "note": "由 run 依赖关系生成"}),
        ],
    ),
    (
        "行业情报",
        "竞品动态扫描 · 第 42 周",
        "自动组队 1 位 · 单智能体执行",
        [
            ("assistant", "数据分析师 · 数据组", "第 42 周情报已去重为 12 条，字段映射校验通过，等写入审批。需要我把 3 条「需跟进」的单独列出来吗？", None),
            ("user", "我", "列出来，标注来源链接。", None),
        ],
    ),
    (
        "客户洞察",
        "客户访谈纪要结构化",
        "自动组队 1 位 · 单智能体执行",
        [("assistant", "内容运营", "访谈录音已转写并清洗，结论我提到了最前面，你看下这个结构行不行？", None)],
    ),
]


def seed_conversations(db: Session):
    if db.scalar(select(func.count(Conversation.id))):
        return
    for ws, title, sub, msgs in CONVOS:
        c = Conversation(id=runner._sid("c_", 6), workspace=ws, title=title, subtitle=sub)
        db.add(c)
        db.flush()
        for role, agent, content, att in msgs:
            db.add(
                Message(
                    conversation_id=c.id,
                    role=role,
                    agent=agent if role == "assistant" else "",
                    content=content,
                    attachment=att,
                )
            )
    db.commit()


def seed_demo_run(db: Session):
    """跑一条会停在审批断点的任务，让演示一进来就有内容。"""
    from .models import Task

    if db.scalar(select(func.count(Task.id))):
        return
    runner.create_task(db, "整理 10 月行业动态周报，按组别汇总进展并外发评审", workspace="行业情报")


def run_seed(db: Session):
    seed_tools(db)
    seed_providers(db)
    seed_conversations(db)
    seed_demo_run(db)
