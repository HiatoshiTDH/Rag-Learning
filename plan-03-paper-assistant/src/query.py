"""P2-P4 — Query pipeline: expansion -> hybrid (vector + BM25, RRF) -> re-rank -> parent-doc.

Entry point chính: retrieve(question, ...) — answer.py / CLI / eval đều đi qua đây.
Mọi dependency (embedder, qdrant client, db_path, llm) đều inject được để test offline.
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

# Cache corpus theo (db_path, mtime) — index lại thì tự làm mới
_bm25_cache: dict = {}


def _get_bm25(db_path: Path | None, filters: dict | None):
    path = db_path or config.SQLITE_PATH
    mtime = path.stat().st_mtime if path.exists() else 0
    key = (str(path), mtime, tuple(sorted((filters or {}).items())))
    if key not in _bm25_cache:
        chunks = load_chunks(db_path=db_path, filters=filters)
        bm25 = BM25Okapi([_tokenize(c["text"]) for c in chunks]) if chunks else None
        _bm25_cache.clear()  # giữ đúng 1 corpus trong RAM
        _bm25_cache[key] = (bm25, chunks)
    return _bm25_cache[key]


def bm25_search(query: str, top_k: int = 20, filters: dict | None = None,
                db_path: Path | None = None) -> list[dict]:
    """BM25 trên bảng chunks — bắt thuật ngữ/tên riêng mà vector search hay trượt."""
    bm25, chunks = _get_bm25(db_path, filters)
    if bm25 is None:
        return []
    q_tokens = _tokenize(query)
    scores = bm25.get_scores(q_tokens)
    if not any(s > 0 for s in scores):
        # Corpus quá nhỏ (1-2 doc sau filter) -> IDF=0, BM25 suy biến.
        # Fallback: đếm từ trùng — vẫn trả kết quả khi mới ingest ít paper.
        q_set = set(q_tokens)
        scores = [float(len(q_set & set(_tokenize(c["text"])))) for c in chunks]
    ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
    return [{**c, "score": float(s)} for c, s in ranked[:top_k] if s > 0]


# ------------------------------------------------------------------- RRF (3.1)

def rrf_fuse(result_lists: list[list[dict]], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion — gộp nhiều bảng xếp hạng, không cần chuẩn hóa score."""
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
    """Với mỗi biến thể câu hỏi: vector top-20 + BM25 top-20, gộp tất cả bằng RRF."""
    result_lists = []
    for q in queries:
        result_lists.append(vector_search(q, top_k=20, filters=filters,
                                          embedder=embedder, client=client))
        result_lists.append(bm25_search(q, top_k=20, filters=filters, db_path=db_path))
    return rrf_fuse(result_lists)[:top_k]


# ------------------------------------------------------------- expansion (4.1)

_EXPAND_PROMPT = """Câu hỏi của người dùng về các paper nghiên cứu:

{question}

Viết lại câu hỏi này thành {n} biến thể để tăng khả năng tìm đúng đoạn văn trong paper:
- Nếu câu hỏi không phải tiếng Anh, biến thể ĐẦU TIÊN phải là bản dịch tiếng Anh
  (paper hầu hết viết bằng tiếng Anh).
- Các biến thể còn lại: dùng thuật ngữ chuyên ngành/từ đồng nghĩa mà tác giả paper
  có thể đã dùng.
Chỉ in ra mỗi dòng một biến thể, không đánh số, không giải thích."""


def expand_query(question: str, n: int = 3, llm=None) -> list[str]:
    """Trả về [câu gốc] + n biến thể. `llm` là callable(prompt)->str, inject được khi test."""
    if llm is None:
        from src.llm import complete

        def llm(prompt: str) -> str:
            return complete(prompt, model=config.EXPAND_MODEL, max_tokens=300)

    raw = llm(_EXPAND_PROMPT.format(question=question, n=n))
    variants = [line.strip() for line in raw.splitlines() if line.strip()]
    return [question] + variants[:n]


# ------------------------------------------------------------ parent-doc (3.4)

def to_parent_sections(chunks: list[dict], db_path: Path | None = None) -> list[dict]:
    """Thay chunk bằng toàn bộ section chứa nó, dedupe, giữ thứ tự xếp hạng."""
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


# ------------------------------------------------------- entry point tổng hợp

def retrieve(question: str, filters: dict | None = None, top_k: int = 8,
             expand: bool = True, hybrid: bool = True, parent: bool = True,
             embedder=None, client=None, db_path: Path | None = None,
             reranker=None, llm=None) -> list[dict]:
    """Pipeline đầy đủ. Trả về list section (parent=True) hoặc list chunk (parent=False).

    Các cờ expand/hybrid/parent + reranker inject được cho phép eval.py đo từng tầng riêng.
    """
    queries = expand_query(question, llm=llm) if expand else [question]
    if hybrid:
        candidates = hybrid_search(queries, filters=filters, top_k=40,
                                   embedder=embedder, client=client, db_path=db_path)
    else:  # v1: vector thuần — dùng làm baseline trong eval
        candidates = rrf_fuse([
            vector_search(q, top_k=40, filters=filters, embedder=embedder, client=client)
            for q in queries
        ])[:40]
    reranker = reranker or get_reranker()
    top_chunks = reranker.rerank(question, candidates, top_k=top_k)
    if not parent:
        return top_chunks
    return to_parent_sections(top_chunks, db_path=db_path)
