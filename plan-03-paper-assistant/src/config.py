"""Shared configuration — read from .env (see .env.example)."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

GROBID_URL = os.getenv("GROBID_URL", "http://localhost:8070")

# Prefer a Qdrant server (docker) when QDRANT_URL is set; otherwise embedded
# mode (in-process, stored at data/qdrant — enough for dev/test, no docker).
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_PATH = os.getenv("QDRANT_PATH", str(ROOT / "data" / "qdrant"))

# "voyage" (default) | "fake" (test/offline, no API calls)
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "voyage")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")

DATA_DIR = ROOT / "data"
PAPERS_DIR = DATA_DIR / "papers"
SEED_FILE = DATA_DIR / "seed_papers.txt"
SQLITE_PATH = DATA_DIR / "metadata.sqlite"

COLLECTION = "papers"
MAX_CHUNK_TOKENS = 800  # rough estimate of ~4 chars / token

# Models — answer uses opus for quality; side tasks (expansion) use haiku for
# cheap/fast (see the cost section in SETUP.md). Override via env if desired.
ANSWER_MODEL = os.getenv("ANSWER_MODEL", "claude-opus-5")
EXPAND_MODEL = os.getenv("EXPAND_MODEL", "claude-haiku-4-5")

# "voyage" | "fake" (test/offline) | "none" (skip re-rank, just cut top-k)
RERANK_BACKEND = os.getenv("RERANK_BACKEND", "voyage")

GOLDEN_SET = DATA_DIR / "golden_set.jsonl"
EXPERIMENTS_FILE = ROOT / "EXPERIMENTS.md"
WATCH_FILE = DATA_DIR / "watch_keywords.txt"
