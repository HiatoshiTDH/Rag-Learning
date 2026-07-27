"""Tuần 2 + 4 — Trái tim của plan: retrieval 3 trục + importance scoring.

    score = ALPHA * recency + BETA * importance + GAMMA * relevance

Bắt đầu với 1/1/1 như paper Generative Agents, rồi tune theo game feel.
Thiếu recency -> NPC nhắc chuyện 50 giờ trước mà quên chuyện vừa xảy ra.
"""

from datetime import datetime, timezone

from src import config
from src.llm import LLM
from src.memory_store import MemoryRecord, MemoryStore

ALPHA = 1.0   # recency
BETA = 1.0    # importance
GAMMA = 1.0   # relevance
DECAY = 0.995  # recency = DECAY ^ (số giờ từ last_accessed)

# Sự kiện gameplay có loại rõ ràng thì gán cứng, khỏi tốn LLM call (README 4.2)
FIXED_IMPORTANCE = {
    "player_attack_npc": 9,
    "player_theft": 8,
    "player_gift": 7,
    "promise_made": 7,
    "promise_kept": 8,
    "promise_broken": 8,
    "trade": 4,
    "player_greeting": 2,
}

# Sự kiện không có trong bảng và không có LLM để chấm -> mặc định trung bình thấp
DEFAULT_IMPORTANCE = 3

_SCORES_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["scores"],
    "additionalProperties": False,
}


def recency(record: MemoryRecord, now: datetime) -> float:
    hours = (now - record.last_accessed).total_seconds() / 3600
    return DECAY ** max(0.0, hours)


def score(record: MemoryRecord, relevance: float, now: datetime) -> float:
    """Điểm 3 trục cho 1 record. importance chuẩn hóa 1-10 -> [0,1];
    relevance là cosine từ vector search, kẹp về [0,1]."""
    rel = min(1.0, max(0.0, relevance))
    return (ALPHA * recency(record, now)
            + BETA * record.importance / 10
            + GAMMA * rel)


def retrieve(candidates: list[MemoryRecord], relevance: dict[str, float],
             now: datetime | None = None, top_k: int = 12,
             store: MemoryStore | None = None) -> list[MemoryRecord]:
    """Chấm score 3 trục trên top-50 ứng viên từ vector search, trả top 8-15.

    Truyền `store` để tự động touch() các record được chọn (ký ức được nhắc
    lại thì tươi trở lại). Reflection gọi với store=None để không làm méo
    recency khi chỉ đọc nội bộ.
    """
    now = now or datetime.now(timezone.utc)
    ranked = sorted(candidates,
                    key=lambda r: score(r, relevance.get(r.id, 0.0), now),
                    reverse=True)
    top = ranked[:top_k]
    if store is not None and top:
        store.touch([r.id for r in top], now=now)
    return top


def score_importance_batch(events: list[dict], npc_persona: str,
                           llm: LLM | None = None,
                           model: str = config.SCORING_MODEL) -> list[int]:
    """Chấm importance cho 1 batch event.

    - event có "kind" trong FIXED_IMPORTANCE -> gán bảng, khỏi gọi LLM.
    - còn lại gom lại chấm MỘT lần bằng Claude Haiku + structured output
      (mẹo giảm cost, README 4.2). Không có LLM -> DEFAULT_IMPORTANCE.

    events: [{"kind": str, "text": str}, ...] -> list[int] cùng thứ tự.
    """
    results: list[int | None] = []
    pending: list[int] = []  # index của event cần LLM chấm
    for i, event in enumerate(events):
        fixed = FIXED_IMPORTANCE.get(event.get("kind", ""))
        results.append(fixed)
        if fixed is None:
            pending.append(i)

    if pending and llm is not None:
        # Gom 10-20 event/lần gọi để không phình prompt
        for start in range(0, len(pending), 20):
            chunk = pending[start:start + 20]
            listing = "\n".join(
                f"{j + 1}. {events[idx]['text']}" for j, idx in enumerate(chunk))
            prompt = (
                f"Bạn là NPC với tính cách và mục tiêu sau:\n{npc_persona}\n\n"
                f"Trên thang 1-10, mỗi sự kiện sau quan trọng thế nào với bạn?\n"
                f"(1 = vụn vặt hằng ngày, 10 = thay đổi cuộc đời)\n\n{listing}\n\n"
                f"Trả về mảng scores đúng {len(chunk)} số, theo đúng thứ tự."
            )
            scores = llm.complete_json(prompt, model=model, schema=_SCORES_SCHEMA)["scores"]
            for j, idx in enumerate(chunk):
                raw = scores[j] if j < len(scores) else DEFAULT_IMPORTANCE
                results[idx] = min(10, max(1, int(raw)))

    return [r if r is not None else DEFAULT_IMPORTANCE for r in results]
