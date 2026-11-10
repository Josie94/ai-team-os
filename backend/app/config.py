"""全局配置：全部通过环境变量覆盖，无 key 时自动降级为本地模拟，保证离线可跑。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DELIVERABLE_DIR = DATA_DIR / "deliverables"
DELIVERABLE_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'app.db'}")

# OpenAI 兼容模型网关
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))

# 执行器节奏（秒），演示用，可通过环境变量关掉
STEP_DELAY = float(os.getenv("STEP_DELAY", "1.2"))
RUN_ASYNC = os.getenv("RUN_ASYNC", "1") == "1"
