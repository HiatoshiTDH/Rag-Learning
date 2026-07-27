# Rag-Learning — Plans that use RAG heavily

This document lists projects/plans where a **RAG (Retrieval-Augmented Generation) system is the heart of the product** — not a side feature. Each plan spells out: why RAG is used heavily, which RAG techniques you will learn, a suggested stack, and the difficulty. Sorted from easy to hard so it can double as a learning roadmap.

## Overview table

| # | Plan | RAG intensity | Difficulty | Key techniques |
|---|------|---------------|------------|----------------|
| 1 | Personal document Q&A chatbot (PDF/notes) | ★★★☆☆ | Easy | Chunking, embedding, vector search |
| 2 | Internal company wiki/docs assistant | ★★★★☆ | Easy–Medium | Hybrid search, metadata filtering |
| 3 | Research paper reading & lookup assistant | ★★★★☆ | Medium | Citations, academic-text chunking |
| 4 | Code assistant on your own codebase | ★★★★☆ | Medium | Code chunking (AST), re-ranking |
| 5 | Customer support bot with a knowledge base | ★★★★☆ | Medium | Query rewriting, feedback loop |
| 6 | Legal / regulation / contract assistant | ★★★★★ | Medium–Hard | Grounding, mandatory citations, anti-hallucination |
| 7 | Personal second brain (Obsidian/Notion) | ★★★★☆ | Medium | Incremental indexing, temporal retrieval |
| 8 | Game NPCs with long-term memory | ★★★★★ | Hard | Memory RAG, recency + importance retrieval |
| 9 | GraphRAG / multi-hop QA over a knowledge base | ★★★★★ | Hard | Knowledge graph, multi-hop reasoning |
| 10 | Agentic RAG — the agent decides when to retrieve | ★★★★★ | Hard | Tool use, self-RAG, query planning |
| 11 | Multimodal RAG (images + text + tables) | ★★★★★ | Hard | Multimodal embedding, table/figure retrieval |
| 12 | RAG Evaluation Harness (measuring RAG quality) | ★★★★★ | Hard | RAGAS, LLM-as-judge, benchmarks |

---

## Group 1 — Basics (learn the standard RAG pipeline)

### 1. Personal document Q&A chatbot (PDF/notes)

- **Description:** Upload PDFs/markdown, ask questions, and get answers with citations pointing to the exact passage in the document.
- **Why RAG is heavy:** All the value lives in retrieval — the LLM knows nothing about your documents; every answer must flow through the ingest → chunk → embed → search pipeline.
- **Techniques learned:** Chunking (fixed-size vs semantic), embedding, cosine similarity, "answer from the context" prompt templates.
- **Suggested stack:** Python + Chroma (embedded vector DB, no server needed) + Voyage AI embeddings or `bge-m3` (good for Vietnamese/Japanese/English multilingual) + Claude API.
- **Estimated time:** 1–2 weeks.

### 2. Internal company wiki/docs assistant

- **Description:** Index the team's entire Confluence/Notion/Google Docs and answer questions like "what's the process for requesting leave" or "where is service X configured".
- **Why RAG is heavy:** Large, constantly changing data from many sources — you must handle periodic syncs, per-user access control, and search good enough to never surface outdated documents.
- **Techniques learned:** **Hybrid search** (BM25 + vector), metadata filtering (by team, last-updated date, trust level), automated ingest pipeline.
- **Suggested stack:** Qdrant or pgvector + BM25 (via Elasticsearch or `rank_bm25`) + a cron sync job.
- **Estimated time:** 2–4 weeks.

---

## Group 2 — Intermediate (harder data, smarter retrieval)

### 3. Research paper reading & lookup assistant

> 📁 **Project folder (detailed plan + skeleton code):** [plan-03-paper-assistant/](plan-03-paper-assistant/)

- **Description:** Index papers from arXiv/Semantic Scholar in your research direction (e.g., robotics, human augmentation, SRL), ask questions across multiple papers, compare methods between papers, find related work.
- **Why RAG is heavy:** Papers have a peculiar structure (abstract, method, equations, references) — naive chunking destroys the context. Answers must cite the right paper and the right section, otherwise they are useless for research.
- **Techniques learned:** Structure-aware chunking, citation tracking, parent-document retrieval (retrieve small chunks but feed the whole section into context), query expansion with domain terminology.
- **Suggested stack:** GROBID (academic PDF parsing) + Qdrant + Claude's citations API (enable `citations: {enabled: true}` on document blocks).
- **Estimated time:** 3–4 weeks.

