"""Cấu hình chung — đọc từ .env (xem .env.example)."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
SQLITE_PATH = DATA_DIR / "memories.sqlite"
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_PATH = os.getenv("QDRANT_PATH", str(DATA_DIR / "qdrant"))
COLLECTION = "npc_memories"

# ---- Embedding: voyage | local (bge-m3) | fake ----
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "local")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")

# ---- LLM: anthropic | openai_compat | fake (test/CI) ----
LLM_BACKEND = os.getenv("LLM_BACKEND", "anthropic")
DIALOGUE_MODEL = os.getenv("DIALOGUE_MODEL", "claude-haiku-4-5")     # latency thấp
REFLECTION_MODEL = os.getenv("REFLECTION_MODEL", "claude-sonnet-5")  # chạy nền
IMPORTANCE_MODEL = os.getenv("IMPORTANCE_MODEL", "claude-haiku-4-5")
OPENAI_COMPAT_BASE_URL = os.getenv("OPENAI_COMPAT_BASE_URL", "http://localhost:11434/v1")
OPENAI_COMPAT_API_KEY = os.getenv("OPENAI_COMPAT_API_KEY", "ollama")
OPENAI_COMPAT_MODEL = os.getenv("OPENAI_COMPAT_MODEL", "qwen2.5:14b")

# ---- Retrieval 3 trục (README mục 4.3) — bắt đầu 1/1/1 như paper gốc ----
ALPHA = float(os.getenv("ALPHA", "1.0"))    # recency
BETA = float(os.getenv("BETA", "1.0"))      # importance
GAMMA = float(os.getenv("GAMMA", "1.0"))    # relevance
RECENCY_DECAY = float(os.getenv("RECENCY_DECAY", "0.995"))  # ^ số giờ

# ---- Reflection ----
REFLECTION_THRESHOLD = int(os.getenv("REFLECTION_THRESHOLD", "150"))

RETRIEVE_TOP_K = 12          # số ký ức đưa vào prompt thoại
CANDIDATE_POOL = 50          # vector search lấy thô trước khi chấm 3 trục
