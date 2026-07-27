"""P2-P4 — Query pipeline: expansion -> hybrid (vector + BM25, RRF) -> re-rank -> parent-doc.

Main entry point: retrieve(question, ...) — answer.py / CLI / eval all go through it.
Every dependency (embedder, qdrant client, db_path, llm) is injectable for offline tests.
"""

import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from src import config
from src.index import get_section, load_chunks, search as vector_search
from src.rerank import get_reranker

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


# ------------------------------------------------------------------ BM25 (3.1)

# Cache the corpus by (db_path, mtime) — re-indexing refreshes it automatically
_bm25_cache: dict = {}


def _get_bm25(db_path: Path | None, filters: dict | None):
    path = db_path or config.SQLITE_PATH
    mtime = path.stat().st_mtime if path.exists() else 0
    key = (str(path), mtime, tuple(sorted((filters or {}).items())))
    if key not in _bm25_cache:
        chunks = load_chunks(db_path=db_path, filters=filters)
        bm25 = BM25Okapi([_tokenize(c["text"]) for c in chunks]) if chunks else None
        _bm25_cache.clear()  # keep exactly one corpus in RAM
        _bm25_cache[key] = (bm25, chunks)
    return _bm25_cache[key]


def bm25_search(query: str, top_k: int = 20, filters: dict | None = None,
                db_path: Path | None = None) -> list[dict]:
    """BM25 over the chunks table — catches terminology/proper nouns that vector search misses."""
    bm25, chunks = _get_bm25(db_path, filters)
    if bm25 is None:
        return []
    q_tokens = _tokenize(query)
    scores = bm25.get_scores(q_tokens)
    if not any(s > 0 for s in scores):
        # Corpus too small (1-2 docs after filtering) -> IDF=0, BM25 degenerates.
        # Fallback: shared-token count — still returns results with few papers ingested.
        q_set = set(q_tokens)
        scores = [float(len(q_set & set(_tokenize(c["text"])))) for c in chunks]
    ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
    return [{**c, "score": float(s)} for c, s in ranked[:top_k] if s > 0]


# ------------------------------------------------------------------- RRF (3.1)

def rrf_fuse(result_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion — merges multiple rankings, no score normalization needed."""
    fused: dict[str, dict] = {}
    scores: dict[str, float] = {}
    for results in result_lists:
        for rank, item in enumerate(results):
            cid = item["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            fused.setdefault(cid, item)
    ordered = sorted(fused, key=lambda cid: scores[cid], reverse=True)
    return [{**fused[cid], "score": scores[cid]} for cid in ordered]


# ------------------------------------------------------------ hybrid (3.1+3.2)

def hybrid_search(queries: list[str], filters: dict | None = None, top_k: int = 40,
                  embedder=None, client=None, db_path: Path | None = None) -> list[dict]:
    """For each question variant: vector top-20 + BM25 top-20, all merged with RRF."""
    result_lists = []
    for q in queries:
        result_lists.append(vector_search(q, top_k=20, filters=filters,
                                          embedder=embedder, client=client))
        result_lists.append(bm25_search(q, top_k=20, filters=filters, db_path=db_path))
    return rrf_fuse(result_lists)[:top_k]


# ------------------------------------------------------------- expansion (4.1)

_EXPAND_PROMPT = """A user's question about research papers:

{question}

Rewrite this question into {n} variants to improve the chance of finding the right passages:
- If the question is not in English, the FIRST variant must be an English translation
  (papers are mostly written in English).
- Remaining variants: use domain terminology/synonyms the paper's authors might have used.
Print one variant per line only — no numbering, no explanations."""


def expand_query(question: str, n: int = 3, llm=None) -> list[str]:
    """Returns [original question] + n variants. `llm` is a callable(prompt)->str, injectable in tests."""
    if llm is None:
        from src.llm import complete

        def llm(prompt: str) -> str:
            return complete(prompt, model=config.EXPAND_MODEL, max_tokens=300)

    raw = llm(_EXPAND_PROMPT.format(question=question, n=n))
    variants = [line.strip() for line in raw.splitlines() if line.strip()]
    return [question] + variants[:n]


# ------------------------------------------------------------ parent-doc (3.4)

def to_parent_sections(chunks: list[dict], db_path: Path | None = None) -> list[dict]:
    """Replace each chunk with its whole containing section, dedupe, keep ranking order."""
    seen: set[str] = set()
    sections: list[dict] = []
    for c in chunks:
        pid = c["parent_section_id"]
        if pid in seen:
            continue
        seen.add(pid)
        section = get_section(pid, db_path=db_path)
        if section:
            sections.append(section)
    return sections


# ------------------------------------------------------- combined entry point

def retrieve(question: str, filters: dict | None = None, top_k: int = 8,
             expand: bool = True, hybrid: bool = True, parent: bool = True,
             embedder=None, client=None, db_path: Path | None = None,
             reranker=None, llm=None) -> list[dict]:
    """The full pipeline. Returns sections (parent=True) or chunks (parent=False).

    The expand/hybrid/parent flags + injectable reranker let eval.py measure each layer separately.
    """
    queries = expand_query(question, llm=llm) if expand else [question]
    if hybrid:
        candidates = hybrid_search(queries, filters=filters, top_k=40,
                                   embedder=embedder, client=client, db_path=db_path)
    else:  # v1: pure vector — used as the baseline in eval
        candidates = rrf_fuse([
            vector_search(q, top_k=40, filters=filters, embedder=embedder, client=client)
            for q in queries
        ])[:40]
    reranker = reranker or get_reranker()
    top_chunks = reranker.rerank(question, candidates, top_k=top_k)
    if not parent:
        return top_chunks
    return to_parent_sections(top_chunks, db_path=db_path)
