# Plan 3 — What to prepare (SETUP)

Everything needed before starting P1 in [PLAN.md](PLAN.md). Finishing this section = Phase 0 done.

## 1. Software on your machine

| Item | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | use a venv |
| Docker + Docker Compose | latest | runs GROBID and Qdrant |
| Git | — | — |
| Free RAM | ~5 GB | GROBID eats ~4 GB while parsing |

## 2. Local services (docker compose)

A [`docker-compose.yml`](docker-compose.yml) is already in this folder:

```bash
docker compose up -d

# Sanity check
curl http://localhost:8070/api/isalive     # GROBID → true
# Qdrant dashboard: open http://localhost:6333/dashboard
```

| Service | Port | Role |
|---------|------|------|
| GROBID | 8070 | Parses academic PDFs → TEI XML |
| Qdrant | 6333 (HTTP) / 6334 (gRPC) | Vector DB, data stored in the `qdrant_storage` volume |

## 3. API keys

Copy [`.env.example`](.env.example) to `.env` and fill in:

| Key | Where to get it | Used for |
|-----|-----------------|----------|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys | Generation (answers + citations), query expansion |
| `VOYAGE_API_KEY` | dash.voyageai.com | Embedding (`voyage-3`) + re-rank (`voyage-rerank-2`) |

### Local-free option (no Voyage needed)

If you want to avoid embedding costs or keep data on your machine:

- Embedding: `bge-m3` via `sentence-transformers` (strong for Vietnamese/Japanese/English multilingual)
- Re-rank: `bge-reranker-v2-m3`
- Extra install: `pip install sentence-transformers` (+ GPU is faster; CPU still works for 10–100 papers)
- Trade-off: slower on large indexes; quality is better/worse depending on domain — the golden set (P2) gives the objective answer

You still need `ANTHROPIC_API_KEY` for generation.

## 4. Seed data

- **10 papers you have read carefully**, in your research direction (robotics / human augmentation / SRL...).
  - Why carefully-read papers: the P2 golden set requires you to know which paper and which section holds the right answer.
- Put the arXiv ids in a text file (e.g. `data/seed_papers.txt`) — script 1.1 reads from it.

## 5. Estimated costs

> Reference prices at the time of writing — re-check each provider's pricing page before large runs.

| Item | Estimate | Notes |
|------|----------|-------|
| Embedding 100 papers (~1.5M tokens) | < $0.5 | voyage-3; one-time cost at indexing. Local-free option: $0 |
| Re-rank | negligible | billed per query-document token pair |
| 1 ordinary question (6–8 section context, ~15K tokens in) | ~$0.08–0.15 | claude-opus-5 ($5/M in, $25/M out) |
| 1 multi-paper comparison (map-reduce) | ~$0.3–0.5 | more calls |
| **A month of personal use (~10 questions/day)** | **~$25–45** | drops sharply with prompt caching + sonnet-5 for simple questions |

Cost-saving tips while developing: work on the 10-paper set, enable prompt caching early (task 5.3 can be pulled forward into P2 if you like), use `claude-sonnet-5` ($3/$15) or `claude-haiku-4-5` ($1/$5) while trying out the pipeline — only switch to opus when evaluating real quality.

## 6. Restart order (each work session)

```bash
cd plan-03-paper-assistant
docker compose up -d          # GROBID + Qdrant
source .venv/bin/activate
# work on the open task in PLAN.md
```

## 7. Phase 0 completion checklist

- [ ] `docker compose up -d` running, both sanity checks pass
- [ ] `.env` filled in, `python -c "import anthropic, voyageai"` runs without error
- [ ] Decided: Voyage or local-free (record in the PLAN.md decision log if changed)
- [ ] `data/seed_papers.txt` has 10 arXiv ids
- [ ] Read section 6 (known traps) in [README.md](README.md) once
