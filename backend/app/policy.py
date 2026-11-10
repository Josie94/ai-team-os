"""工具风险注册表 + 审批策略。

策略（与原型一致）：
- 高风险：外发消息、删除文件、写外部系统 → 必须人工
- 中风险：白名单内的写入 → 免审；白名单外 → 挂起
- 低风险：搜索、抓取、读取项目内文件 → 直接执行
"""
from .models import Tool

DEFAULT_TOOLS = [
    dict(name="llm.generate", label="模型生成", risk="low", whitelist=[], description="调用模型网关生成内容"),
    dict(name="web.search", label="联网检索", risk="low", whitelist=[], description="检索公开资料"),
    dict(name="web.fetch", label="网页抓取", risk="low", whitelist=[], description="抓取指定页面正文"),
    dict(name="fs.read", label="读取项目文件", risk="low", whitelist=[], description="只读项目内文件"),
    dict(name="fs.hash", label="证据链校验", risk="low", whitelist=[], description="计算 sha256 证据指纹"),
    dict(name="fs.write_project", label="写入项目目录", risk="mid",
         whitelist=["deliverables/"], description="写入项目交付物目录"),
    dict(name="feishu.base.batch_create", label="写外部多维表格", risk="mid",
         whitelist=[], description="批量写入飞书 Base"),
    dict(name="feishu.message", label="外发消息", risk="high", whitelist=[], description="对外发送消息，不可撤回"),
    dict(name="fs.delete", label="删除文件", risk="high", whitelist=[], description="删除文件，不可恢复"),
]


def requires_approval(tool: Tool | None, args: dict) -> tuple[bool, str]:
    """返回 (是否需要审批, 风险等级)。工具未注册一律按高风险处理（默认拒绝）。"""
    if tool is None or not tool.enabled:
        return True, "high"
    risk = tool.risk
    if risk == "high":
        return True, risk
    if risk == "mid":
        target = str(args.get("path") or args.get("target") or "")
        if any(target.startswith(p) for p in (tool.whitelist or [])):
            return False, risk
        return True, risk
    return False, risk


def policy_snapshot(tools: list[Tool]) -> dict:
    """给前端审批策略面板用的分级快照。"""
    out = {"high": [], "mid": [], "low": []}
    for t in tools:
        out.setdefault(t.risk, []).append(
            {"name": t.name, "label": t.label, "whitelist": t.whitelist or []}
        )
    return out
