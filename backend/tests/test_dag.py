"""Phase 2 DAG 场景测试：并行执行 / 汇聚 / 快速失败 / 审批挂起兄弟继续 /
断点续跑不重算 / 超槽排队 / 环检测 / 幂等审批。

沿用 Phase 1 的建库与 TestClient 方式，但用独立 DB，避免与 test_flow 相互干扰。
"""
import os
import tempfile
import time

DB = os.path.join(tempfile.mkdtemp(), "test_dag.db")
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["STEP_DELAY"] = "0"
os.environ["RUN_ASYNC"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import dag as daglib  # noqa: E402
from app.db import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Run, Step, Task  # noqa: E402
from app.seed import run_seed  # noqa: E402

init_db()
_db = SessionLocal()
run_seed(_db)
_db.close()

client = TestClient(app)


def wait(predicate, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        v = predicate()
        if v:
            return v
        time.sleep(0.1)
    raise AssertionError("超时未达到预期状态")


_seq_counter = {"n": 0}


def make_task(steps: list[dict], goal: str = "DAG 测试任务") -> str:
    """直接建一条带指定步骤的 run（绕过规划器，精确控制图结构）。"""
    db = SessionLocal()
    try:
        _seq_counter["n"] += 1
        n = _seq_counter["n"]
        task = Task(
            id=f"T-DAG-{n}",
            workspace="测试",
            title=goal,
            goal=goal,
            status="queued",
        )
        db.add(task)
        db.flush()
        run = Run(id=f"run_dag_{n}", task_id=task.id, status="queued")
        db.add(run)
        db.flush()
        for i, s in enumerate(steps, start=1):
            db.add(
                Step(
                    run_id=run.id,
                    seq=i,
                    agent=s.get("agent", "测试智能体"),
                    title=s.get("title", f"步骤 {i}"),
                    tool=s.get("tool", "llm.generate"),
                    args=s.get("args", {}),
                )
            )
        run.total_steps = len(steps)
        db.commit()
        rid = run.id
    finally:
        db.close()
    return rid


def run_state(rid: str) -> dict:
    return client.get(f"/api/runs/{rid}").json()


def start(rid: str) -> None:
    from app.runner import execute_run

    execute_run(rid)


# ---------------- 单元：图结构 ----------------
def test_graph_topology_and_cycle():
    class S:
        def __init__(self, seq, args):
            self.seq = seq
            self.args = args
            self.title = "t"
            self.agent = "a"
            self.tool = "llm.generate"

    steps = [
        S(1, {"node_id": "n1"}),
        S(2, {"node_id": "n2", "depends_on": ["n1"]}),
        S(3, {"node_id": "n3", "depends_on": ["n1"]}),
        S(4, {"node_id": "n4", "depends_on": ["n2", "n3"]}),
    ]
    nodes, deps = daglib.build_graph(steps)
    assert len(nodes) == 4
    assert daglib.topo_order(deps)[0] == "n1"
    assert daglib.topo_order(deps)[-1] == "n4"
    # n2/n3 互不依赖 → 都是 n1 的就绪下游
    assert daglib.ready_nodes(deps, {"n1"}) == ["n2", "n3"]
    assert daglib.ready_nodes(deps, {"n1", "n2"}) == ["n3"]
    assert daglib.downstream(deps, "n1") == {"n2", "n3", "n4"}


def test_graph_cycle_detected():
    class S:
        def __init__(self, seq, args):
            self.seq = seq
            self.args = args
            self.title = "t"
            self.agent = "a"
            self.tool = "llm.generate"

    steps = [
        S(1, {"node_id": "a", "depends_on": ["b"]}),
        S(2, {"node_id": "b", "depends_on": ["a"]}),
    ]
    _, deps = daglib.build_graph(steps)
    try:
        daglib.validate_graph(deps)
    except daglib.CyclicGraph:
        return
    raise AssertionError("成环必须被检出")


def test_linear_plan_has_no_dependency():
    """Phase 1 语义的线性步骤（无 depends_on）应回退为串行等价。"""
    class S:
        def __init__(self, seq, args):
            self.seq = seq
            self.args = args
            self.title = "t"
            self.agent = "a"
            self.tool = "llm.generate"

    steps = [S(i, {}) for i in (1, 2, 3)]
    _, deps = daglib.build_graph(steps)
    # 无依赖声明 → 按 seq 自动串成链，保持 Phase 1 串行等价
    assert deps["seq-1"] == []
    assert deps["seq-2"] == ["seq-1"]
    assert deps["seq-3"] == ["seq-2"]
    assert daglib.ready_nodes(deps, set()) == ["seq-1"]
    assert daglib.ready_nodes(deps, {"seq-1"}) == ["seq-2"]


# ---------------- 集成：并行与汇聚 ----------------
def test_parallel_branch_and_join():
    """n1 → (n2 ‖ n3) → n4：n2/n3 并行，n4 汇聚后完成。"""
    rid = make_task([
        {"title": "拆解", "args": {"node_id": "n1"}},
        {"title": "检索", "tool": "web.search", "args": {"node_id": "n2", "depends_on": ["n1"]}},
        {"title": "读文件", "tool": "fs.read", "args": {"node_id": "n3", "depends_on": ["n1"]}},
        {"title": "汇总", "args": {"node_id": "n4", "depends_on": ["n2", "n3"]}},
    ])
    start(rid)
    final = wait(lambda: (lambda r: r if r["status"] == "completed" else None)(run_state(rid)))
    assert final["done_steps"] == 4
    assert all(s["status"] == "done" for s in final["steps"])


def test_parallel_timing_is_concurrent():
    """n2/n3 无依赖 → 应并行（总耗时接近单个步骤，而非两倍）。"""
    os.environ["STEP_DELAY"] = "0.6"
    import importlib

    from app import config as cfg

    importlib.reload(cfg)
    rid = make_task([
        {"title": "拆解", "args": {"node_id": "n1"}},
        {"title": "A", "args": {"node_id": "n2", "depends_on": ["n1"]}},
        {"title": "B", "args": {"node_id": "n3", "depends_on": ["n1"]}},
    ])
    t0 = time.time()
    start(rid)
    elapsed = time.time() - t0
    os.environ["STEP_DELAY"] = "0"
    importlib.reload(cfg)
    # 串行需 ~1.8s（3×0.6），并行应明显更快
    assert elapsed < 1.6, f"并行未生效，耗时 {elapsed:.2f}s"


# ---------------- 集成：快速失败 ----------------
def test_fail_fast():
    """节点失败 → run→failed（快速失败，A1②）。

    构造失败方式：引用一个已禁用的高风险工具以外的路径——用不存在且未注册的
    工具会按"未注册即高风险"挂审批（Phase 1 策略），所以这里用 skills 参数
    触发"技能不可用"错误，走真实异常路径。
    """
    rid = make_task([
        {"title": "拆解", "args": {"node_id": "n1"}},
        {"title": "坏技能", "args": {"node_id": "n2", "depends_on": ["n1"], "skill": "不存在的技能"}},
        {"title": "后续", "args": {"node_id": "n3", "depends_on": ["n2"]}},
    ])
    start(rid)
    final = wait(lambda: (lambda r: r if r["status"] in ("failed", "completed") else None)(run_state(rid)))
    assert final["status"] == "failed", f"应快速失败，实际 {final['status']}"
    assert "技能不可用" in (final.get("error") or "")


def test_unregistered_tool_requires_approval():
    """未注册工具按高风险处理 → 挂审批而非直接失败（Phase 1 策略保持）。"""
    rid = make_task([
        {"title": "未知工具", "tool": "不存在的工具", "args": {"node_id": "n1"}},
    ])
    start(rid)
    r = wait(lambda: (lambda x: x if any(s["status"] == "awaiting_approval" for s in x["steps"]) else None)(run_state(rid)))
    assert r["status"] == "running"
    aps = client.get("/api/approvals?status=pending").json()
    assert any(a["run_id"] == rid and a["risk"] == "high" for a in aps)


# ---------------- 集成：审批挂起 + 兄弟节点继续 ----------------
def test_approval_breakpoint_siblings_continue():
    """n2 命中高风险挂审批；n3（与 n2 无依赖）应照常跑完；run 保持 running。"""
    rid = make_task([
        {"title": "拆解", "args": {"node_id": "n1"}},
        {"title": "外发", "tool": "feishu.message", "args": {"node_id": "n2", "depends_on": ["n1"]}},
        {"title": "旁支检索", "tool": "web.search", "args": {"node_id": "n3", "depends_on": ["n1"]}},
    ])
    start(rid)
    r = wait(lambda: (lambda x: x if any(s["status"] == "awaiting_approval" for s in x["steps"]) else None)(run_state(rid)))
    # run 级保持 running（A1①）
    assert r["status"] == "running"
    # 兄弟节点 n3 已完成（不因 n2 挂起而阻塞）
    states = {s["seq"]: s["status"] for s in r["steps"]}
    assert states[3] == "done", f"兄弟节点应继续执行，实际 {states}"


def test_approval_idempotent_and_resume():
    """批准后从断点续跑，已完成步骤不重算；重复决策返回 409。"""
    rid = make_task([
        {"title": "拆解", "args": {"node_id": "n1"}},
        {"title": "外发", "tool": "feishu.message", "args": {"node_id": "n2", "depends_on": ["n1"]}},
    ])
    start(rid)
    ap = wait(
        lambda: [
            a for a in client.get("/api/approvals?status=pending").json() if a["run_id"] == rid
        ]
    )[0]
    first_step_done = run_state(rid)["steps"][0]["duration_ms"]

    d = client.post(f"/api/approvals/{ap['id']}/decision", json={"decision": "approve"})
    assert d.status_code == 200, d.text

    final = wait(lambda: (lambda r: r if r["status"] == "completed" else None)(run_state(rid)))
    assert final["done_steps"] == 2
    # 已完成步骤未被重算（duration 不变）
    assert final["steps"][0]["duration_ms"] == first_step_done

    again = client.post(f"/api/approvals/{ap['id']}/decision", json={"decision": "approve"})
    assert again.status_code == 409


# ---------------- 集成：并发槽 ----------------
def test_slot_limit_queues_nodes():
    """slots_total=2 时，3 个就绪节点不应同时 running（超槽排队）。"""
    rid = make_task([
        {"title": "A", "args": {"node_id": "n1"}},
        {"title": "B", "args": {"node_id": "n2"}},
        {"title": "C", "args": {"node_id": "n3"}},
    ])
    db = SessionLocal()
    try:
        run = db.get(Run, rid)
        run.slots_total = 2
        db.commit()
    finally:
        db.close()

    peak = {"v": 0}
    import threading

    stop = threading.Event()

    def watcher():
        while not stop.is_set():
            r = run_state(rid)
            running = sum(1 for s in r["steps"] if s["status"] == "running")
            peak["v"] = max(peak["v"], running)
            time.sleep(0.02)

    t = threading.Thread(target=watcher, daemon=True)
    t.start()
    start(rid)
    stop.set()
    t.join(timeout=2)
    final = run_state(rid)
    assert final["status"] == "completed"
    assert peak["v"] <= 2, f"并发超出槽位上限：峰值 {peak['v']}"


# ---------------- 集成：技能系统 ----------------
def test_skill_expansion():
    """技能启用 → 节点引用后展开 prompt；禁用 → 报错。"""
    skills = client.get("/api/skills").json()
    assert any(s["name"] == "report.draft" for s in skills)

    rid = make_task([
        {"title": "写初稿", "tool": "fs.write_project",
         "args": {"node_id": "n1", "skill": "report.draft", "path": "deliverables/x.md"}},
    ])
    start(rid)
    final = wait(lambda: (lambda r: r if r["status"] == "completed" else None)(run_state(rid)))
    assert final["done_steps"] == 1
    db = SessionLocal()
    try:
        step = db.scalar(select(Step).where(Step.run_id == rid, Step.seq == 1))
        assert step.args.get("prompt"), "技能应展开出 prompt"
    finally:
        db.close()

    # 禁用技能后应报错
    client.post("/api/skills/report.draft/toggle")
    rid2 = make_task([
        {"title": "写初稿", "tool": "fs.write_project",
         "args": {"node_id": "n1", "skill": "report.draft", "path": "deliverables/y.md"}},
    ], goal="禁用技能用例")
    start(rid2)
    failed = wait(lambda: (lambda r: r if r["status"] in ("failed", "completed") else None)(run_state(rid2)))
    assert failed["status"] == "failed"
    assert "技能不可用" in (failed.get("error") or "")
    client.post("/api/skills/report.draft/toggle")  # 恢复
