"""Cấu hình chung — đọc từ .env (xem .env.example)."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"

# "voyage" (mặc định) | "fake" (test/offline, không gọi API)
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "voyage")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")

# "anthropic" (mặc định) | "none" (server chạy không có LLM — importance dùng
# bảng cứng/mặc định, không dialogue). Test không dùng biến này: inject ScriptedLLM.
LLM_BACKEND = os.getenv("LLM_BACKEND", "anthropic")

# Ưu tiên Qdrant server (docker) nếu có QDRANT_URL; không thì embedded mode
# (chạy trong process, lưu ở data/qdrant — đủ cho dev/test, không cần docker).
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_PATH = os.getenv("QDRANT_PATH", str(DATA_DIR / "qdrant"))
SQLITE_PATH = DATA_DIR / "memories.sqlite"
COLLECTION = "npc_memories"

# Models (README mục 5.1): Haiku cho thoại + chấm importance (latency/cost),
# Sonnet cho reflection chạy nền (không chặn hội thoại).
DIALOGUE_MODEL = os.getenv("DIALOGUE_MODEL", "claude-haiku-4-5")
SCORING_MODEL = os.getenv("SCORING_MODEL", "claude-haiku-4-5")
REFLECTION_MODEL = os.getenv("REFLECTION_MODEL", "claude-sonnet-5")

# Latency budget cho thoại (giây) — quá hạn thì trả canned fallback (README 5.1)
DIALOGUE_TIMEOUT = float(os.getenv("DIALOGUE_TIMEOUT", "10"))

# personas.json (gitignore — nội dung game của bạn); chưa có thì server
# fallback sang personas.example.json (2 NPC mẫu, được commit)
PERSONAS_FILE = DATA_DIR / "personas.json"
PERSONAS_EXAMPLE = DATA_DIR / "personas.example.json"
DIALOGUE_LOG = DATA_DIR / "dialogue_log.jsonl"
