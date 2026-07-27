"""Unit test cho reflection worker (tuần 5-6): trigger theo ngưỡng,
watermark reset, và luật bắt buộc source_ids."""

from src.llm import ScriptedLLM
from src.reflection import reflect, should_reflect
from tests.conftest import seed

NPC = "blacksmith_tom"


def test_should_reflect_threshold(store, now):
    for i in range(18):  # 18 * 8 = 144 < 150
        seed(store, NPC, f"sự kiện đáng kể thứ {i}", importance=8, hours_ago=2, now=now)
    assert not should_reflect(NPC, store)

    seed(store, NPC, "một sự kiện đáng kể nữa", importance=8, hours_ago=1, now=now)
    assert should_reflect(NPC, store)  # 152 >= 150


def test_reflect_resets_watermark(store, now):
    for i in range(20):
        seed(store, NPC, f"Akira giúp ta việc lớn lần thứ {i}", importance=8,
             hours_ago=3, now=now)
    assert should_reflect(NPC, store)

    llm = ScriptedLLM([
        {"questions": ["Akira là người thế nào?"]},
        {"insight": "Akira hay giúp đỡ ta", "importance": 8, "source_indexes": [1, 2]},
    ])
    created = reflect(NPC, store, llm)
    assert len(created) == 1

    # reflection mới nhất là watermark -> ký ức cũ không bị đếm lại
    assert not should_reflect(NPC, store)


def test_insight_without_sources_is_dropped(store, now):
    seed(store, NPC, "Akira ghé xưởng mua đinh", importance=5, hours_ago=1, now=now)
    llm = ScriptedLLM([
        {"questions": ["Akira là người thế nào?"]},
        {"insight": "nhận định bịa không có nguồn", "importance": 9, "source_indexes": []},
    ])
    assert reflect(NPC, store, llm) == []  # không truy được nguồn -> không ghi


def test_reflect_on_empty_stream_is_noop(store):
    llm = ScriptedLLM([])  # không được phép gọi LLM
    assert reflect(NPC, store, llm) == []
    assert llm.calls == []
