"""Tuần 1 — Memory stream: schema + ghi/đọc record (chưa cần game).

Stream là append-only; `last_accessed` được cập nhật mỗi lần record
được retrieve — ký ức được nhắc lại thì "tươi" trở lại.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

MemoryType = Literal["observation", "dialogue", "reflection", "plan"]


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
    source_ids: list[str] = field(default_factory=list)     # reflection trỏ về ký ức gốc
    embedding: list[float] | None = None


class MemoryStore:
    """Lưu record + vector index. V1 dùng SQLite + Qdrant local là đủ."""

    def add(self, record: MemoryRecord) -> None:
        """TODO(tuần 1): embed text, lưu record + vector.

        Lọc tại nguồn: chỉ ghi khi có tương tác/sự kiện gameplay,
        KHÔNG ghi mọi frame — stream toàn rác là bẫy số 1 (README mục 8).
        """
        raise NotImplementedError

    def candidates(self, npc_id: str, context_text: str, top_k: int = 50) -> list[MemoryRecord]:
        """TODO(tuần 1): vector search top-50 theo relevance, scope theo npc_id.

        Đây mới là bước lọc thô — chấm điểm 3 trục nằm ở scoring.py.
        Scope theo npc_id là bắt buộc: NPC không được "nhớ" thứ nó chưa từng chứng kiến.
        """
        raise NotImplementedError

    def touch(self, ids: list[str]) -> None:
        """TODO(tuần 1): cập nhật last_accessed cho các record vừa được retrieve."""
        raise NotImplementedError
