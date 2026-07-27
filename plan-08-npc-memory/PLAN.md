# Plan 8 — Full execution plan (NPC Memory RAG)

> This document is the **detailed execution plan** — phases, tasks, definition of done.
> Architecture & design rationale: see [README.md](README.md). Environment setup: [SETUP.md](SETUP.md).

> **📍 CURRENT STATUS: P1→P5 code complete, 30 offline tests passing.**
> What remains happens on your home machine (needs API keys + network):
> follow **[TEST_AT_HOME.md](TEST_AT_HOME.md)** — the live B1 test ships as `python -m scripts.demo_b1`.
> Not yet coded: wiring into a real game (P6 — needs a Unity/Roblox project) and NPC-to-NPC memory sharing (B4, see Out of scope).

## Execution principles

1. **Offline-first** — every core mechanism is testable with `pytest` and no keys/docker/game
   (HashEmbedder + in-memory Qdrant + ScriptedLLM). Real keys are only needed to measure *quality*.
2. **Test memory like you test code** (README section 7) — the B1/B2/B3 + injection scenarios live
   in `tests/test_memory.py`; whenever α/β/γ weights or the reflection threshold change, re-run the suite.
3. **The LLM never decides gameplay** — every consequence goes through `propose_game_action` +
   server-side `validate_action`, DENY by default.

## Phase overview

| Phase | Week (README) | Name | Status | Runnable result |
|-------|---------------|------|--------|-----------------|
| P0 | — | Environment setup | ✅ (see SETUP.md) | `pytest` green on a bare machine, no docker |
| P1 | 1 | Memory stream: schema + read/write + vector search | ✅ code + tests | Write 31 memories, retrieve correctly, scoped by npc_id |
| P2 | 2 | Three-axis retrieval + B1 test harness | ✅ code + tests | B1 passes: the promise beats 30 noise events |
| P3 | 3 | Memory service (FastAPI) + streaming + prefetch + fallback | ✅ code + tests | WS `/talk` streams chunk by chunk; timeout → canned line |
| P4 | 4 | Importance scoring + relationship state | ✅ code + tests | B2: theft → negative affinity → price ×1.15–1.3 |
| P5 | 5–6 | Reflection worker | ✅ code + tests | B3 passes; insights must carry source_ids |
| P6 | 7–8 | Real game integration + live hardening + tuning | ⬜ home machine / game project | See TEST_AT_HOME.md |

---

## P1 — Memory stream (week 1)

| # | Task | File | DoD | Status |
|---|------|------|-----|--------|
| 1.1 | `MemoryRecord` schema + `MemoryRecord.new` helper | `src/memory_store.py` | auto id/timestamps, participants + source_ids | ✅ |
| 1.2 | `MemoryStore.add`: embed + SQLite + Qdrant upsert, idempotent | `src/memory_store.py` | running twice doesn't duplicate | ✅ |
| 1.3 | `candidates()`: top-50 vector search, **scoped by npc_id** | `src/memory_store.py` | no-leak test passes | ✅ |
| 1.4 | `touch()`: retrieved memories become fresh again | `src/memory_store.py` | `test_retrieval_refreshes_memory` | ✅ |
| 1.5 | 2 embedder backends: voyage (real) / hash (offline) | `src/embedding.py` | switched via `EMBED_BACKEND` env | ✅ |

## P2 — Three-axis retrieval (week 2)

| # | Task | File | DoD | Status |
|---|------|------|-----|--------|
| 2.1 | `score = α·recency + β·importance + γ·relevance`, decay 0.995^hours | `src/scoring.py` | arithmetic unit tests pass | ✅ |
| 2.2 | `retrieve()`: score three axes over top-50, return 8–15, auto-touch | `src/scoring.py` | `test_retrieve_ranks_and_touches_only_top` | ✅ |
| 2.3 | Scenario B1 in the test harness | `tests/test_memory.py` | promise (5h, imp 8) beats 30 noise events (0.5h, imp 2) | ✅ |
| 2.4 | Important-beats-trivia scenario | `tests/test_memory.py` | imp 9 (72h ago) beats imp 1 (3 minutes ago) | ✅ |
| 2.5 | Tune α/β/γ for game feel with real embeddings | — | done in P6, with numbers recorded | ⬜ |

## P3 — Memory service + dialogue (week 3)

| # | Task | File | DoD | Status |
|---|------|------|-----|--------|
| 3.1 | System prompt: persona + anti-injection rules, `cache_control` on the last block | `src/dialogue.py` | prompt caching + rules tests | ✅ |
| 3.2 | `respond()`: stream text chunks, tool_use goes through validation | `src/dialogue.py` | `text`/`action`/`fallback` event generator | ✅ |
| 3.3 | Canned fallback by relationship on API error/timeout | `src/dialogue.py` | `test_timeout_falls_back...`; the NPC never freezes | ✅ |
| 3.4 | `validate_action`: item/quest whitelist, price bounds, DENY by default | `src/dialogue.py` | injection test: 9999 gold blocked | ✅ |
| 3.5 | FastAPI: `POST /event`, `POST /prefetch`, `WS /talk`, dialogue log | `src/server.py` | TestClient + websocket tests pass | ✅ |
| 3.6 | Injectable LLM wrapper + `ScriptedLLM` for tests | `src/llm.py` | every offline test makes zero network calls | ✅ |

