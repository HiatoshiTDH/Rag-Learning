"""P1 (task 1.4 + 1.5) — Qdrant (vector) + SQLite (metadata & full section).

Qdrant: chunk nhỏ + payload để filter (paper_id, section_type, year).
SQLite: full text từng section -> parent-document retrieval ở P3.
"""

import json
import sqlite3
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from src import config
from src.embedding import Embedder, get_embedder
from src.ingest import Chunk, Paper


# ------------------------------------------------------------------- kết nối

def get_qdrant() -> QdrantClient:
    """QDRANT_URL (docker server) nếu có, không thì embedded mode tại data/qdrant."""
    if config.QDRANT_URL:
        return QdrantClient(url=config.QDRANT_URL)
    Path(config.QDRANT_PATH).parent.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=config.QDRANT_PATH)


def ensure_collection(client: QdrantClient, dim: int) -> None:
    """Tạo collection nếu chưa có. Đổi embedder (đổi dim) -> xóa collection index lại."""
    if not client.collection_exists(config.COLLECTION):
        client.create_collection(
            config.COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )


def _connect_db(db_path: Path | None = None) -> sqlite3.Connection:
    db_path = db_path or config.SQLITE_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS papers (
            paper_id TEXT PRIMARY KEY, title TEXT, authors_json TEXT, year INTEGER, abstract TEXT
        );
        CREATE TABLE IF NOT EXISTS sections (
            parent_section_id TEXT PRIMARY KEY, paper_id TEXT, paper_title TEXT,
            section TEXT, section_type TEXT, text TEXT
        );
    """)
    return conn


# --------------------------------------------------------------------- ghi

def save_metadata(paper: Paper, chunks: list[Chunk], db_path: Path | None = None) -> None:
    """Task 1.5 — paper + full text từng section vào SQLite (INSERT OR REPLACE = idempotent).

    Full text section được ghép lại từ chunks (đã qua lọc References) để
    parent-document retrieval trả về đúng những gì đã được index.
    """
    conn = _connect_db(db_path)
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO papers VALUES (?,?,?,?,?)",
            (paper.paper_id, paper.title, json.dumps(paper.authors, ensure_ascii=False),
             paper.year, paper.abstract),
        )
        by_parent: dict[str, list[Chunk]] = {}
        for c in chunks:
            by_parent.setdefault(c.parent_section_id, []).append(c)
        for parent_id, group in by_parent.items():
            conn.execute(
                "INSERT OR REPLACE INTO sections VALUES (?,?,?,?,?,?)",
                (parent_id, paper.paper_id, paper.title,
                 group[0].section, group[0].section_type,
                 "\n\n".join(c.text for c in group)),
            )
    conn.close()


def upsert_chunks(chunks: list[Chunk], embedder: Embedder | None = None,
                  client: QdrantClient | None = None) -> int:
    """Task 1.4 — embed + upsert Qdrant. Point id = uuid5(chunk_id) -> chạy lại không duplicate."""
    if not chunks:
        return 0
    embedder = embedder or get_embedder()
    client = client or get_qdrant()
    ensure_collection(client, embedder.dim)

    vectors = embedder.embed_docs([c.text for c in chunks])
    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, c.chunk_id)),
            vector=vec,
            payload={
                "chunk_id": c.chunk_id, "paper_id": c.paper_id, "title": c.title,
                "year": c.year, "section": c.section, "section_type": c.section_type,
                "text": c.text, "parent_section_id": c.parent_section_id,
            },
        )
        for c, vec in zip(chunks, vectors)
    ]
    client.upsert(config.COLLECTION, points)
    return len(points)


# --------------------------------------------------------------------- đọc

def search(query: str, top_k: int = 20, filters: dict | None = None,
           embedder: Embedder | None = None, client: QdrantClient | None = None) -> list[dict]:
    """Vector search có filter payload (paper_id / section_type / year).

    Đây là bản v1 cho task 2.1 — hybrid (BM25 + RRF) sẽ bọc quanh hàm này ở P3.
    """
    embedder = embedder or get_embedder()
    client = client or get_qdrant()
    qfilter = None
    if filters:
        qfilter = Filter(must=[
            FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()
        ])
    hits = client.query_points(
        config.COLLECTION,
        query=embedder.embed_query(query),
        limit=top_k,
        query_filter=qfilter,
        with_payload=True,
    ).points
    return [{**h.payload, "score": h.score} for h in hits]


def get_section(parent_section_id: str, db_path: Path | None = None) -> dict | None:
    """Full text một section — dùng cho parent-document retrieval (P3)."""
    conn = _connect_db(db_path)
    row = conn.execute(
        "SELECT parent_section_id, paper_id, paper_title, section, section_type, text "
        "FROM sections WHERE parent_section_id = ?", (parent_section_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    keys = ["parent_section_id", "paper_id", "paper_title", "section", "section_type", "text"]
    return dict(zip(keys, row))
