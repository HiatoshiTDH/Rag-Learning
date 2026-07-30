"""Test harness trí nhớ — chạy offline hoàn toàn (HashEmbedder + Qdrant in-memory + fake LLM).

Đây là các kịch bản B1-B5 trong README mục 1, viết thành test theo PLAN P4.
Chạy lại mỗi lần đổi ALPHA/BETA/GAMMA hay ngưỡng reflection.
"""

from datetime import timedelta

import pytest
from qdrant_client import QdrantClient

from src import config
from src.embedding import HashEmbedder
from src.memory_store import MemoryRecord, MemoryStore, now_utc
from src.reflection import reflect, should_reflect
from src.scoring import recency, retrieve, score_importance_batch


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=tmp_path / "mem.sqlite",
                       client=QdrantClient(":memory:"), embedder=HashEmbedder())


# ------------------------------------------------------------------ store cơ bản

def test_add_and_candidates(store):
    store.add("tom", "observation", "player akira promised to bring healing medicine", 7)
    hits = store.candidates("tom", "medicine promise")
    assert len(hits) == 1 and hits[0].relevance > 0


def test_no_leak_across_npcs(store):
    """Ký ức scope theo npc_id — NPC khác không thấy chuyện nó không chứng kiến."""
    store.add("tom", "observation", "akira stole bread from my shop", 8)
    assert store.candidates("mira", "akira stole bread") == []


def test_touch_refreshes_recency(store):
    old = now_utc() - timedelta(hours=100)
    r = store.add("tom", "observation", "some old event happened", 5, created_at=old)
    assert recency(r, now_utc()) < 0.7          # 0.995^100 ≈ 0.61
    store.touch([r.id])
    refreshed = store.recent("tom")[0]
    assert recency(refreshed, now_utc()) > 0.99  # được nhắc lại -> tươi trở lại


# ------------------------------------------------------------- retrieval 3 trục

def test_remembers_promise_after_noise(store):
    """B1: lời hứa 3 ngày trước phải thắng 30 sự kiện nhiễu mới hơn."""
    promise = store.add(
        "tom", "dialogue", "akira promised to bring rare healing medicine for my illness",
        7, created_at=now_utc() - timedelta(days=3),
    )
    for i in range(30):
        store.add("tom", "observation", f"village weather cloudy morning number {i}", 2)

    results = retrieve(store.candidates("tom", "did akira keep the medicine promise"))
    assert results and results[0].id == promise.id


def test_important_beats_recent_trivia():
    """B2/B5: quan trọng + cũ thắng vặt vãnh + mới (cùng độ liên quan)."""
    now = now_utc()
    theft = MemoryRecord(id="m1", npc_id="tom", type="observation",
                         text="akira stole my best sword", importance=9,
                         created_at=now - timedelta(days=3),
                         last_accessed=now - timedelta(days=3), relevance=0.5)
    trivia = MemoryRecord(id="m2", npc_id="tom", type="observation",
                          text="a bird flew past the window", importance=1,
                          created_at=now, last_accessed=now, relevance=0.5)
    assert retrieve([trivia, theft], now=now)[0].id == "m1"


def test_recency_decay_math():
    now = now_utc()
    r = MemoryRecord(id="x", npc_id="t", type="observation", text="e", importance=5,
                     created_at=now - timedelta(hours=100),
                     last_accessed=now - timedelta(hours=100))
    assert abs(recency(r, now) - config.RECENCY_DECAY ** 100) < 1e-9


# -------------------------------------------------------------- importance (P2.1)

def test_fixed_importance_skips_llm():
    calls = []
    def llm(prompt):
        calls.append(prompt)
        return "[]"
    scores = score_importance_batch(
        [{"event_type": "player_attack_npc", "text": "akira attacked me"},
         {"event_type": "player_greeting", "text": "akira said hello"}],
        "Tom the blacksmith", llm=llm,
    )
    assert scores == [9, 2] and calls == []      # toàn loại cứng -> 0 LLM call


def test_importance_batch_mixed():
    scores = score_importance_batch(
        [{"event_type": "player_gift", "text": "akira gave me gold"},
         {"event_type": "", "text": "akira saved my daughter from the river"},
         {"event_type": "", "text": "akira asked about the weather"}],
        "Tom", llm=lambda p: "[10, 2]",
    )
    assert scores == [7, 10, 2]                   # gift từ bảng, 2 cái còn lại từ LLM


def test_importance_parse_robust():
    """LLM local trả rác vẫn không được làm sập pipeline."""
    scores = score_importance_batch([{"event_type": "", "text": "x"}], "Tom",
                                    llm=lambda p: "chắc khoảng 8 điểm nhé")
    assert scores == [8]
    scores = score_importance_batch([{"event_type": "", "text": "x"}], "Tom",
                                    llm=lambda p: "không chấm được")
    assert scores == [5]                          # fallback trung tính


# ----------------------------------------------------------------- reflection

def _reflection_llm(prompt: str) -> str:
    """Fake LLM cho cả 2 bước: sinh câu hỏi, rồi sinh nhận định kèm nguồn thật."""
    import re
    if "câu hỏi cấp cao" in prompt:
        return "Akira là người thế nào?"
    ids = re.findall(r"mem_[0-9a-f]+", prompt)[:2]
    return f"NHẬN ĐỊNH: Akira là người đáng tin cậy, đã giữ lời nhiều lần\nNGUỒN: {', '.join(ids)}"


def test_reflection_forms_opinion(store):
    """B3: reflection ra nhận định type=reflection, BẮT BUỘC có source_ids thật."""
    for i in range(5):
        store.add("tom", "observation", f"akira kept promise number {i} helping villagers", 6)
    written = reflect(store, "tom", llm=_reflection_llm)
    assert written and written[0].type == "reflection"
    valid = {r.id for r in store.recent("tom", limit=50)}
    assert written[0].source_ids and set(written[0].source_ids) <= valid


def test_reflection_drops_unsourced_insight(store):
    """Nhận định không truy được nguồn -> KHÔNG ghi (chống nhận định bịa)."""
    store.add("tom", "observation", "some event", 5)
    written = reflect(store, "tom",
                      llm=lambda p: "Akira tốt" if "câu hỏi" in p else "NHẬN ĐỊNH: bịa\nNGUỒN: mem_khongtontai")
    assert written == []


def test_should_reflect_threshold(store, monkeypatch):
    monkeypatch.setattr(config, "REFLECTION_THRESHOLD", 20)
    for _ in range(3):
        store.add("tom", "observation", "big event happened", 9)   # tổng 27 >= 20
    assert should_reflect(store, "tom")
    reflect(store, "tom", llm=_reflection_llm)
    # Sau reflect: watermark dời lên -> chưa đủ ký ức mới
    assert not should_reflect(store, "tom")
