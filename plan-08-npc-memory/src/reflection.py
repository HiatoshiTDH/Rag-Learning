"""Weeks 5-6 — Reflection worker: compress fragmentary memories into insights.

Runs in the background, triggered when the total importance of new memories
crosses a threshold (~150 per the original paper) or at the end of each
in-game "day". Uses Claude Sonnet 5 (claude-sonnet-5) — low latency is not
needed since it never blocks dialogue.

3 steps (README 4.4):
1. Take the ~100 most recent memories -> ask Sonnet "the 3 highest-level questions?"
2. For each question: retrieve related memories -> generate an insight.
3. Write a type=reflection record with high importance, source_ids REQUIRED.

Anti-fabrication (trap #4, README section 8): the LLM returns the INDEXES of
its source memories in the numbered list — we map them to real ids ourselves.
An insight that cannot point to any source is dropped, not written.
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
    """Total importance of new memories since the last reflection >= threshold."""
    return store.importance_sum_since_last_reflection(npc_id) >= threshold


def _numbered(memories: list[MemoryRecord]) -> str:
    return "\n".join(f"{i + 1}. {m.text}" for i, m in enumerate(memories))


def reflect(npc_id: str, store: MemoryStore, llm: LLM,
            model: str = MODEL, max_questions: int = 3) -> list[MemoryRecord]:
    """Run one reflection pass, return the reflection records written."""
    recent = store.recent(npc_id, limit=100)
    if not recent:
        return []

    questions = llm.complete_json(
        f"These are the most recent memories of a game NPC:\n\n{_numbered(recent)}\n\n"
        f"What are the {max_questions} highest-level questions that can be answered "
        f"from these memories? (e.g., 'What kind of person is player X?', "
        f"'What is changing in the village?')",
        model=model, schema=_QUESTIONS_SCHEMA,
    )["questions"][:max_questions]

    created: list[MemoryRecord] = []
    for question in questions:
        # three-axis retrieval around the question; store=None so we don't
        # touch — a worker's internal read is not "a memory being recalled"
        cands, relevance = store.candidates(npc_id, question, top_k=50)
        related = scoring.retrieve(cands, relevance, top_k=15, store=None)
        if not related:
            continue

        result = llm.complete_json(
            f"Question: {question}\n\n"
            f"Related memories (numbered):\n{_numbered(related)}\n\n"
            f"Draw ONE high-level insight that answers the question above, with:\n"
            f"- importance 1-10 (insights about personality/relationships are usually 7-9)\n"
            f"- source_indexes: the numbers of the memories the insight is based on "
            f"(required, at least 1)",
            model=model, schema=_INSIGHT_SCHEMA,
        )
        source_ids = [related[i - 1].id for i in result.get("source_indexes", [])
                      if 1 <= i <= len(related)]
        if not source_ids:
            continue  # insight has no traceable source -> don't write it (anti-fabrication)

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
    """Entry point for the worker/server: only runs with enough new memories and an LLM."""
    if llm is None or not should_reflect(npc_id, store):
        return []
    return reflect(npc_id, store, llm, model=model)
