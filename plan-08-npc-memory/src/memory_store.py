"""P1 — Memory stream: SQLite (record) + Qdrant (vector), scope chặt theo npc_id.

`last_accessed` cập nhật mỗi lần record được retrieve — ký ức được nhắc lại
thì "tươi" trở lại, đúng như trí nhớ người thật.
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from qdrant_client import QdrantClient
from qdrant_client.models import (Distance, FieldCondition, Filter, MatchValue,
                                  PointStruct, VectorParams)

from src import config
from src.embedding import Embedder, get_embedder

MemoryType = Literal["observation", "dialogue", "reflection", "plan"]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MemoryRecord:
    id: str
    npc_id: str
    type: MemoryType
    text: str
    created_at: datetime
    last_accessed: datetime
    importance: int                                          # 1-10
    participants: list[str] = field(default_factory=list)    # ["player:akira"]
    source_ids: list[str] = field(default_factory=list)      # reflection -> ký ức gốc
    relevance: float = 0.0                                   # điền lúc retrieve


class MemoryStore:
    """V1: SQLite + Qdrant (embedded mode nếu không có QDRANT_URL)."""

    def __init__(self, db_path: Path | None = None, client: QdrantClient | None = None,
                 embedder: Embedder | None = None):
        self.db_path = db_path or config.SQLITE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or get_embedder()
        if client is not None:
            self.client = client
        elif config.QDRANT_URL:
            self.client = QdrantClient(url=config.QDRANT_URL)
        else:
            Path(config.QDRANT_PATH).parent.mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=config.QDRANT_PATH)
        if not self.client.collection_exists(config.COLLECTION):
            self.client.create_collection(
                config.COLLECTION,
                vectors_config=VectorParams(size=self.embedder.dim, distance=Distance.COSINE),
            )
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, npc_id TEXT, type TEXT, text TEXT,
                    created_at TEXT, last_accessed TEXT, importance INTEGER,
                    participants_json TEXT, source_ids_json TEXT
                )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_npc ON memories(npc_id, created_at)")

    # ------------------------------------------------------------------- ghi

    def add(self, npc_id: str, type: MemoryType, text: str,
            importance: int, participants: list[str] | None = None,
            source_ids: list[str] | None = None,
            created_at: datetime | None = None) -> MemoryRecord:
        """Ghi một ký ức. Lọc TẠI NGUỒN trước khi gọi hàm này — không ghi mọi frame
        (bẫy số 1, README mục 8). `created_at` truyền được để test harness giả lập thời gian."""
        ts = created_at or now_utc()
        record = MemoryRecord(
            id=f"mem_{uuid.uuid4().hex[:20]}", npc_id=npc_id, type=type, text=text,
            created_at=ts, last_accessed=ts, importance=importance,
            participants=participants or [], source_ids=source_ids or [],
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?)",
                (record.id, npc_id, type, text, ts.isoformat(), ts.isoformat(),
                 importance, json.dumps(record.participants), json.dumps(record.source_ids)),
            )
        vec = self.embedder.embed_docs([text])[0]
        self.client.upsert(config.COLLECTION, [PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, record.id)), vector=vec,
            payload={"memory_id": record.id, "npc_id": npc_id},
        )])
        return record

    # ------------------------------------------------------------------- đọc

    def _rows_to_records(self, rows, relevance: dict[str, float] | None = None) -> list[MemoryRecord]:
        out = []
        for r in rows:
            out.append(MemoryRecord(
                id=r[0], npc_id=r[1], type=r[2], text=r[3],
                created_at=datetime.fromisoformat(r[4]),
                last_accessed=datetime.fromisoformat(r[5]),
                importance=r[6],
                participants=json.loads(r[7]), source_ids=json.loads(r[8]),
                relevance=(relevance or {}).get(r[0], 0.0),
            ))
        return out

    def candidates(self, npc_id: str, context_text: str,
                   top_k: int = config.CANDIDATE_POOL) -> list[MemoryRecord]:
        """Lọc thô bằng vector search, SCOPE THEO npc_id (NPC không được nhớ thứ
        nó chưa từng chứng kiến). Chấm 3 trục nằm ở scoring.py."""
        hits = self.client.query_points(
            config.COLLECTION,
            query=self.embedder.embed_query(context_text),
            limit=top_k,
            query_filter=Filter(must=[FieldCondition(key="npc_id", match=MatchValue(value=npc_id))]),
            with_payload=True,
        ).points
        if not hits:
            return []
        relevance = {h.payload["memory_id"]: float(h.score) for h in hits}
        ids = list(relevance)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM memories WHERE id IN ({','.join('?' * len(ids))})", ids
            ).fetchall()
        return self._rows_to_records(rows, relevance)

    def touch(self, ids: list[str], when: datetime | None = None) -> None:
        """Ký ức vừa được dùng -> last_accessed mới -> recency 'tươi' trở lại."""
        if not ids:
            return
        ts = (when or now_utc()).isoformat()
        with self._connect() as conn:
            conn.execute(
                f"UPDATE memories SET last_accessed = ? WHERE id IN ({','.join('?' * len(ids))})",
                [ts, *ids],
            )

    def recent(self, npc_id: str, limit: int = 100,
               types: tuple[str, ...] | None = None) -> list[MemoryRecord]:
        """Ký ức gần nhất (cho reflection)."""
        sql = "SELECT * FROM memories WHERE npc_id = ?"
        params: list = [npc_id]
        if types:
            sql += f" AND type IN ({','.join('?' * len(types))})"
            params.extend(types)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return self._rows_to_records(rows)

    def importance_since(self, npc_id: str, since: datetime | None) -> int:
        """Tổng importance của ký ức mới từ mốc `since` — trigger reflection."""
        sql = "SELECT COALESCE(SUM(importance), 0) FROM memories WHERE npc_id = ? AND type != 'reflection'"
        params: list = [npc_id]
        if since is not None:
            sql += " AND created_at > ?"
            params.append(since.isoformat())
        with self._connect() as conn:
            return int(conn.execute(sql, params).fetchone()[0])

    def last_reflection_at(self, npc_id: str) -> datetime | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(created_at) FROM memories WHERE npc_id = ? AND type = 'reflection'",
                (npc_id,),
            ).fetchone()
        return datetime.fromisoformat(row[0]) if row and row[0] else None
