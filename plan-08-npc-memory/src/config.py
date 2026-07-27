"""Shared configuration — read from .env (see .env.example)."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"

# "voyage" (default) | "fake" (test/offline, no API calls)
EMBED_BACKEND = os.getenv("EMBED_BACKEND", "voyage")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")

# "anthropic" (default) | "none" (server runs without an LLM — importance uses
# the fixed table/defaults, no dialogue). Tests don't use this variable: they
# inject ScriptedLLM directly.
LLM_BACKEND = os.getenv("LLM_BACKEND", "anthropic")

# Prefer a Qdrant server (docker) when QDRANT_URL is set; otherwise embedded
# mode (in-process, stored under data/qdrant — enough for dev/test, no docker).
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_PATH = os.getenv("QDRANT_PATH", str(DATA_DIR / "qdrant"))
SQLITE_PATH = DATA_DIR / "memories.sqlite"
COLLECTION = "npc_memories"

# Models (README section 5.1): Haiku for dialogue + importance scoring
# (latency/cost), Sonnet for background reflection (doesn't block dialogue).
DIALOGUE_MODEL = os.getenv("DIALOGUE_MODEL", "claude-haiku-4-5")
SCORING_MODEL = os.getenv("SCORING_MODEL", "claude-haiku-4-5")
REFLECTION_MODEL = os.getenv("REFLECTION_MODEL", "claude-sonnet-5")

# Dialogue latency budget (seconds) — past this, fall back to a canned line
# (the NPC never freezes)
DIALOGUE_TIMEOUT = float(os.getenv("DIALOGUE_TIMEOUT", "10"))

# personas.json (gitignored — your game content); when missing, the server
# falls back to personas.example.json (2 sample NPCs, committed)
PERSONAS_FILE = DATA_DIR / "personas.json"
PERSONAS_EXAMPLE = DATA_DIR / "personas.example.json"
DIALOGUE_LOG = DATA_DIR / "dialogue_log.jsonl"
