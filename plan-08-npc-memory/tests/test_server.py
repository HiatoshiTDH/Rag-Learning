"""Test FastAPI service end-to-end offline (fake embedder + fake LLM backend)."""

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from src import config, server
from src.embedding import HashEmbedder
from src.memory_store import MemoryStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = MemoryStore(db_path=tmp_path / "mem.sqlite",
                        client=QdrantClient(":memory:"), embedder=HashEmbedder())
    monkeypatch.setattr(server, "get_store", lambda: store)
    monkeypatch.setattr(config, "LLM_BACKEND", "fake")
    server._prefetched.clear()
    return TestClient(server.app)


def test_event_fixed_importance_no_llm(client):
    r = client.post("/npc/blacksmith_tom/event",
                    json={"text": "akira tặng tôi 50 vàng", "event_type": "player_gift"})
    assert r.status_code == 200
    assert r.json()["importance"] == 7            # từ bảng FIXED_IMPORTANCE


def test_talk_returns_text_and_records_dialogue(client):
    client.post("/npc/blacksmith_tom/event",
                json={"text": "akira promised to bring medicine", "event_type": "player_promise"})
    r = client.post("/npc/blacksmith_tom/talk",
                    json={"player_utterance": "ông còn nhớ lời hứa về thuốc không?",
                          "player_id": "akira"})
    assert r.status_code == 200 and r.json()["text"]

    mems = client.get("/npc/blacksmith_tom/memories").json()
    assert any(m["type"] == "dialogue" for m in mems)   # lượt thoại tự thành ký ức


def test_prefetch_then_talk_uses_cache(client):
    client.post("/npc/blacksmith_tom/event",
                json={"text": "akira helped repair my forge", "event_type": "player_gift"})
    r = client.post("/npc/blacksmith_tom/prefetch",
                    json={"player_utterance": "", "player_id": "akira"})
    assert r.json()["prefetched"] >= 1
    assert "blacksmith_tom" in server._prefetched
    client.post("/npc/blacksmith_tom/talk",
                json={"player_utterance": "chào ông", "player_id": "akira"})
    assert "blacksmith_tom" not in server._prefetched   # cache dùng 1 lần rồi bỏ


def test_memories_endpoint_scoped(client):
    client.post("/npc/blacksmith_tom/event",
                json={"text": "secret of tom", "event_type": "player_gift"})
    assert client.get("/npc/other_npc/memories").json() == []
