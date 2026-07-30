"""Cấu hình chung — đọc từ .env (xem .env.example)."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

GROBID_URL = os.getenv("GROBID_URL", "http://localhost:8070")

# Ưu tiên Qdrant server (docker) nếu có QDRANT_URL; không thì dùng embedded mode
# (chạy trong process, lưu ở data/qdrant — đủ cho dev/test, không cần docker).
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_PATH = os.getenv("QDRANT_PATH", str(ROOT / "data" / "qdrant"))

# "voyage" (mặc định) | "fake" (test/offline, không gọi API)
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "voyage")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")

DATA_DIR = ROOT / "data"
PAPERS_DIR = DATA_DIR / "papers"
SEED_FILE = DATA_DIR / "seed_papers.txt"
SQLITE_PATH = DATA_DIR / "metadata.sqlite"

COLLECTION = "papers"
MAX_CHUNK_TOKENS = 800  # ước lượng ~4 ký tự / token

# Ngôn ngữ trả lời — tách biệt với ngôn ngữ câu hỏi:
# "auto" (mặc định, trả lời theo ngôn ngữ câu hỏi) | "en" | "vi"
ANSWER_LANGUAGE = os.getenv("ANSWER_LANGUAGE", "auto")

# ---- LLM backend ----
# "anthropic" (mặc định, có citations API) | "openai_compat" (Ollama/LM Studio/
# Groq/Gemini... — citation chuyển sang chế độ đánh số nguồn qua prompt)
LLM_BACKEND = os.getenv("LLM_BACKEND", "anthropic")

# Models khi LLM_BACKEND=anthropic — answer dùng opus cho chất lượng; tác vụ
# phụ (expansion) dùng haiku cho rẻ/nhanh. Đổi qua env nếu muốn.
ANSWER_MODEL = os.getenv("ANSWER_MODEL", "claude-opus-5")
EXPAND_MODEL = os.getenv("EXPAND_MODEL", "claude-haiku-4-5")

# Khi LLM_BACKEND=openai_compat: mọi call dùng chung 1 endpoint + 1 model.
# Mặc định trỏ Ollama local; xem SETUP.md mục "Phương án local/free" cho
# base_url của Groq/Gemini/LM Studio.
OPENAI_COMPAT_BASE_URL = os.getenv("OPENAI_COMPAT_BASE_URL", "http://localhost:11434/v1")
OPENAI_COMPAT_API_KEY = os.getenv("OPENAI_COMPAT_API_KEY", "ollama")  # Ollama không cần key thật
OPENAI_COMPAT_MODEL = os.getenv("OPENAI_COMPAT_MODEL", "qwen2.5:14b")

# "voyage" | "local" (bge-*, chạy trên máy, $0) | "fake" (test) | "none" (bỏ re-rank)
RERANK_BACKEND = os.getenv("RERANK_BACKEND", "voyage")

GOLDEN_SET = DATA_DIR / "golden_set.jsonl"
EXPERIMENTS_FILE = ROOT / "EXPERIMENTS.md"
WATCH_FILE = DATA_DIR / "watch_keywords.txt"
