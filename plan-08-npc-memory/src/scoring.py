"""P1.3 + P2.1 — Trái tim của plan: retrieval 3 trục + importance scoring.

    score = ALPHA * recency + BETA * importance + GAMMA * relevance

Thiếu recency -> NPC nhắc chuyện 50 giờ trước mà quên chuyện vừa xảy ra.
Thiếu importance -> chuyện vặt đè chuyện lớn. Trọng số tune qua .env.
"""

import json
import re
from datetime import datetime

from src import config
from src.memory_store import MemoryRecord, now_utc

# Sự kiện gameplay có loại rõ ràng thì gán cứng, khỏi tốn LLM call (P2.1)
FIXED_IMPORTANCE = {
    "player_attack_npc": 9,
    "player_steal": 8,
    "player_gift": 7,
    "player_promise": 7,
    "player_trade": 4,
    "player_greeting": 2,
}


def recency(record: MemoryRecord, now: datetime) -> float:
    hours = max(0.0, (now - record.last_accessed).total_seconds() / 3600)
    return config.RECENCY_DECAY ** hours


def score(record: MemoryRecord, now: datetime) -> float:
    return (config.ALPHA * recency(record, now)
            + config.BETA * (record.importance / 10.0)
            + config.GAMMA * record.relevance)


def retrieve(candidates: list[MemoryRecord], now: datetime | None = None,
             top_k: int = config.RETRIEVE_TOP_K) -> list[MemoryRecord]:
    """Chấm 3 trục trên pool ứng viên (đã có .relevance từ vector search),
    trả top-k. Caller nhớ gọi store.touch([r.id for r in kết_quả])."""
    now = now or now_utc()
    return sorted(candidates, key=lambda r: score(r, now), reverse=True)[:top_k]


# ------------------------------------------------- importance scoring (P2.1)

_IMPORTANCE_PROMPT = """Bạn chấm độ quan trọng của sự kiện với một NPC trong game.
NPC: {persona}

Với MỖI sự kiện dưới đây, chấm 1-10 (1 = vụn vặt thường nhật, 10 = thay đổi cuộc đời NPC).
Chỉ in ra một mảng JSON số nguyên, đúng thứ tự, không giải thích. Ví dụ: [3, 8, 1]

Sự kiện:
{events}"""


def score_importance_batch(events: list[dict], npc_persona: str, llm=None) -> list[int]:
    """events: [{"event_type": "...", "text": "..."}]. Loại có trong FIXED_IMPORTANCE
    -> gán bảng; còn lại gom chấm MỘT lần bằng LLM (batch, P2.1)."""
    scores: list[int | None] = [FIXED_IMPORTANCE.get(e.get("event_type", "")) for e in events]
    pending = [i for i, s in enumerate(scores) if s is None]
    if not pending:
        return scores  # type: ignore[return-value]

    if llm is None:
        from src.llm import complete

        def llm(prompt: str) -> str:
            return complete(prompt, model=config.IMPORTANCE_MODEL, max_tokens=200)

    listing = "\n".join(f"{n + 1}. {events[i]['text']}" for n, i in enumerate(pending))
    raw = llm(_IMPORTANCE_PROMPT.format(persona=npc_persona, events=listing))
    # Parse bền: lấy mảng JSON đầu tiên; hỏng thì fallback mọi số trong text; vẫn hỏng -> 5
    parsed: list[int] = []
    m = re.search(r"\[[\d,\s]*\]", raw)
    if m:
        try:
            parsed = [int(x) for x in json.loads(m.group())]
        except (json.JSONDecodeError, ValueError):
            parsed = []
    if len(parsed) != len(pending):
        nums = [int(x) for x in re.findall(r"\b(?:10|[1-9])\b", raw)]
        parsed = nums[:len(pending)]
    for n, i in enumerate(pending):
        val = parsed[n] if n < len(parsed) else 5
        scores[i] = max(1, min(10, val))
    return scores  # type: ignore[return-value]
