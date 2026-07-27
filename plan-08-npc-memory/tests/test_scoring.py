"""Unit test cho retrieval 3 trục + importance scoring (tuần 2 + 4)."""

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
    # recency 1 + importance 1 + relevance kẹp về 1 -> 3.0 với trọng số 1/1/1
    assert scoring.score(r, relevance=1.7, now=now) == pytest.approx(3.0)
    assert scoring.score(r, relevance=-0.3, now=now) == pytest.approx(2.0)


# --------------------------------------------------------------- importance

def test_fixed_importance_no_llm_call():
    events = [{"kind": "player_attack_npc", "text": "bị tấn công"},
              {"kind": "player_gift", "text": "được tặng hoa"},
              {"kind": "player_greeting", "text": "chào hỏi"}]
    assert scoring.score_importance_batch(events, "persona", llm=None) == [9, 7, 2]


def test_unknown_kind_without_llm_gets_default():
    events = [{"kind": "something_odd", "text": "một sự kiện lạ"}]
    assert scoring.score_importance_batch(events, "persona", llm=None) == \
        [scoring.DEFAULT_IMPORTANCE]


def test_llm_batch_scores_unknown_kinds_and_clamps():
    events = [
        {"kind": "player_gift", "text": "được tặng hoa"},          # bảng cứng: 7
        {"kind": "", "text": "làng bên bị cướp tấn công ban đêm"},  # LLM chấm
        {"kind": "", "text": "một con mèo đi ngang"},               # LLM chấm
    ]
    llm = ScriptedLLM([{"scores": [9, 42]}])  # 42 phải bị kẹp về 10
    result = scoring.score_importance_batch(events, "persona", llm=llm)
    assert result == [7, 9, 10]
    # chỉ 1 call cho cả batch (mẹo giảm cost README 4.2), và không hỏi lại event đã có bảng
    assert len(llm.calls) == 1
    assert "cướp" in llm.calls[0]["prompt"]
    assert "tặng hoa" not in llm.calls[0]["prompt"]


# ----------------------------------------------------------------- retrieve

def test_retrieve_ranks_and_touches_only_top(store, now):
    a = seed(store, NPC, "sự kiện quan trọng về thanh kiếm", 9, hours_ago=48, now=now)
    b = seed(store, NPC, "sự kiện thường về thanh kiếm", 5, hours_ago=1, now=now)
    c = seed(store, NPC, "chuyện vặt về thời tiết hôm nay", 1, hours_ago=200, now=now)

    cands, relevance = store.candidates(NPC, "thanh kiếm")
    top = scoring.retrieve(cands, relevance, now=now, top_k=2, store=store)

    assert [m.id for m in top] == [a.id, b.id] or [m.id for m in top] == [b.id, a.id]
    # 2 record được chọn thì last_accessed nhảy về now; record bị loại giữ nguyên
    assert store.get(a.id).last_accessed == now
    assert store.get(b.id).last_accessed == now
    assert store.get(c.id).last_accessed < now
