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

# Models — answer dùng opus cho chất lượng; tác vụ phụ (expansion) dùng haiku
# cho rẻ/nhanh (xem SETUP.md mục chi phí). Đổi qua env nếu muốn.
ANSWER_MODEL = os.getenv("ANSWER_MODEL", "claude-opus-5")
EXPAND_MODEL = os.getenv("EXPAND_MODEL", "claude-haiku-4-5")

# "voyage" | "fake" (test/offline) | "none" (bỏ qua re-rank, chỉ cắt top-k)
RERANK_BACKEND = os.getenv("RERANK_BACKEND", "voyage")

GOLDEN_SET = DATA_DIR / "golden_set.jsonl"
EXPERIMENTS_FILE = ROOT / "EXPERIMENTS.md"
WATCH_FILE = DATA_DIR / "watch_keywords.txt"