### 4. Code assistant on your own codebase

- **Description:** Q&A about your own codebase: "where is the input buffer handled", "how does the save-game flow work", "write tests for module X in the current style".
- **Why RAG is heavy:** Code cannot be chunked by characters — it must be chunked by structure (function, class) using an AST. Retrieval must combine semantic search + exact symbol match, and must return enough context (imports, related type definitions).
- **Techniques learned:** AST-based chunking (tree-sitter), hybrid retrieval for code, re-ranking, repo-map/context stuffing.
- **Suggested stack:** tree-sitter + code-specialized embeddings (Voyage `voyage-code-3`) + Qdrant.
- **Estimated time:** 3–5 weeks.

### 5. Customer support bot with a knowledge base

- **Description:** A bot that answers customers from FAQ + docs + ticket history; escalates to a human when not confident enough.
- **Why RAG is heavy:** Real user questions are "dirty" (abbreviations, typos, vague descriptions) — query rewriting is required before search. One wrong answer loses a customer, so you need confidence thresholds + fallbacks.
- **Techniques learned:** Query rewriting/decomposition, confidence scoring, feedback loop (poorly rated answers → improve the index), A/B testing retrieval.
- **Estimated time:** 3–5 weeks.

### 6. Legal / regulation / contract assistant

- **Description:** Q&A over statutes, internal regulations, or contracts — every answer **must** include the original clause.
- **Why RAG is heavy:** This is a domain where hallucination = disaster. The whole system is built around "only say what was retrieved": mandatory citations, refusing when no grounding is found, and handling clauses that cross-reference each other.
- **Techniques learned:** Grounded generation, citation enforcement, cross-reference resolution, "I don't know" behavior, faithfulness evaluation.
- **Estimated time:** 4–6 weeks.

### 7. Personal second brain (Obsidian/Notion)

- **Description:** Index all your personal notes and ask things like "what did I conclude about topic X last month", "summarize every note related to lab Y".
- **Why RAG is heavy:** Notes change daily → you need **incremental indexing** (only re-embed edited notes). Questions often have a temporal component → retrieval must combine semantic + temporal ("recently", "back in March").
- **Techniques learned:** Incremental/delta indexing, temporal-aware retrieval, backlink-aware context (pull linked notes into context too).
- **Suggested stack:** A file watcher (watchdog) + SQLite-vec or Chroma (runs locally; personal data never leaves your machine).
- **Estimated time:** 2–4 weeks.

---

## Group 3 — Advanced (RAG as a whole system, not just one pipeline)

### 8. Game NPCs with long-term memory (Memory RAG)

> 📁 **Project folder (detailed plan + skeleton code):** [plan-08-npc-memory/](plan-08-npc-memory/)

- **Description:** NPCs remember every interaction with the player across sessions — "last time you promised to bring me medicine", "you once betrayed this village". A great fit if you are building Unity/Roblox games.
- **Why RAG is heavy:** NPC memory *is* a complete RAG system: every event is stored as a memory record, and during dialogue you retrieve along **three axes at once: relevance (semantic) + recency + importance** — exactly the architecture of the Generative Agents paper (Stanford). Plus the reflection problem: periodically compressing fragmentary memories into high-level insights.
- **Techniques learned:** Memory stream, multi-criteria scoring function, periodic reflection/summarization, retrieval under game latency constraints.
- **Suggested stack:** A lightweight vector DB next to the game server + Claude Haiku 4.5 for low-latency dialogue, Claude Sonnet 5 for reflection.
- **Estimated time:** 4–8 weeks.

### 9. GraphRAG / multi-hop QA over a knowledge base

