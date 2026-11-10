from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import BASE_DIR
from .db import SessionLocal, init_db
from . import events
from .seed import run_seed


@asynccontextmanager
async def lifespan(_: FastAPI):
    events.start()  # 配置 REDIS_URL 时拉起跨进程订阅线程
    init_db()
    db = SessionLocal()
    try:
        run_seed(db)
    finally:
        db.close()
    yield


app = FastAPI(title="AI Team OS · Phase 1 MVP", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/")
def root():
    return {"service": "ai-team-os", "docs": "/docs", "api": "/api/health"}


# 生产构建后单端口托管（frontend/dist 存在时生效）
_dist = Path(BASE_DIR).parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/app", StaticFiles(directory=str(_dist), html=True), name="app")
