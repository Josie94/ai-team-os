"""10 态状态机：状态只能由后端迁移，前端不允许本地推导。

queued → running → awaiting_approval / awaiting_input / paused → … → completed
失败/取消/驳回/归档为终态（归档可回填）。
"""

STATES = [
    "queued",          # 排队
    "running",         # 执行中
    "awaiting_approval",  # 等待审批
    "awaiting_input",  # 等待输入
    "paused",          # 暂停
    "completed",       # 已完成
    "failed",          # 失败
    "cancelled",       # 已取消
    "rejected",        # 已驳回
    "archived",        # 已归档
]

LABELS = {
    "queued": "排队",
    "running": "执行中",
    "awaiting_approval": "等待审批",
    "awaiting_input": "等待输入",
    "paused": "已暂停",
    "completed": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
    "rejected": "已驳回",
    "archived": "已归档",
}

TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelled", "archived"},
    "running": {"awaiting_approval", "awaiting_input", "paused", "completed", "failed", "cancelled"},
    "awaiting_approval": {"running", "rejected", "cancelled", "failed"},
    "awaiting_input": {"running", "cancelled", "failed"},
    "paused": {"running", "cancelled", "archived"},
    "completed": {"archived"},
    "failed": {"archived", "queued"},
    "cancelled": {"archived"},
    "rejected": {"archived"},
    "archived": set(),
}

TERMINAL = {"completed", "cancelled", "rejected", "archived"}


class IllegalTransition(Exception):
    def __init__(self, cur: str, nxt: str):
        super().__init__(f"非法状态迁移: {cur} → {nxt}")
        self.cur, self.next = cur, nxt


def can(cur: str, nxt: str) -> bool:
    return nxt in TRANSITIONS.get(cur, set())


def transit(obj, nxt: str):
    """按状态机迁移，非法迁移直接抛错（服务端强约束）。"""
    if not can(obj.status, nxt):
        raise IllegalTransition(obj.status, nxt)
    obj.status = nxt
    return obj
