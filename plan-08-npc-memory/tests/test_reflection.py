"""Unit tests for the reflection worker (weeks 5-6): threshold trigger,
watermark reset, and the mandatory-source_ids rule."""

from src.llm import ScriptedLLM
from src.reflection import reflect, should_reflect
from tests.conftest import seed

NPC = "blacksmith_tom"


def test_should_reflect_threshold(store, now):
    for i in range(18):  # 18 * 8 = 144 < 150
        seed(store, NPC, f"notable event number {i}", importance=8, hours_ago=2, now=now)
    assert not should_reflect(NPC, store)

    seed(store, NPC, "one more notable event", importance=8, hours_ago=1, now=now)
    assert should_reflect(NPC, store)  # 152 >= 150


def test_reflect_resets_watermark(store, now):
    for i in range(20):
        seed(store, NPC, f"Akira helped me with something big, time {i}", importance=8,
             hours_ago=3, now=now)
    assert should_reflect(NPC, store)

    llm = ScriptedLLM([
        {"questions": ["What kind of person is Akira?"]},
        {"insight": "Akira is often helpful to me", "importance": 8, "source_indexes": [1, 2]},
    ])
    created = reflect(NPC, store, llm)
    assert len(created) == 1

    # the newest reflection is the watermark -> old memories aren't counted again
    assert not should_reflect(NPC, store)


def test_insight_without_sources_is_dropped(store, now):
    seed(store, NPC, "Akira stopped by the workshop to buy nails", importance=5,
         hours_ago=1, now=now)
    llm = ScriptedLLM([
        {"questions": ["What kind of person is Akira?"]},
        {"insight": "a fabricated insight with no sources", "importance": 9,
         "source_indexes": []},
    ])
    assert reflect(NPC, store, llm) == []  # untraceable -> not written


def test_reflect_on_empty_stream_is_noop(store):
    llm = ScriptedLLM([])  # the LLM must not be called at all
    assert reflect(NPC, store, llm) == []
    assert llm.calls == []
