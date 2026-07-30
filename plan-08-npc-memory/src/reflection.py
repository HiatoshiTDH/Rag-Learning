"""P2.2-2.3 — Reflection: nén ký ức vụn thành nhận định cấp cao, chạy nền.

Trigger khi tổng importance ký ức mới (từ lần reflect trước) vượt ngưỡng.
Nhận định BẮT BUỘC kèm source_ids — không có thì không debug được nhận định bịa.
"""

import re

from src import config
from src.memory_store import MemoryStore

_QUESTIONS_PROMPT = """Dưới đây là các ký ức gần đây của NPC "{npc_id}":

{memories}

Từ những ký ức này, 3 câu hỏi cấp cao nhất có thể trả lời được là gì?
(dạng "X là người thế nào?", "Quan hệ giữa X và Y ra sao?"...)
Chỉ in mỗi dòng một câu hỏi, không đánh số."""

_INSIGHT_PROMPT = """Ký ức liên quan của NPC (mỗi dòng có [id]):

{memories}

Câu hỏi: {question}

Rút ra MỘT nhận định cấp cao trả lời câu hỏi trên. In đúng định dạng:
NHẬN ĐỊNH: <một câu>
NGUỒN: <các id cách nhau bởi dấu phẩy>"""


def should_reflect(store: MemoryStore, npc_id: str) -> bool:
    since = store.last_reflection_at(npc_id)
    return store.importance_since(npc_id, since) >= config.REFLECTION_THRESHOLD


def reflect(store: MemoryStore, npc_id: str, llm=None, n_questions: int = 3) -> list:
    """3 bước (README mục 4.4). Trả về list record reflection đã ghi."""
    if llm is None:
        from src.llm import complete

        def llm(prompt: str) -> str:
            return complete(prompt, model=config.REFLECTION_MODEL, max_tokens=800)

    recent = store.recent(npc_id, limit=100, types=("observation", "dialogue"))
    if not recent:
        return []
    listing = "\n".join(f"[{r.id}] {r.text}" for r in recent)

    # Bước 1: câu hỏi cấp cao
    questions = [q.strip() for q in llm(
        _QUESTIONS_PROMPT.format(npc_id=npc_id, memories=listing)
    ).splitlines() if q.strip()][:n_questions]

    written = []
    for question in questions:
        # Bước 2: retrieve ký ức liên quan cho từng câu hỏi
        related = store.candidates(npc_id, question, top_k=20) or recent[:20]
        rel_listing = "\n".join(f"[{r.id}] {r.text}" for r in related)
        raw = llm(_INSIGHT_PROMPT.format(memories=rel_listing, question=question))

        insight = ""
        source_ids: list[str] = []
        for line in raw.splitlines():
            if line.upper().startswith("NHẬN ĐỊNH:"):
                insight = line.split(":", 1)[1].strip()
            elif line.upper().startswith("NGUỒN:"):
                source_ids = re.findall(r"mem_[0-9a-f]+", line)
        if not insight:
            continue
        valid_ids = {r.id for r in related}
        source_ids = [s for s in source_ids if s in valid_ids]
        if not source_ids:
            continue  # nhận định không truy được nguồn -> bỏ, không ghi bịa

        # Bước 3: ghi record reflection, importance cao
        written.append(store.add(
            npc_id=npc_id, type="reflection", text=insight,
            importance=8, source_ids=source_ids,
        ))
    return written
