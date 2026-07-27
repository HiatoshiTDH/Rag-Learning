"""Weeks 2 + 4 — The heart of the plan: three-axis retrieval + importance scoring.

    score = ALPHA * recency + BETA * importance + GAMMA * relevance

Start at 1/1/1 like the Generative Agents paper, then tune for game feel.
Missing recency -> the NPC brings up something from 50 hours ago while
forgetting what just happened.
"""

from datetime import datetime, timezone

from src import config
from src.llm import LLM
from src.memory_store import MemoryRecord, MemoryStore

ALPHA = 1.0   # recency
BETA = 1.0    # importance
GAMMA = 1.0   # relevance
DECAY = 0.995  # recency = DECAY ^ (hours since last_accessed)

# Gameplay events with a clear category get hard-coded values — no LLM call (README 4.2)
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

# Events not in the table with no LLM available to score -> low-average default
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
    """Three-axis score for one record. importance 1-10 normalized to [0,1];
    relevance is the cosine from vector search, clamped to [0,1]."""
    rel = min(1.0, max(0.0, relevance))
    return (ALPHA * recency(record, now)
            + BETA * record.importance / 10
            + GAMMA * rel)


def retrieve(candidates: list[MemoryRecord], relevance: dict[str, float],
             now: datetime | None = None, top_k: int = 12,
             store: MemoryStore | None = None) -> list[MemoryRecord]:
    """Score the top-50 vector-search candidates on three axes, return the top 8-15.

    Pass `store` to automatically touch() the selected records (a recalled
    memory becomes fresh again). Reflection calls this with store=None so its
    internal reads don't distort recency.
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
    """Score importance for a batch of events.

    - events whose "kind" is in FIXED_IMPORTANCE -> table value, no LLM call.
    - the rest are scored in ONE batched call to Claude Haiku + structured
      output (the cost trick from README 4.2). No LLM -> DEFAULT_IMPORTANCE.

    events: [{"kind": str, "text": str}, ...] -> list[int] in the same order.
    """
    results: list[int | None] = []
    pending: list[int] = []  # indexes of events that need LLM scoring
    for i, event in enumerate(events):
        fixed = FIXED_IMPORTANCE.get(event.get("kind", ""))
        results.append(fixed)
        if fixed is None:
            pending.append(i)

    if pending and llm is not None:
        # Group 10-20 events per call to keep the prompt small
        for start in range(0, len(pending), 20):
            chunk = pending[start:start + 20]
            listing = "\n".join(
                f"{j + 1}. {events[idx]['text']}" for j, idx in enumerate(chunk))
            prompt = (
                f"You are an NPC with the following personality and goals:\n{npc_persona}\n\n"
                f"On a 1-10 scale, how important is each of the following events to you?\n"
                f"(1 = everyday trivia, 10 = life-changing)\n\n{listing}\n\n"
                f"Return a scores array of exactly {len(chunk)} integers, in the same order."
            )
            scores = llm.complete_json(prompt, model=model, schema=_SCORES_SCHEMA)["scores"]
            for j, idx in enumerate(chunk):
                raw = scores[j] if j < len(scores) else DEFAULT_IMPORTANCE
                results[idx] = min(10, max(1, int(raw)))

    return [r if r is not None else DEFAULT_IMPORTANCE for r in results]