## P4 — Importance + relationships (week 4)

| # | Task | File | DoD | Status |
|---|------|------|-----|--------|
| 4.1 | `FIXED_IMPORTANCE` table for clearly-typed events — no LLM call | `src/scoring.py` | gift=7, attack=9 with no LLM call | ✅ |
| 4.2 | Batch-score 10–20 events/call with Haiku + structured output, clamp 1–10 | `src/scoring.py` | 1 call per batch, 42 → 10 | ✅ |
| 4.3 | `RelationshipTracker`: affinity accumulated from a fixed delta table | `src/relationship.py` | B2: gift +2, attack −6 → cold | ✅ |
| 4.4 | Relationship label into the dialogue prompt + price multiplier for the game server | `src/relationship.py`, `src/dialogue.py` | `PRICE_MULTIPLIER[cold] = 1.15` | ✅ |

## P5 — Reflection worker (weeks 5–6)

| # | Task | File | DoD | Status |
|---|------|------|-----|--------|
| 5.1 | Trigger: total new-memory importance ≥ 150 (watermark = latest reflection) | `src/reflection.py` | 144 → False, 152 → True; resets after reflect | ✅ |
| 5.2 | 3 steps: high-level questions → retrieve → insight (Sonnet) | `src/reflection.py` | B3 passes in the harness | ✅ |
| 5.3 | Anti-fabrication: LLM returns source **indexes**, we map to ids; no sources → dropped | `src/reflection.py` | `test_insight_without_sources_is_dropped` | ✅ |
| 5.4 | `POST /reflect` endpoint (called periodically by a worker/cron) | `src/server.py` | forced-reflect test passes | ✅ |

## P6 — Home machine + real game (weeks 7–8) — REMAINING

| # | Task | DoD |
|---|------|-----|
| 6.1 | Run [TEST_AT_HOME.md](TEST_AT_HOME.md): offline suite → live server → `scripts/demo_b1` | Live B1 PASS with real embeddings + LLM |
| 6.2 | Tune α/β/γ + top_k with real voyage-3 (HashEmbedder says nothing about quality) | Numbers recorded in `EXPERIMENTS.md`, like Plan 3 |
| 6.3 | Wire 1 NPC into the game (Unity: UnityWebRequest/WebSocket; Roblox: HttpService) | In-game conversation < 2s perceived latency |
| 6.4 | Prefetch on trigger radius + verify cache_read_input_tokens > 0 from turn 2 | See the Haiku 4096-token note in TEST_AT_HOME |
| 6.5 | Manual adversarial testing (all injection flavors) against the real LLM | No action accepted; everything logged |

---

## Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Dialogue > 2s ruins game feel | Medium | High | Streaming + prefetch already coded; measure for real in 6.3, then shrink top_k / persona if needed |
| Retrieval tuned on HashEmbedder doesn't reflect real voyage | Certain | Medium | HashEmbedder only tests mechanics; quality tuning must happen in 6.2 with real keys |
| LLM tricked into proposing bogus actions | High | Low | DENY-by-default validation already blocks consequences; what's left is dialogue tone — hardening in 6.5 |
| Stream grows without bound | Medium | Medium | Reflection compresses; demoting/deleting old fragments is a later extension (not needed at test scale) |
| API cost with many NPCs | Medium | Medium | FIXED_IMPORTANCE table + batch scoring + only 3–10 key NPCs get RAG (README 5.2) |

## Technical decisions (decision log)

| Decision | Choice | Why | Revisit when |
|----------|--------|-----|--------------|
| Vector DB | Qdrant embedded (no docker) | Enough for one dev machine; same family as Plan 3 | Multiple game servers → Qdrant server (`QDRANT_URL`) |
| Record store | SQLite next to Qdrant | Easy `last_accessed` updates + reflection queries | Multiple service instances → Postgres |
| Embedding | voyage-3 (fake: hash) | Multilingual — memories in any language | Cost → local bge-m3 |
| Dialogue + scoring LLM | claude-haiku-4-5 | Fastest; enough for short NPC lines | Flat dialogue → try Sonnet for key NPCs |
| Reflection LLM | claude-sonnet-5 | Background job; insight quality matters | Cost → lower reflect frequency before downgrading the model |
| Importance without an LLM | Fixed table + default 3 | Service survives LLM_BACKEND=none | — |
| Reflection sources | LLM returns indexes, code maps to ids | LLMs echo long ids badly; indexes + own mapping is safer | — |
| Action validation | Whitelist + DENY by default | Players WILL talk NPCs into giving items | — |

## Out of scope (fixed, to avoid creep)

- **B4 — NPC-to-NPC memory sharing** (rumor spreading): after B1–B3 run well in a real game
- Planning layer (NPC daily schedules) — README section 9
- Demoting/deleting compressed memory fragments (needed once the stream actually grows)
- Game-engine code (Unity C#/Roblox Lua) — this repo contains only the memory service
- Multi-tenant / multiple game servers sharing one service
