"""Model Gateway：OpenAI 兼容协议适配层。

设计约束（与原型文案一致）：新增供应商只需填 base_url / model / key 引用，不改执行引擎。
未配置 key 时自动降级为本地规则生成，保证离线可演示完整闭环。
"""
import json
import os
from typing import Any

import httpx

from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_TIMEOUT


class ModelGateway:
    def __init__(self, provider: dict[str, Any] | None = None):
        p = provider or {}
        self.base_url = (p.get("base_url") or LLM_BASE_URL).rstrip("/")
        self.api_key = p.get("api_key") or LLM_API_KEY
        self.model = p.get("model") or LLM_MODEL
        self.provider = p.get("provider") or "openai-compatible"
        self.last_error: str | None = None

    @property
    def live(self) -> bool:
        return bool(self.api_key)

    # ---------- 基础调用 ----------
    def chat(self, messages: list[dict], temperature: float = 0.4, max_tokens: int = 1200) -> str:
        if not self.live:
            return self._offline_reply(messages)
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            with httpx.Client(timeout=LLM_TIMEOUT) as client:
                r = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                r.raise_for_status()
                data = r.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:  # 网络/鉴权/配额失败都降级，不让主流程挂掉
            self.last_error = str(exc)
            return self._offline_reply(messages, note=f"（模型网关降级：{type(exc).__name__}）")

    # ---------- 流式调用（SSE） ----------
    def chat_stream(self, messages: list[dict], temperature: float = 0.6, max_tokens: int = 800):
        """生成器：逐段产出文本增量。真实模型走 OpenAI 流式协议；离线把完整回复切块模拟。"""
        if not self.live:
            for piece in _chunk(self._offline_reply(messages)):
                yield piece
            return
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }
            with httpx.Client(timeout=LLM_TIMEOUT) as client:
                with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                ) as r:
                    r.raise_for_status()
                    for line in r.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            return
                        try:
                            obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = obj.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        text = delta.get("content")
                        if text:
                            yield text
        except Exception as exc:  # 流式中断也降级，不让对话挂掉
            self.last_error = str(exc)
            for piece in _chunk(self._offline_reply(messages, note=f"（模型网关降级：{type(exc).__name__}）")):
                yield piece

    # ---------- 任务规划 ----------
    def plan(self, goal: str) -> list[dict]:
        """产出 Step 列表：agent / title / tool / args。"""
        if self.live:
            prompt = (
                "你是企业内网 AI 团队的协调器。请把下面的目标拆成 4-6 个可执行步骤，"
                "严格输出 JSON 数组，每项形如 "
                '{"agent":"报告撰写","title":"撰写初稿","tool":"llm.generate","args":{}}。'
                "可用工具：llm.generate、web.search、web.fetch、fs.read、fs.hash、"
                "fs.write_project、feishu.message。"
                "最后一步必须是 feishu.message（外发/通知），用于人工审批断点。"
                f"\n目标：{goal}"
            )
            raw = self.chat([{"role": "user", "content": prompt}], temperature=0.2, max_tokens=800)
            steps = self._parse_json(raw)
            if steps:
                return steps[:8]
        return self._offline_plan(goal)

    @staticmethod
    def _parse_json(raw: str) -> list[dict] | None:
        try:
            start, end = raw.find("["), raw.rfind("]")
            if start < 0 or end < 0:
                return None
            data = json.loads(raw[start : end + 1])
            out = []
            for item in data:
                if not isinstance(item, dict) or not item.get("title"):
                    continue
                out.append(
                    {
                        "agent": item.get("agent") or "需求分析师",
                        "title": item["title"],
                        "tool": item.get("tool") or "llm.generate",
                        "args": item.get("args") or {},
                    }
                )
            return out or None
        except Exception:
            return None

    # ---------- 离线降级 ----------
    @staticmethod
    def _offline_plan(goal: str) -> list[dict]:
        short = goal.strip().replace("\n", " ")[:40]
        return [
            {"agent": "需求分析师", "title": f"拆解目标：{short}", "tool": "llm.generate", "args": {}},
            {"agent": "研究助理", "title": "检索相关资料并去重", "tool": "web.search", "args": {"q": short}},
            {"agent": "数据分析师", "title": "核对数据口径与来源", "tool": "fs.read", "args": {"path": "deliverables/context.md"}},
            {"agent": "报告撰写", "title": "撰写交付物初稿", "tool": "fs.write_project", "args": {"path": f"deliverables/{short}.md"}},
            {"agent": "合规审核", "title": "证据链校验（sha256）", "tool": "fs.hash", "args": {}},
            {"agent": "报告撰写", "title": "外发评审并通知相关人", "tool": "feishu.message", "args": {"to": "product@team、research@team、quality@team"}},
        ]

    @staticmethod
    def _offline_reply(messages: list[dict], note: str = "") -> str:
        user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        if "拆解" in user or "JSON" in user:
            return "[]"
        return (
            f"收到。这条我先按「{user[:36]}」理解：会先确认口径与来源，再产出可核验的交付物；"
            "涉及外发或写入外部系统的动作会在审批中心挂起，等你确认后从断点继续。" + note
        )


def provider_from_env() -> dict:
    return {
        "provider": "deepseek" if "deepseek" in LLM_BASE_URL else "openai-compatible",
        "model": LLM_MODEL,
        "base_url": LLM_BASE_URL,
        "api_key": LLM_API_KEY,
        "name": LLM_MODEL,
    }


def _chunk(text: str, size: int = 14) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]
