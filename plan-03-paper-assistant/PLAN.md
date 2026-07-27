# Plan 3 — Full execution plan (Paper Assistant)

> This document is the **detailed execution plan** — phases, tasks, definitions of done, hour estimates.
> Architecture & design rationale: see [README.md](README.md). Environment preparation: see [SETUP.md](SETUP.md).

> **📍 CURRENT STATUS: all P1→P5 code is written; the 26 offline tests pass.**
> Remaining work happens on the home machine (needs Docker + API keys + network access to arXiv):
> follow **[TEST_AT_HOME.md](TEST_AT_HOME.md)** — or `./scripts/smoke_test.sh` for the automated version.
> The only unwritten code: 5.4 web UI (optional; only build it if the CLI feels lacking).

## Execution principles

1. **Every phase ends with something runnable** — no phase is "code written but nothing testable".
2. **The golden set exists from Phase 2**, before optimizing anything. Every later change must come with numbers to prove it.
3. Work sequentially P0 → P5. Within a phase, tasks may be interleaved.

## Phase overview

| Phase | Name | Time | Runnable outcome |
|-------|-----|-----------|-------------------|
| P0 | Environment preparation | 0.5 day | GROBID + Qdrant running locally, API keys working |
| P1 | Ingest pipeline | Week 1 | 10 papers indexed, chunks inspectable with correct sections |
| P2 | Query v1 + Golden set | Week 2 | Ask → answer with correct citations (pure vector search) |
| P3 | Advanced retrieval | Weeks 2–3 | Hybrid + re-rank + parent-doc, measured recall improvement |
| P4 | Query expansion + multi-paper | Week 3 | Vietnamese questions work; comparing 2+ papers works |
| P5 | Package for daily use | Week 4 | CLI + auto-ingest from arXiv by keyword |

---

## P0 — Environment preparation (0.5 day)

Detailed checklist in [SETUP.md](SETUP.md). Summary:

- [ ] `docker compose up -d` → GROBID (8070) + Qdrant (6333) running
- [ ] `.env` has `ANTHROPIC_API_KEY` + `VOYAGE_API_KEY` (or choose the local-free option)
- [ ] `pip install -r requirements.txt` inside a venv
- [ ] Sanity check: curl GROBID returns `GROBID service is up`, open the Qdrant dashboard `localhost:6333/dashboard`
- [ ] Pre-select **10 starter papers** in your research direction (pick papers you have read carefully — needed for the golden set in P2)

## P1 — Ingest pipeline (week 1, ~12–16h)

> **Status: ✅ code + tests done** (12 offline tests pass — TEI parsing, chunking, index, search, idempotency).
> Remaining for P1: run live on a machine with Docker — `docker compose up -d`, fill in seed_papers.txt, then `python -m src.ingest_all` (the network parts of tasks 1.1/1.2 are already coded, just need to run).

| # | Task | File | DoD | Hours |
|---|------|------|-----|-----|
| 1.1 | Download papers from the arXiv API by id/keyword, save PDF + metadata | `src/ingest.py::fetch_arxiv` | 10 PDFs in `data/papers/`, with accompanying metadata JSON | 2 |
| 1.2 | Call GROBID, parse TEI XML into structure (title, sections, paragraphs) | `src/ingest.py::parse_pdf` | Can print the section tree of 1 paper, in order, with no two-column mixing | 3 |
| 1.3 | Structure-aware chunking + `section_type` normalization | `src/ingest.py::chunk_paper` | Chunks carry full metadata; abstract is its own chunk; References excluded | 4 |
| 1.4 | Batch embedding + Qdrant upsert (full payload) | `src/index.py` | Trying 1 query in the Qdrant dashboard returns a sensible chunk | 3 |
| 1.5 | Store full-text sections in SQLite (for parent-doc later) | `src/index.py` | Querying SQLite by `parent_section_id` returns the right section | 2 |
| 1.6 | Script `python -m src.ingest_all` runs the whole pipeline over the folder | new | One command indexes all 10 papers, idempotent (rerun creates no duplicates) | 2 |

**Pitfalls to avoid in P1** (details in README section 6): two-column PDFs, References polluting retrieval, chunks cutting across paragraphs.

## P2 — Query v1 + Golden set (week 2, ~10–14h)

| # | Task | File | DoD | Hours |
|---|------|------|-----|-----|
| 2.1 | Pure vector search: embed the question → top-8 chunks | `src/query.py::hybrid_search` (v1 version) | Returns chunks + metadata + score | 2 |
| 2.2 | Generation with the citations API (document blocks) | `src/answer.py::answer` | Answer with citations pointing to the right paper/section, rendered as text | 4 |
| 2.3 | **Golden set of ~30 questions** over the 10 well-read papers | `tests/test_retrieval.py` | Each question has `expect_paper` (+ `expect_section_type` when clear) | 3 |
| 2.4 | Script measuring recall@8 + report | `tests/` | Running `pytest` produces a baseline number, recorded in `EXPERIMENTS.md` | 2 |
| 2.5 | Minimal CLI: `python -m src.ask "question"` | new | Usable from the terminal | 1 |

