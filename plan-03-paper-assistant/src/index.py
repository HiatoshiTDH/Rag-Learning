"""Tuần 1 — Embedding + lưu vào Qdrant (vector) và SQLite (metadata/full section).

Embedding: voyage-3 (đa ngôn ngữ) hoặc bge-m3 nếu muốn chạy local.
"""

from src.ingest import Chunk

COLLECTION = "papers"
EMBED_MODEL = "voyage-3"


def embed(texts: list[str]) -> list[list[float]]:
    """TODO(tuần 1): gọi Voyage AI embeddings theo batch."""
    raise NotImplementedError


def upsert_chunks(chunks: list[Chunk]) -> None:
    """TODO(tuần 1): upsert vào Qdrant với payload = metadata của chunk
    (paper_id, section_type, year...) để filter được khi query.

    Đồng thời lưu full text từng section vào SQLite
    -> dùng cho parent-document retrieval (src/query.py).
    """
    raise NotImplementedError
