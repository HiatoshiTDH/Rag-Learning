# Full verification on your home machine

All P1→P5 code is written and passes 26 offline tests. This document is **the order to run a full verification on a real machine** — work top to bottom; every step has an expected output. Estimate: ~30–45 minutes (mostly waiting for GROBID to parse).

> Shortcut: `./scripts/smoke_test.sh` runs steps 1→6 automatically and prints PASS/FAIL per item.

## Step 0 — Clone & install (once)

```bash
git clone <repo> && cd Rag-Learning/plan-03-paper-assistant
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Step 1 — Offline tests (no docker/keys needed)

```bash
EMBED_BACKEND=fake RERANK_BACKEND=fake python -m pytest tests/ -q
```

**Expected:** `26 passed`. A failure here = a code/Python-environment problem, nothing to do with docker or the API yet.

## Step 2 — Bring up the services

```bash
docker compose up -d
curl http://localhost:8070/api/isalive     # → true (GROBID needs ~30-60s on first start)
```

Open http://localhost:6333/dashboard — seeing the Qdrant UI means it's OK.

## Step 3 — Fill in the configuration

```bash
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY (console.anthropic.com), VOYAGE_API_KEY (dash.voyageai.com)
python -c "from src.embedding import get_embedder; get_embedder(); print('Voyage OK')"
```

**Expected:** `Voyage OK`. To try things first without paying for embeddings: `EMBED_BACKEND=fake` (but search results will be semantically meaningless — only for checking the pipeline runs end to end).

## Step 4 — Real ingest (P1 live)

Add 2–3 arXiv ids to `data/seed_papers.txt` (start small so it's fast), then:

```bash
python -m src.cli ingest
```

**Expected:** one line per paper `  <id>: N sections, M chunks`, ending with `Done: ... chunks. Errors: none`.
Cross-checks:
- `python -m src.cli list` → shows the paper list
- Qdrant dashboard → collection `papers` → inspect a few points: payload must have correct `section`, `section_type`
- Run `python -m src.cli ingest` a second time → **chunk count does not grow** (idempotent)

## Step 5 — Real questions (P2–P4 live)

```bash
# Ordinary question (the router handles it)
python -m src.cli ask "What problem does paper <id> solve?"

# Restrict to a section
python -m src.cli ask "what is the main method?" --paper <id> --section-type method

# Comparison (needs >=2 ingested papers)
python -m src.cli compare "how do these two papers differ in their evaluation?" <id1> <id2>
```

**Expected:** an answer + a `Sources:` section listing `[n] Paper title — Section name`. An answer **with no citations at all** for a content question = something's wrong, see Troubleshooting.

**Cost of this step:** a few cents (opus-5). To keep repeat runs cheap: add `--no-expand` and/or set `ANSWER_MODEL=claude-sonnet-5` in `.env`.

## Step 6 — Golden set + baseline measurement (P2.3–2.4)

```bash
cp data/golden_set.example.jsonl data/golden_set.jsonl
# Edit into 10-30 real questions on papers YOU have read (grow gradually; 10 is enough to start)

python -m src.cli eval --stage v1     --note "baseline pure vector"
python -m src.cli eval --stage hybrid --note "+BM25/RRF"
python -m src.cli eval --stage rerank --note "+voyage rerank"
python -m src.cli eval --stage full   --note "+expansion"
```

**Expected:** 4 new rows in `EXPERIMENTS.md`, recall rising (or at least not falling) across stages. This is task 3.5 — from now on every change is compared against these numbers.

## Step 7 — (Optional) Weekly auto-ingest (P5.2)

```bash
# Uncomment/add keywords in data/watch_keywords.txt then:
python -m src.cli watch

# Cron every Monday at 8am:
# 0 8 * * 1  cd /path/to/plan-03-paper-assistant && .venv/bin/python -m src.cli watch >> watch.log 2>&1
```

---

## Troubleshooting

| Symptom | Common cause | Fix |
|---------|--------------|-----|
| GROBID 503 / connection refused | Not finished starting (first run downloads models, ~30-60s) | Wait, then `curl .../api/isalive` again |
| GROBID fails on one specific paper | Unusual/scanned PDF layout | Drop that paper from the seed — expected per PLAN (risk #1) |
| Qdrant dimension mismatch error | Switched `EMBED_BACKEND` (fake 256 dims ↔ voyage 1024 dims) | Delete the collection: `docker compose down && docker volume rm plan-03-paper-assistant_qdrant_storage` (or delete `data/qdrant/` if embedded) then re-ingest |
| `anthropic.AuthenticationError` | Wrong/missing key in `.env` | Check `.env`; make sure `source .venv/bin/activate` ran in the right directory |
| Voyage 401 | Same as above for `VOYAGE_API_KEY` | — |
| Answers without citations | Question outside the paper corpus (correct behavior: the model must say "not covered") or retrieval missed | Try `ask --paper <id>` to narrow down; if it still misses → add the case to the golden set and debug with `eval` |
| Vietnamese questions much worse than English | Expansion didn't run (using `--no-expand`?) | Drop `--no-expand` — the English translation lives in expansion |
| `Golden set empty` during eval | Example not copied to `golden_set.jsonl` | Step 6 |

## Mapping to PLAN.md

| Step above | Phase in PLAN | After this step the phase counts as |
|------------|---------------|--------------------------------------|
| 1 | (code check) | — |
| 2–3 | P0 | ✅ complete |
| 4 | P1 | ✅ complete (the missing live part) |
| 5 | P2.2/2.5, P3, P4 | ✅ code complete; quality tuned further via step 6 |
| 6 | P2.3–2.4 + P3.5 | ✅ baseline with numbers |
| 7 | P5.2 | ✅ complete |

After all 7 steps pass: the project is in "daily real use" shape — what remains is growing the golden set and tuning by the numbers.
