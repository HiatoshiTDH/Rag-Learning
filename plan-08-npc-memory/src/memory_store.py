"""Week 1 — Memory stream: schema + record read/write (no game needed yet).

The stream is append-only; `last_accessed` is updated every time a record is
retrieved — a memory that gets recalled becomes "fresh" again.

Storage: SQLite is the source of truth for records (easy last_accessed
updates, easy reflection queries), Qdrant holds vectors for the top-50
relevance search. Same pattern as Plan 3 (index.py).
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from qdrant_client import QdrantClient
from qdrant_client.models import (Distance, FieldCondition, Filter,
                                  MatchValue, PointStruct, VectorParams)

from src import config
from src.embedding import Embedder, get_embedder

MemoryType = Literal["observation", "dialogue", "reflection", "plan"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MemoryRecord:
    id: str
    npc_id: str
    type: MemoryType
    text: str
    created_at: datetime
    last_accessed: datetime
    importance: int              # 1-10
    participants: list[str] = field(default_factory=list)   # ["player:akira"]
    source_ids: list[str] = field(default_factory=list)     # reflections point to their sources
    embedding: list[float] | None = None

    @classmethod
    def new(cls, npc_id: str, type: MemoryType, text: str, importance: int,
            participants: list[str] | None = None,
            source_ids: list[str] | None = None,
            created_at: datetime | None = None) -> "MemoryRecord":
        """Helper for server/tests: auto-generates id + timestamps."""
        ts = created_at or _now()
        return cls(
            id=f"mem_{uuid.uuid4().hex}",
            npc_id=npc_id, type=type, text=text,
            created_at=ts, last_accessed=ts,
            importance=importance,
            participants=participants or [],
            source_ids=source_ids or [],
        )


def _point_id(memory_id: str) -> str:
    """Qdrant only accepts uuid/int point ids — derive one stably from the memory id."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, memory_id))


def get_qdrant() -> QdrantClient:
    """QDRANT_URL (docker server) when set, otherwise embedded mode at data/qdrant."""
    if config.QDRANT_URL:
        return QdrantClient(url=config.QDRANT_URL)
    Path(config.QDRANT_PATH).mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=config.QDRANT_PATH)


class MemoryStore:
    """Records (SQLite) + vector index (Qdrant).

    Tests inject QdrantClient(":memory:") + a temp db_path + HashEmbedder.
    """

    def __init__(self, db_path: Path | None = None,
                 client: QdrantClient | None = None,
                 embedder: Embedder | None = None):
        self.embedder = embedder or get_embedder()
        self.client = client or get_qdrant()
        self.db_path = Path(db_path or config.SQLITE_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: FastAPI may call from multiple threads
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY, npc_id TEXT NOT NULL, type TEXT NOT NULL,
                text TEXT NOT NULL, created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL, importance INTEGER NOT NULL,
                participants_json TEXT NOT NULL, source_ids_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_memories_npc ON memories(npc_id, created_at);
        """)
        if not self.client.collection_exists(config.COLLECTION):
            self.client.create_collection(
                config.COLLECTION,
                vectors_config=VectorParams(size=self.embedder.dim, distance=Distance.COSINE),
            )

    # --------------------------------------------------------------- write

    def add(self, record: MemoryRecord) -> MemoryRecord:
        """Embed the text, store record + vector. Idempotent by record.id.

        Filtering at the source is the game/server's job: only write on
        interactions or gameplay events — NEVER every frame (trap #1,
        README section 8).
        """
        if record.embedding is None:
            record.embedding = self.embedder.embed_docs([record.text])[0]
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO memories VALUES (?,?,?,?,?,?,?,?,?)",
                (record.id, record.npc_id, record.type, record.text,
                 record.created_at.isoformat(), record.last_accessed.isoformat(),
                 record.importance,
                 json.dumps(record.participants, ensure_ascii=False),
                 json.dumps(record.source_ids, ensure_ascii=False)),
            )
        self.client.upsert(
            config.COLLECTION,
            points=[PointStruct(
                id=_point_id(record.id),
                vector=record.embedding,
                payload={"memory_id": record.id, "npc_id": record.npc_id},
            )],
        )
        return record

    # ---------------------------------------------------------------- read

    def _row_to_record(self, row: tuple) -> MemoryRecord:
        return MemoryRecord(
            id=row[0], npc_id=row[1], type=row[2], text=row[3],
            created_at=datetime.fromisoformat(row[4]),
            last_accessed=datetime.fromisoformat(row[5]),
            importance=row[6],
            participants=json.loads(row[7]),
            source_ids=json.loads(row[8]),
        )

    def get(self, memory_id: str) -> MemoryRecord | None:
        row = self.conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return self._row_to_record(row) if row else None

    def candidates(self, npc_id: str, context_text: str,
                   top_k: int = 50) -> tuple[list[MemoryRecord], dict[str, float]]:
        """Vector search for the top-50 by relevance, SCOPED BY npc_id.

        This is only the coarse filter — the three-axis scoring lives in
        scoring.retrieve. Scoping by npc_id is mandatory: an NPC must never
        "remember" something it did not witness (the no-leak test).

        Returns (records, relevance) — relevance: memory_id -> cosine score,
        exactly the shape scoring.retrieve expects.
        """
        vector = self.embedder.embed_query(context_text)
        hits = self.client.query_points(
            config.COLLECTION,
            query=vector,
            limit=top_k,
            query_filter=Filter(must=[
                FieldCondition(key="npc_id", match=MatchValue(value=npc_id)),
            ]),
        ).points
        records, relevance = [], {}
        for hit in hits:
            record = self.get(hit.payload["memory_id"])
            if record is None:  # orphaned vector (record deleted) — skip
                continue
            records.append(record)
            relevance[record.id] = float(hit.score)
        return records, relevance

    def recent(self, npc_id: str, limit: int = 100) -> list[MemoryRecord]:
        """Newest memories first — the input to reflection."""
        rows = self.conn.execute(
            "SELECT * FROM memories WHERE npc_id = ? ORDER BY created_at DESC LIMIT ?",
            (npc_id, limit)).fetchall()
        return [self._row_to_record(r) for r in rows]

    def touch(self, ids: list[str], now: datetime | None = None) -> None:
        """Update last_accessed on records that were just retrieved — a recalled
        memory becomes 'fresh' again (recency is computed from last_accessed)."""
        ts = (now or _now()).isoformat()
        with self.conn:
            self.conn.executemany(
                "UPDATE memories SET last_accessed = ? WHERE id = ?",
                [(ts, i) for i in ids])

    # ---------------------------------------------------- for reflection

    def importance_sum_since_last_reflection(self, npc_id: str) -> int:
        """Total importance of new memories (excluding reflections) since the
        last reflection — the reflection worker's trigger (README 4.4)."""
        watermark = self.conn.execute(
            "SELECT MAX(created_at) FROM memories WHERE npc_id = ? AND type = 'reflection'",
            (npc_id,)).fetchone()[0]
        if watermark is None:
            row = self.conn.execute(
                "SELECT COALESCE(SUM(importance), 0) FROM memories "
                "WHERE npc_id = ? AND type != 'reflection'", (npc_id,)).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COALESCE(SUM(importance), 0) FROM memories "
                "WHERE npc_id = ? AND type != 'reflection' AND created_at > ?",
                (npc_id, watermark)).fetchone()
        return int(row[0])