- **Description:** Answer questions that require **connecting multiple pieces of information**: "Which professor worked at lab X and now researches topic Y?" — no single chunk contains the full answer.
- **Why RAG is heavy:** Pure vector search fails on multi-hop questions. You must build a knowledge graph (entities + relations extracted from documents), let retrieval walk the graph's edges, and combine community summarization for overview questions ("what are the main themes of this whole corpus").
- **Techniques learned:** LLM-based entity/relation extraction, graph traversal retrieval, community detection + hierarchical summarization (Microsoft's GraphRAG architecture), query routing (which questions go to the graph vs the vector index).
- **Suggested stack:** Neo4j or NetworkX + a vector DB side by side.
- **Estimated time:** 6–10 weeks.

### 10. Agentic RAG — the agent decides when to retrieve

- **Description:** Instead of "search on every question", the agent judges for itself: does this question need retrieval? From which source (internal docs / web / database)? Are the results sufficient, or should it search again with a different query?
- **Why RAG is heavy:** Retrieval becomes **a tool inside the agent loop** — the agent can call search multiple times, rewrite its own queries, grade its own results (self-RAG), and synthesize across sources. This is the architecture of modern production RAG systems.
- **Techniques learned:** Tool use with the Claude API (tool runner), query planning & decomposition, self-reflection on retrieval results, multi-source routing, corrective RAG (CRAG).
- **Suggested stack:** Claude API tool use (model `claude-opus-5`, adaptive thinking) + 2–3 different retrieval tools (vector search, BM25, web search).
- **Estimated time:** 6–10 weeks.

### 11. Multimodal RAG (images + text + tables)

- **Description:** Q&A over technical documents containing figures, diagrams, and data tables — "which pins does the circuit diagram in chapter 3 connect", "what does the performance comparison table say".
- **Why RAG is heavy:** You must index and retrieve non-text content: images need multimodal embeddings or vision-model captioning before indexing, tables must keep their structure, and answers must feed the right image/table into the vision model's context.
- **Techniques learned:** Multimodal embedding (CLIP-family / voyage-multimodal), image captioning for indexing, table extraction & serialization, layout-aware parsing.
- **Estimated time:** 6–10 weeks.

### 12. RAG Evaluation Harness

- **Description:** Build an automated evaluation system for the RAG pipelines above: measure retrieval precision/recall, faithfulness, answer relevancy — run it like CI every time you change the chunking strategy or embedding model.
- **Why RAG is heavy:** What you can't measure you can't improve. This plan forces you to understand **every stage** of RAG because you must measure each one: is the chunking good, did retrieval hit, does the answer stick to the context.
- **Techniques learned:** RAGAS metrics, LLM-as-judge, building golden datasets, regression testing for RAG, layered error analysis (chunking → retrieval → generation).
- **Suggested stack:** RAGAS, or write your own judge with Claude + structured outputs (`output_config.format`) for schema-based grading.
- **Estimated time:** 3–5 weeks (reusable across every other project).

---

## Suggested roadmap

```
Plan 1 (PDF chatbot)          ← learn the standard pipeline
   ↓
Plan 2 or 7                   ← hybrid search + incremental indexing
   ↓
Plan 3 or 4                   ← hard chunking (papers / code) + re-ranking
   ↓
Plan 12 (evaluation)          ← learn to measure BEFORE building complex systems
   ↓
Plan 8 / 9 / 10               ← pick by interest: games / graphs / agents
```

Personal note: if your goal is game dev → prioritize **Plan 8 (NPC memory)**; if your goal is research/grad school → prioritize **Plan 3 (paper assistant)** then **Plan 9 (GraphRAG)**.

## Notes on the shared stack

- **Embeddings:** Anthropic has no embeddings API — use Voyage AI (Anthropic's partner; `voyage-3` is multilingual and `voyage-code-3` is for code) or open-source `bge-m3` (strong for Vietnamese/Japanese, runs locally).
- **Vector DB:** start with Chroma (embedded, zero-config) → move to Qdrant or pgvector when you need production features/complex filtering.
- **LLM:** default to `claude-opus-5` for quality; `claude-sonnet-5` for high volume; `claude-haiku-4-5` for low-latency tasks (e.g., in-game NPC dialogue). Enable prompt caching for context/documents repeated across requests to cut the cached portion's cost by ~90%.
- **Guiding principle:** do Plan 12 (evaluation) as early as possible — every chunking/embedding/re-ranking decision should be backed by numbers, not gut feeling.