**Key milestone:** the baseline recall number from 2.4 is the yardstick for all of P3. Record it carefully.

## P3 — Advanced retrieval (weeks 2–3, ~12–16h)

| # | Task | File | DoD | Hours |
|---|------|------|-----|-----|
| 3.1 | BM25 index over all chunks + RRF merged with vector | `src/query.py` | Recall@8 ≥ baseline (expected gains on questions containing terminology/proper names) | 4 |
| 3.2 | Metadata filter (paper_id, section_type) when the question is explicit | `src/query.py` | Asking "in paper X..." searches only paper X | 2 |
| 3.3 | Re-ranking top-40 → top-8 | `src/query.py::rerank` | Recall@8 up vs 3.1, numbers recorded in `EXPERIMENTS.md` | 3 |
| 3.4 | Parent-document retrieval (chunk → whole section, dedupe) | `src/query.py::to_parent_sections` | Answer quality improves on "explain how..." questions | 3 |
| 3.5 | Rerun the golden set after every change, lock in the best config | `EXPERIMENTS.md` | Comparison table: v1 / +BM25 / +rerank / +parent-doc | 2 |

## P4 — Query expansion + multi-paper (week 3, ~8–12h)

| # | Task | File | DoD | Hours |
|---|------|------|-----|-----|
| 4.1 | Query expansion: 2–3 variants + English translation | `src/query.py::expand_query` | Asking in Vietnamese gets recall on par with asking in English | 3 |
| 4.2 | Map-reduce for comparison questions: retrieve/summarize per paper → synthesize | `src/answer.py::compare_papers` | "Compare how A and B measure X" yields a comparison table with citations on both sides | 4 |
| 4.3 | Simple router: single-paper vs multi-paper vs overview questions | `src/answer.py` | Automatically picks the right flow for the 3 question types in the golden set | 3 |

## P5 — Package for daily use (week 4, ~8–12h)

| # | Task | File | DoD | Hours |
|---|------|------|-----|-----|
| 5.1 | Complete CLI: `ask`, `ingest`, `list`, `compare` | `src/cli.py` | Full `--help`, clear errors | 3 |
| 5.2 | Auto-ingest: cron/script scanning arXiv by keyword weekly | new | Runs periodically, only ingests new papers (dedupe by arXiv id) | 3 |
| 5.3 | Prompt caching for the system portion + repeated documents | `src/answer.py` | `cache_read_input_tokens > 0` from the 2nd request onward | 2 |
| 5.4 | (Optional) Minimal web UI — only if the CLI feels lacking | new | — | 4 |

---

## Risks & mitigations

| Risk | Probability | Impact | Mitigation |
|--------|----------|-----------|-----------|
| GROBID fails to parse some papers (odd layout, scans) | High | Medium | Skip failing papers in v1, log them; do not try to handle every PDF |
| Low recall on Vietnamese questions | High | High | 4.1 is mandatory, not optional; always include an EN translation among the query variants |
| API costs exceed expectations | Low | Low | See the SETUP.md cost table; enable prompt caching (5.3); develop against the small 10-paper set |
| Numeric tables in papers cannot be extracted | Certain | Low | Accept in v1 (document the limitation); upgrade with a vision model later (hand off to Plan 11) |
| Tuning retrieval by gut feeling, no convergence | Medium | High | Golden set from P2 + `EXPERIMENTS.md`; merge no change without numbers |

## Technical decisions locked in (decision log)

| Decision | Choice | Reason | Revisit when |
|-----------|------|-------|-------------|
| PDF parser | GROBID | Purpose-built for academic papers, outputs TEI XML with sections | GROBID fails on >20% of papers |
| Vector DB | Qdrant | Strong payload filtering, easy local docker | Managed/cloud needed |
| Embedding | voyage-3 (option: bge-m3 local) | Multilingual, good quality | Cost becomes an issue → bge-m3 |
| Re-ranker | voyage-rerank-2 (option: bge-reranker-v2-m3 local) | Same Voyage ecosystem | Same as above |
| Answering LLM | claude-opus-5 | Best synthesis + citations quality | Cost too high → claude-sonnet-5 for simple questions |
| Metadata store | SQLite | Enough for single-user, zero-config | Multiple users → Postgres (+pgvector, consider merging vectors in too) |

## Out of scope (locked to prevent scope creep)

- Extracting numeric tables/figures (→ Plan 11)
- Citation graph between papers (→ Plan 9)
- Multi-user, permissions
- Fine-tuning embeddings

## Experiment tracking

Create `EXPERIMENTS.md` from P2; one row per golden-set run:

```
| Date | Config | recall@8 | Notes |
|------|----------|----------|---------|
| ...  | v1 vector-only | 0.xx | baseline |
| ...  | +BM25 RRF      | 0.xx | ... |
```
