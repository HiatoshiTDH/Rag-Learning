# Plan 3 — Research paper reading & lookup assistant (detailed)

> 🗂 **Document set for this plan:**
> - README.md (this file) — architecture & design rationale
> - [PLAN.md](PLAN.md) — full execution plan: phases, tasks, DoD, hour estimates, risks, decision log
> - [SETUP.md](SETUP.md) — everything to prepare: software, API keys, costs, Phase 0 checklist
> - [TEST_AT_HOME.md](TEST_AT_HOME.md) — **end-to-end test to run on the home machine** (7 steps + troubleshooting)
> - [scripts/smoke_test.sh](scripts/smoke_test.sh) — automated version of that test
> - [docker-compose.yml](docker-compose.yml) + [.env.example](.env.example) — run GROBID/Qdrant right away

> RAG usage level: ★★★★☆ · Difficulty: Medium · Time: 3–4 weeks
> A good fit if you are on a research track (robotics, human augmentation, SRL…) and want a tool you actually use every day, not just an exercise.

## 1. Goals & user stories

The system indexes papers in your research direction and can answer these kinds of questions:

| # | User story | Technical requirement |
|---|-----------|------------------|
| U1 | "What method does paper X use to solve problem Y?" | Retrieval within 1 paper, in the right Method section |
| U2 | "Compare how papers A and B measure Z" | Retrieval across multiple papers + synthesis |
| U3 | "Which papers in my library use dataset D?" | Combined metadata + full-text search |
| U4 | "Summarize the main approaches to problem P across my paper library" | Map-reduce summarization over multiple papers |
| U5 | "Where does this answer come from?" | Citations pointing to the right paper, section/page |

**Golden rule:** an answer without citations is a useless answer for research. Every design decision revolves around preserving the provenance of information.

## 2. Overall architecture

```
┌────────────── INGEST ──────────────┐   ┌───────── QUERY ─────────┐
│ arXiv API / Semantic Scholar API   │   │ User question            │
│        ↓                           │   │        ↓                 │
│ PDF → GROBID → TEI XML             │   │ Query expansion          │
│        ↓                           │   │ (domain terminology)     │
│ Structure-aware chunking           │   │        ↓                 │
│ (by section, keep metadata)        │   │ Hybrid search            │
│        ↓                           │   │ (vector + BM25 + filter) │
│ Embedding → Qdrant                 │   │        ↓                 │
│ Metadata → SQLite                  │   │ Re-rank → Parent-doc     │
└────────────────────────────────────┘   │        ↓                 │
                                         │ Claude + citations       │
                                         └──────────────────────────┘
```

## 3. Ingest pipeline — where 60% of the effort goes

### 3.1 Data sources
- **arXiv API**: download PDFs + metadata (title, authors, abstract, categories) by keyword/category (e.g. `cs.RO`, `cs.AI`).
- **Semantic Scholar API**: adds citation count, references, paperId — used later for the "which paper cites which" feature.
- Local library: a folder of PDFs you already downloaded.

### 3.2 Parsing academic PDFs — do not use ordinary PDF-to-text
Paper PDFs are two-column, with formulas, tables, headers/footers — naive text extraction will interleave the two columns and break everything downstream. Use **GROBID** (run via Docker): it returns fully structured TEI XML — title, abstract, each named section, each paragraph, and an already-parsed reference list.

```
docker run -p 8070:8070 lfoppiano/grobid:0.8.0
```

### 3.3 Structure-aware chunking
This is the central technique of this plan. Rules:

- **The chunk unit = a paragraph within a section**; never cut across paragraphs. Only paragraphs that are too long (>800 tokens) get further split by sentence.
- Every chunk carries full metadata:

```json
{
  "chunk_id": "2309.12345#method#3",
  "paper_id": "arXiv:2309.12345",
  "title": "...",
  "authors": ["..."],
  "year": 2023,
  "section": "3. Method",
  "section_type": "method",
  "text": "...",
  "parent_section_text_ref": "2309.12345#method"
}
```

