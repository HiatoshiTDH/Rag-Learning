"""Tuần 5-6 — Reflection worker: nén ký ức vụn thành nhận định cấp cao.

Chạy nền, trigger khi tổng importance ký ức mới vượt ngưỡng (~150 theo
paper gốc) hoặc cuối mỗi "ngày" trong game. Dùng Claude Sonnet 5
(claude-sonnet-5) — không cần latency thấp vì không chặn hội thoại.

3 bước (README 4.4):
1. Lấy ~100 ký ức gần nhất -> hỏi Sonnet "3 câu hỏi cấp cao nhất?"
2. Với mỗi câu hỏi: retrieve ký ức liên quan -> sinh nhận định.
3. Ghi record type=reflection, importance cao, BẮT BUỘC kèm source_ids.

Chống bịa (bẫy số 4, README mục 8): LLM trả về CHỈ SỐ của ký ức nguồn trong
danh sách đã đánh số — mình tự map sang id thật. Nhận định không chỉ ra được
nguồn nào -> bỏ, không ghi.
"""

from src import config, scoring
from src.llm import LLM
from src.memory_store import MemoryRecord, MemoryStore

REFLECTION_THRESHOLD = 150
MODEL = config.REFLECTION_MODEL

_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["questions"],
    "additionalProperties": False,
}

_INSIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "insight": {"type": "string"},
        "importance": {"type": "integer"},
        "source_indexes": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["insight", "importance", "source_indexes"],
    "additionalProperties": False,
}


def should_reflect(npc_id: str, store: MemoryStore,
                   threshold: int = REFLECTION_THRESHOLD) -> bool:
    """Tổng importance của ký ức mới kể từ lần reflect trước >= ngưỡng."""
    return store.importance_sum_since_last_reflection(npc_id) >= threshold


def _numbered(memories: list[MemoryRecord]) -> str:
    return "\n".join(f"{i + 1}. {m.text}" for i, m in enumerate(memories))


def reflect(npc_id: str, store: MemoryStore, llm: LLM,
            model: str = MODEL, max_questions: int = 3) -> list[MemoryRecord]:
    """Chạy 1 vòng reflection, trả về các record reflection đã ghi."""
    recent = store.recent(npc_id, limit=100)
    if not recent:
        return []

    questions = llm.complete_json(
        f"Đây là những ký ức gần nhất của một NPC trong game:\n\n{_numbered(recent)}\n\n"
        f"{max_questions} câu hỏi cấp cao nhất có thể trả lời từ những ký ức này là gì? "
        f"(kiểu: 'Người chơi X là người thế nào?', 'Điều gì đang thay đổi trong làng?')",
        model=model, schema=_QUESTIONS_SCHEMA,
    )["questions"][:max_questions]

    created: list[MemoryRecord] = []
    for question in questions:
        # retrieve theo 3 trục quanh câu hỏi; store=None để không touch —
        # đọc nội bộ của worker không phải là "ký ức được nhắc lại"
        cands, relevance = store.candidates(npc_id, question, top_k=50)
        related = scoring.retrieve(cands, relevance, top_k=15, store=None)
        if not related:
            continue

        result = llm.complete_json(
            f"Câu hỏi: {question}\n\n"
            f"Ký ức liên quan (đã đánh số):\n{_numbered(related)}\n\n"
            f"Rút ra MỘT nhận định cấp cao trả lời câu hỏi trên, kèm:\n"
            f"- importance 1-10 (nhận định về tính cách/quan hệ thường 7-9)\n"
            f"- source_indexes: số thứ tự của những ký ức làm căn cứ (bắt buộc, ít nhất 1)",
            model=model, schema=_INSIGHT_SCHEMA,
        )
        source_ids = [related[i - 1].id for i in result.get("source_indexes", [])
                      if 1 <= i <= len(related)]
        if not source_ids:
            continue  # nhận định không truy được nguồn -> không ghi (chống bịa)

        record = MemoryRecord.new(
            npc_id=npc_id, type="reflection",
            text=result["insight"],
            importance=min(10, max(1, int(result["importance"]))),
            source_ids=source_ids,
        )
        store.add(record)
        created.append(record)
    return created


def maybe_reflect(npc_id: str, store: MemoryStore, llm: LLM | None,
                  model: str = MODEL) -> list[MemoryRecord]:
    """Entry point cho worker/server: chỉ chạy khi đủ ký ức mới và có LLM."""
    if llm is None or not should_reflect(npc_id, store):
        return []
    return reflect(npc_id, store, llm, model=model)
