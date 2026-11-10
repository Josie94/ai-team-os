"""最小闭环回归：对话 → 任务 → 审批断点 → 断点续跑 → 交付物。"""
import os
import tempfile
import time

DB = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{DB}"
os.environ["STEP_DELAY"] = "0"
os.environ["RUN_ASYNC"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import run_seed  # noqa: E402
from app.state_machine import IllegalTransition, transit  # noqa: E402

init_db()
_db = SessionLocal()
run_seed(_db)
_db.close()

client = TestClient(app)


def wait(predicate, timeout=12):
    end = time.time() + timeout
    while time.time() < end:
        v = predicate()
        if v:
            return v
        time.sleep(0.1)
    raise AssertionError("超时未达到预期状态")


def test_chat_creates_task():
    r = client.post("/api/chat", json={"text": "整理本周团队周报并外发"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["task_id"] and body["run_id"]
    assert "已转为任务" in body["reply"]


def test_smalltalk_no_task():
    r = client.post("/api/chat", json={"text": "你是谁"})
    assert r.status_code == 200
    assert r.json()["task_id"] is None


def test_approval_breakpoint_and_resume():
    r = client.post("/api/tasks", json={"goal": "撰写白皮书初稿并外发评审"})
    run_id = r.json()["run"]["id"]

    def pending():
        rows = client.get("/api/approvals?status=pending").json()
        return [a for a in rows if a["run_id"] == run_id]

    aps = wait(pending)
    ap = aps[0]
    assert ap["risk"] == "high"
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "awaiting_approval"
    # 断点处不执行外发：该 step 仍是等待审批
    assert any(s["status"] == "awaiting_approval" for s in run["steps"])

    d = client.post(f"/api/approvals/{ap['id']}/decision", json={"decision": "approve"})
    assert d.status_code == 200, d.text

    def completed():
        r = client.get(f"/api/runs/{run_id}").json()
        return r if r["status"] == "completed" else None

    final = wait(completed)
    assert final["done_steps"] == final["total_steps"]
    assert final["deliverables"], "完成态必须有交付物"
    assert len(final["deliverables"][0]["sha256"]) == 64

    # 幂等：同一审批再次决策应失败
    again = client.post(f"/api/approvals/{ap['id']}/decision", json={"decision": "approve"})
    assert again.status_code == 409


def test_reject_stops_run():
    r = client.post("/api/tasks", json={"goal": "扫描竞品动态并外发简报"})
    run_id = r.json()["run"]["id"]

    def pending():
        rows = client.get("/api/approvals?status=pending").json()
        return [a for a in rows if a["run_id"] == run_id]

    ap = wait(pending)[0]
    client.post(f"/api/approvals/{ap['id']}/decision", json={"decision": "reject", "note": "口径未确认"})

    def rejected():
        r = client.get(f"/api/runs/{run_id}").json()
        return r if r["status"] == "rejected" else None

    assert wait(rejected)["status"] == "rejected"


def test_illegal_transition_rejected():
    class Obj:
        status = "completed"

    try:
        transit(Obj(), "running")
    except IllegalTransition:
        return
    raise AssertionError("终态不应允许迁回执行中")
