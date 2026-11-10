"""SSE 事件总线：线程安全的发布/订阅。

执行器跑在线程里，SSE 端点跑在事件循环里——用线程安全队列解耦两端：
runner 每次落库后 publish()，SSE 端点订阅后把事件推给浏览器。

两种部署形态：
- 单进程（默认）：内存队列即可；
- 多 worker：设置 REDIS_URL 后启用 Redis pub/sub——本进程 publish 会同步发到
  Redis 频道，每个进程各跑一个订阅线程，把远端事件扇入本地队列。
  publish/subscribe 接口签名不变，业务代码零改动。
"""
import json
import os
import queue
import threading

_lock = threading.Lock()
_subs: list["queue.Queue[tuple[str, str]]"] = []

REDIS_URL = os.getenv("REDIS_URL", "")
REDIS_CHANNEL = os.getenv("SSE_CHANNEL", "ai-team-os.events")
_redis_client = None  # 惰性连接


def _redis():
    global _redis_client
    if _redis_client is None:
        import redis as _redis_mod

        _redis_client = _redis_mod.Redis.from_url(
            REDIS_URL, decode_responses=True, socket_timeout=5
        )
    return _redis_client


def subscribe() -> "queue.Queue[tuple[str, str]]":
    q: "queue.Queue[tuple[str, str]]" = queue.Queue(maxsize=500)
    with _lock:
        _subs.append(q)
    return q


def unsubscribe(q: "queue.Queue[tuple[str, str]]") -> None:
    with _lock:
        try:
            _subs.remove(q)
        except ValueError:
            pass


def _fanout(event: str, msg: str) -> None:
    with _lock:
        subs = list(_subs)
    for q in subs:
        try:
            q.put_nowait((event, msg))
        except queue.Full:
            pass


def publish(event: str, data: dict) -> None:
    """广播一条事件；订阅方拿到 (event_name, json_str)。满队列即丢弃，SSE 只做信号。"""
    msg = json.dumps(data, ensure_ascii=False, default=str)
    _fanout(event, msg)
    if REDIS_URL:
        try:
            _redis().publish(REDIS_CHANNEL, f"{event}\t{msg}")
        except Exception:
            pass  # Redis 故障不阻塞主流程，本地订阅者仍能收到


def _redis_listener() -> None:
    """订阅线程：把其他进程发布到 Redis 的事件扇入本地队列。"""
    import time

    while True:
        try:
            pubsub = _redis().pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(REDIS_CHANNEL)
            for item in pubsub.listen():
                raw = item.get("data")
                if not isinstance(raw, str) or "\t" not in raw:
                    continue
                event, msg = raw.split("\t", 1)
                _fanout(event, msg)
        except Exception:
            time.sleep(1)  # 断线重连


def start() -> None:
    """进程启动时调用：启用 Redis 时拉起跨进程订阅线程。"""
    if REDIS_URL and not getattr(start, "_started", False):
        start._started = True  # type: ignore[attr-defined]
        threading.Thread(target=_redis_listener, daemon=True).start()


def sse_frame(event: str, data: str) -> bytes:
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")
