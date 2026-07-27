# Plan 8 — Environment setup

Lighter than Plan 3: **no docker needed** (Qdrant runs in embedded mode inside
the process, stored under `data/qdrant`). You only need Python 3.11+ and (for
live runs) 2 API keys.

## 1. Python

```bash
cd plan-08-npc-memory
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Run offline (no keys) — verify immediately

```bash
python -m pytest tests/ -q        # expected: 30 passed
```

The test suite forces `EMBED_BACKEND=fake` + `LLM_BACKEND=none` itself and
makes zero network calls.

To run the **server** offline (the NPC only speaks canned lines, but memory
read/write works fully):

```bash
EMBED_BACKEND=fake LLM_BACKEND=none uvicorn src.server:app --port 8080
```

## 3. API keys (for live runs)

```bash
cp .env.example .env   # then fill in:
```

| Key | Where to get it | Used for |
|-----|-----------------|----------|
| `ANTHROPIC_API_KEY` | console.anthropic.com | Dialogue (Haiku), importance scoring (Haiku), reflection (Sonnet), judge |
| `VOYAGE_API_KEY` | dash.voyageai.com | Embedding memories + queries (voyage-3, multilingual) |

**Estimated dev cost** (a few hundred dialogue turns/day): Haiku 4.5 is $1/$5
per MTok; each turn is ~1–2K tokens in + ~100 tokens out → on the order of a
few cents/day. Reflection (Sonnet 5) only runs once importance accumulates to
≥ 150 — a few times per play day. voyage-3 embedding cost is negligible at
this scale. Prompt caching: see the Haiku note in TEST_AT_HOME step 5.

## 4. Qdrant server (optional, not needed yet)

Embedded mode covers the whole plan. Only when multiple processes must share
one index:

```bash
docker run -p 6333:6333 -v $(pwd)/data/qdrant-server:/qdrant/storage qdrant/qdrant
# .env: QDRANT_URL=http://localhost:6333
```

**Note:** switching `EMBED_BACKEND` (fake ↔ voyage) changes the vector
dimension — delete `data/qdrant/` and re-index; never mix the two vector
types in one collection.

## 5. Directory layout after running

```
data/
├── personas.example.json  # 2 sample NPCs (committed) — copy to personas.json to edit
├── personas.json          # your game's personas (gitignored; falls back to the example)
├── memories.sqlite        # memory records + relationships (auto-created)
├── qdrant/                # embedded vector index (auto-created)
└── dialogue_log.jsonl     # full conversation log (auto-created — for exploit/injection review)
```
