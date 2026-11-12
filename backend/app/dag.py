"""DAG 图模型：依赖解析、拓扑排序、环检测。

Phase 2 在 Phase 1 的线性 Step 序列上叠加依赖关系：
- 依赖声明在 `Step.args["depends_on"]`（沿用 README §七 预留字段），值为上游节点标识；
- 节点标识优先用 `Step.args["node_id"]`，缺省回落到 `Step.seq`（保持 Phase 1 兼容）；
- 无依赖声明的节点按 `seq` 串成链，等价 Phase 1 行为。

纯内存结构，不依赖数据库，方便单测。
"""
from dataclasses import dataclass, field


class CyclicGraph(Exception):
    """依赖成环。"""


@dataclass
class Node:
    """一个可调度节点（对应一条 Step）。"""

    key: str                     # 图内唯一标识
    seq: int                     # 数据库里的 step.seq
    title: str = ""
    agent: str = ""
    tool: str = "llm.generate"
    args: dict = field(default_factory=dict)
    skill: str | None = None
    depends_on: list[str] = field(default_factory=list)

    @property
    def is_dag(self) -> bool:
        """是否带显式依赖（纯串行节点为 False）。"""
        return bool(self.depends_on)


def _as_key(value) -> str:
    return str(value)


def build_graph(steps) -> tuple[dict[str, Node], dict[str, list[str]]]:
    """从 Step 列表构建节点表与依赖表。

    - 节点 key：args["node_id"] 优先，否则 "seq-{seq}"；
    - 依赖：args["depends_on"] 里的每一项按"先 node_id 后 seq-{n}"顺序解析；
    - 依赖了不存在的节点 → 视为指向该 seq（若也不存在则忽略并保持图可调度）。
    """
    nodes: dict[str, Node] = {}
    by_seq: dict[int, str] = {}

    for step in steps:
        args = step.args or {}
        key = _as_key(args.get("node_id") or f"seq-{step.seq}")
        nodes[key] = Node(
            key=key,
            seq=step.seq,
            title=getattr(step, "title", "") or "",
            agent=getattr(step, "agent", "") or "",
            tool=getattr(step, "tool", "llm.generate") or "llm.generate",
            args=args,
            skill=args.get("skill"),
            depends_on=[],
        )
        by_seq[step.seq] = key

    for key, node in nodes.items():
        deps = node.args.get("depends_on") or []
        if isinstance(deps, (str, int)):
            deps = [deps]
        resolved: list[str] = []
        for dep in deps:
            dep_key = _as_key(dep)
            if dep_key in nodes:
                resolved.append(dep_key)
            elif dep_key.isdigit() and int(dep_key) in by_seq:
                resolved.append(by_seq[int(dep_key)])
            elif f"seq-{dep_key}" in nodes:
                resolved.append(f"seq-{dep_key}")
        node.depends_on = [d for d in resolved if d != key]

    # 全图都没有声明依赖 → 视为 Phase 1 的线性计划，按 seq 串成链（保持串行等价）
    if nodes and not any(n.depends_on for n in nodes.values()):
        ordered = sorted(nodes.values(), key=lambda n: n.seq)
        for prev, cur in zip(ordered, ordered[1:]):
            cur.depends_on = [prev.key]

    return nodes, {k: list(v.depends_on) for k, v in nodes.items()}


def validate_graph(deps: dict[str, list[str]]) -> None:
    """拓扑校验：存在环则抛 CyclicGraph，并给出环上节点。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {k: WHITE for k in deps}
    stack: list[str] = []

    def visit(node: str) -> None:
        color[node] = GRAY
        stack.append(node)
        for dep in deps.get(node, []):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                cycle = stack[stack.index(dep):] + [dep]
                raise CyclicGraph("依赖成环: " + " → ".join(cycle))
            if color[dep] == WHITE:
                visit(dep)
        stack.pop()
        color[node] = BLACK

    for node in deps:
        if color[node] == WHITE:
            visit(node)


def topo_order(deps: dict[str, list[str]]) -> list[str]:
    """拓扑排序（Kahn），返回依赖在前、依赖者在后的顺序。"""
    validate_graph(deps)
    indeg = {k: 0 for k in deps}
    children: dict[str, list[str]] = {k: [] for k in deps}
    for node, parents in deps.items():
        indeg[node] = len([p for p in parents if p in indeg])
        for p in parents:
            if p in children:
                children[p].append(node)

    ready = sorted([k for k, d in indeg.items() if d == 0])
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for child in children.get(node, []):
            indeg[child] -= 1
            if indeg[child] == 0:
                ready.append(child)
                ready.sort()
    return order


def ready_nodes(deps: dict[str, list[str]], done: set[str]) -> list[str]:
    """就绪集：所有上游都已完成的节点（入度按未完成上游计）。"""
    out = []
    for node, parents in deps.items():
        if node in done:
            continue
        if all(p in done for p in parents if p in deps):
            out.append(node)
    return out


def downstream(deps: dict[str, list[str]], node: str) -> set[str]:
    """某节点的全部下游（传递闭包）。"""
    children: dict[str, list[str]] = {k: [] for k in deps}
    for n, parents in deps.items():
        for p in parents:
            children.setdefault(p, []).append(n)
    seen: set[str] = set()
    stack = list(children.get(node, []))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(children.get(cur, []))
    return seen