- **`section_type`** is normalized (abstract / intro / related_work / method / experiment / result / conclusion) — enabling filters like "search only in Method".
- **The abstract is always indexed as its own chunk** with priority weighting — it is the best summary of the paper.
- Math formulas: keep them as LaTeX in the chunk text (GROBID preserves this); do not try to "translate" them into prose.

### 3.4 Embedding & index
- Embedding: `voyage-3` (multilingual, understands academic text well) or `bge-m3` if you want to run locally for free.
- Vector DB: **Qdrant** — needs payload filtering (by `paper_id`, `section_type`, `year`), which Chroma handles less well.
- Metadata + full text of each section: SQLite — used for parent-document retrieval and BM25.

## 4. Query pipeline

### 4.1 Query expansion with domain terminology
Users phrase things differently from papers: you ask about an "EMG-controlled exoskeleton" but the paper says "sEMG-driven assistive device". Before searching, have Claude generate 2–3 alternative phrasings of the question (including an English translation when the question is asked in Vietnamese — papers are mostly in English), then search with all variants and merge the results.

### 4.2 Hybrid search + filter
- Vector search (top 20) + BM25 (top 20) → merged with Reciprocal Rank Fusion.
- Apply filters when the question is explicit: a specific paper name → filter `paper_id`; "method" → prefer `section_type: method`.

### 4.3 Re-ranking
Pass ~40 candidates through a reranker (`voyage-rerank-2` or local `bge-reranker-v2-m3`) → keep the top 6–8. This step gives the clearest quality improvement relative to the effort spent.

### 4.4 Parent-document retrieval
Small chunks make search precise, but the LLM needs broader context: after selecting the top chunks, **replace each chunk with the entire section containing it** (already stored in SQLite). Dedupe when multiple chunks share a section.

### 4.5 Generation with citations
Use Claude's citations API — pass each section as a `document` block with `citations: {enabled: true}` and a `title` of "Paper title — Section title". The response returns text segments with a `citations` array pointing to exactly which document and where → renderable as footnotes/links. No need to prompt "please cite" and parse by hand — the API does it in a structured way.

For questions comparing multiple papers (U2, U4): run **map-reduce** — retrieve per paper, summarize each paper's perspective (map), then one final call to synthesize the comparison (reduce).

## 5. Milestones

| Week | Work | Definition of done |
|------|------|--------------------|
| 1 | GROBID pipeline + chunking + index 10 papers | Chunks visible in Qdrant with correct sections |
| 2 | Basic query pipeline (vector search → Claude + citations) | U1 works, answers carry correct citations |
| 2–3 | Hybrid + re-rank + parent-document | Measurable improvement on a self-made 20-question set |
| 3 | Query expansion + multi-paper (map-reduce) | U2, U4 work |
| 4 | Simple CLI/UI + automatic keyword-based arXiv ingest | Usable daily |

## 6. Known pitfalls

- **Do not chunk by fixed character count** — losing section boundaries means losing the ability to cite the right place.
- **The References section**: do not index it as ordinary text (it will pollute retrieval terribly because it contains every keyword). Keep it separate; use it only for the citation graph.
- **Numeric tables**: GROBID parses tables rather poorly. Accept skipping them in v1; upgrade later with a vision model (interfaces with Plan 11).
- **Asking in Vietnamese about English papers**: a query translation/expansion step is mandatory, otherwise recall is very low even with a "multilingual" embedding.
- **Evaluating by gut feeling**: build a golden set of ~30 questions with known answers + correct sources starting in week 2. Every time you change chunking/embedding, rerun it and compare numbers (connects to Plan 12).

## 7. Extension directions

- **Citation graph** (Semantic Scholar references) → answer "which paper builds on which" → a natural stepping stone to Plan 9 (GraphRAG).
- **New-paper radar**: a weekly cron that scans arXiv by keyword, auto-ingests, and summarizes what is new relative to the existing library.
- **Related-work writing support**: retrieve papers related to a topic + generate a cited draft — directly useful for a 研究計画書/proposal.
