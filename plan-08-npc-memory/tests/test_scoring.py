"""Unit tests for three-axis retrieval + importance scoring (weeks 2 + 4)."""

from datetime import timedelta

import pytest

from src import scoring
from src.llm import ScriptedLLM
from src.memory_store import MemoryRecord
from tests.conftest import seed

NPC = "blacksmith_tom"


def _record(now, hours_ago=0.0, importance=5) -> MemoryRecord:
    return MemoryRecord.new(NPC, "observation", "text", importance,
                            created_at=now - timedelta(hours=hours_ago))


# ------------------------------------------------------------------ recency

def test_recency_decay(now):
    fresh = _record(now, hours_ago=0)
    old = _record(now, hours_ago=100)
    assert scoring.recency(fresh, now) == pytest.approx(1.0)
    assert scoring.recency(old, now) == pytest.approx(0.995 ** 100)


def test_score_three_axes(now):
    r = _record(now, hours_ago=0, importance=10)
    # recency 1 + importance 1 + relevance clamped to 1 -> 3.0 with 1/1/1 weights
    assert scoring.score(r, relevance=1.7, now=now) == pytest.approx(3.0)
    assert scoring.score(r, relevance=-0.3, now=now) == pytest.approx(2.0)


# --------------------------------------------------------------- importance

def test_fixed_importance_no_llm_call():
    events = [{"kind": "player_attack_npc", "text": "was attacked"},
              {"kind": "player_gift", "text": "received flowers"},
              {"kind": "player_greeting", "text": "a greeting"}]
    assert scoring.score_importance_batch(events, "persona", llm=None) == [9, 7, 2]


def test_unknown_kind_without_llm_gets_default():
    events = [{"kind": "something_odd", "text": "a strange event"}]
    assert scoring.score_importance_batch(events, "persona", llm=None) == \
        [scoring.DEFAULT_IMPORTANCE]


def test_llm_batch_scores_unknown_kinds_and_clamps():
    events = [
        {"kind": "player_gift", "text": "received flowers"},                 # fixed table: 7
        {"kind": "", "text": "raiders attacked the neighboring village at night"},  # LLM scores
        {"kind": "", "text": "a cat walked past"},                           # LLM scores
    ]
    llm = ScriptedLLM([{"scores": [9, 42]}])  # 42 must be clamped to 10
    result = scoring.score_importance_batch(events, "persona", llm=llm)
    assert result == [7, 9, 10]
    # one call for the whole batch (cost trick, README 4.2), and no re-asking
    # about events already covered by the table
    assert len(llm.calls) == 1
    assert "raiders" in llm.calls[0]["prompt"]
    assert "received flowers" not in llm.calls[0]["prompt"]


# ----------------------------------------------------------------- retrieve

def test_retrieve_ranks_and_touches_only_top(store, now):
    a = seed(store, NPC, "an important event involving the sword", 9, hours_ago=48, now=now)
    b = seed(store, NPC, "an ordinary event involving the sword", 5, hours_ago=1, now=now)
    c = seed(store, NPC, "trivia about today's weather", 1, hours_ago=200, now=now)

    cands, relevance = store.candidates(NPC, "the sword")
    top = scoring.retrieve(cands, relevance, now=now, top_k=2, store=store)

    assert [m.id for m in top] == [a.id, b.id] or [m.id for m in top] == [b.id, a.id]
    # the 2 selected records get last_accessed bumped to now; the rejected one keeps its old value
    assert store.get(a.id).last_accessed == now
    assert store.get(b.id).last_accessed == now
    assert store.get(c.id).last_accessed < now
