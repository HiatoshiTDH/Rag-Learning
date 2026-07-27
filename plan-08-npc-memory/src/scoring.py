"""Tuần 2 + 4 — Trái tim của plan: retrieval 3 trục + importance scoring.

    score = ALPHA * recency + BETA * importance + GAMMA * relevance

Bắt đầu với 1/1/1 như paper Generative Agents, rồi tune theo game feel.
Thiếu recency -> NPC nhắc chuyện 50 giờ trước mà quên chuyện vừa xảy ra.
"""

from datetime import datetime, timezone

from src.memory_store import MemoryRecord

ALPHA = 1.0   # recency
BETA = 1.0    # importance
GAMMA = 1.0   # relevance
DECAY = 0.995  # recency = DECAY ^ (số giờ từ last_accessed)

# Sự kiện gameplay có loại rõ ràng thì gán cứng, khỏi tốn LLM call
FIXED_IMPORTANCE = {
    "player_attack_npc": 9,
    "player_gift": 7,
    "player_greeting": 2,
}


def recency(record: MemoryRecord, now: datetime) -> float:
    hours = (now - record.last_accessed).total_seconds() / 3600
    return DECAY ** hours


def retrieve(candidates: list[MemoryRecord], relevance: dict[str, float],
             now: datetime | None = None, top_k: int = 12) -> list[MemoryRecord]:
    """TODO(tuần 2): chấm score 3 trục trên 50 ứng viên từ vector search,
    trả top 8-15. importance chuẩn hóa về [0,1]. Gọi store.touch() cho kết quả."""
    raise NotImplementedError


def score_importance_batch(events: list[dict], npc_persona: str) -> list[int]:
    """TODO(tuần 4): sự kiện có trong FIXED_IMPORTANCE thì gán bảng;
    còn lại gom 10-20 event chấm một lần bằng Claude Haiku 4.5
    (claude-haiku-4-5) + structured output trả về mảng số 1-10."""
    raise NotImplementedError
