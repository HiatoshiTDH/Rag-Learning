"""Tuần 2-3 — Query pipeline: expansion -> hybrid search -> re-rank -> parent-doc.

Thứ tự triển khai (theo milestone trong README):
  tuần 2: vector search thuần cho chạy được đã
  tuần 2-3: thêm BM25 + RRF, re-rank, parent-document
  tuần 3: query expansion
"""


def expand_query(question: str) -> list[str]:
    """TODO(tuần 3): cho Claude sinh 2-3 cách diễn đạt khác (kèm bản tiếng Anh
    nếu câu hỏi là tiếng Việt — paper hầu hết tiếng Anh)."""
    raise NotImplementedError


def hybrid_search(queries: list[str], filters: dict | None = None, top_k: int = 40) -> list[dict]:
    """TODO(tuần 2-3): vector top-20 + BM25 top-20, gộp bằng Reciprocal Rank Fusion.

    filters: {"paper_id": ..., "section_type": ...} khi câu hỏi nêu rõ.
    """
    raise NotImplementedError


def rerank(question: str, candidates: list[dict], top_k: int = 8) -> list[dict]:
    """TODO(tuần 2-3): voyage-rerank-2 hoặc bge-reranker-v2-m3 local.

    Đây là bước cải thiện chất lượng rõ nhất so với công sức bỏ ra.
    """
    raise NotImplementedError


def to_parent_sections(chunks: list[dict]) -> list[dict]:
    """TODO(tuần 2-3): thay mỗi chunk bằng TOÀN BỘ section chứa nó (đọc từ SQLite),
    dedupe nếu nhiều chunk cùng section."""
    raise NotImplementedError
