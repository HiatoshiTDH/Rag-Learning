"""Test memory service qua HTTP/WebSocket (TestClient — vẫn offline)."""

import pytest
from fastapi.testclient import TestClient

from src import config
from src.llm import ScriptedLLM
from src.relationship import RelationshipTracker
from src.server import create_app
from tests.conftest import seed

NPC = "blacksmith_tom"
PERSONAS = {NPC: "Thợ rèn Tom: cộc cằn nhưng tốt bụng, quý người giữ lời hứa."}


@pytest.fixture
def make_client(store, tmp_path, monkeypatch):
    """Factory: make_client(llm) -> TestClient với store/relationship tạm."""
    monkeypatch.setattr(config, "DIALOGUE_LOG", tmp_path / "dialogue_log.jsonl")
    relationships = RelationshipTracker(tmp_path / "memories.sqlite")

    def _make(llm=None):
        app = create_app(store=store, llm=llm, relationships=relationships,
                         personas=PERSONAS)
        return TestClient(app)

    return _make


def test_event_fixed_importance_and_relationship(make_client, store):
    with make_client() as client:  # llm=None: importance từ bảng cứng
        r = client.post(f"/npc/{NPC}/event", json={
            "kind": "player_gift", "text": "Akira tặng ta một bó hoa",
            "participants": ["player:akira"]})
        assert r.status_code == 200
        body = r.json()
        assert body["importance"] == 7      # bảng FIXED_IMPORTANCE, không cần LLM
        assert body["affinity"] == 2        # quan hệ ấm lên
        assert store.get(body["id"]).text == "Akira tặng ta một bó hoa"

        r = client.post(f"/npc/{NPC}/event", json={
            "kind": "player_attack_npc", "text": "Akira vung kiếm vào ta",
            "participants": ["player:akira"]})
        assert r.json()["importance"] == 9
        assert r.json()["affinity"] == -4   # 2 - 6 -> lạnh nhạt (B2)


def test_prefetch_returns_relevant_ids(make_client, store, now):
    promise = seed(store, NPC, "Akira hứa mang thuốc chữa bệnh cho ta",
                   importance=8, hours_ago=5, now=now)
    with make_client() as client:
        r = client.post(f"/npc/{NPC}/prefetch",
                        json={"context": "Akira lại gần, từng hứa mang thuốc"})
        assert r.status_code == 200
        assert promise.id in r.json()["memory_ids"]


def test_ws_talk_streams_reply_and_records_dialogue(make_client, store, now):
    seed(store, NPC, "Akira hứa mang thuốc chữa bệnh cho ta", importance=8,
         hours_ago=5, now=now)
    llm = ScriptedLLM(["À, thuốc à... cậu vẫn nhớ lời hứa đấy chứ?"])
    with make_client(llm) as client:
        with client.websocket_connect(f"/npc/{NPC}/talk") as ws:
            ws.send_json({"utterance": "Cháu mang thuốc đến cho bác đây",
                          "player_id": "akira"})
            pieces, event = [], ws.receive_json()
            while event["type"] != "done":
                if event["type"] == "text":
                    pieces.append(event["text"])
                event = ws.receive_json()
        assert "".join(pieces) == "À, thuốc à... cậu vẫn nhớ lời hứa đấy chứ?"

        # ký ức retrieve được phải nằm trong prompt gửi LLM
        assert "thuốc" in llm.calls[0]["messages"][0]["content"]
        # lượt thoại được ghi lại thành ký ức type=dialogue
        dialogues = [m for m in store.recent(NPC) if m.type == "dialogue"]
        assert len(dialogues) == 1 and "akira" in dialogues[0].text
        # và ghi log hội thoại (xử lý khai thác về sau)
        assert config.DIALOGUE_LOG.exists()


def test_ws_talk_without_llm_falls_back(make_client):
    with make_client(llm=None) as client:
        with client.websocket_connect(f"/npc/{NPC}/talk") as ws:
            ws.send_json({"utterance": "chào bác", "player_id": "akira"})
            types = []
            event = ws.receive_json()
            while event["type"] != "done":
                types.append(event["type"])
                event = ws.receive_json()
        assert "fallback" in types  # NPC không bao giờ đứng đơ


def test_reflect_endpoint_forced(make_client, store, now):
    for i in range(3):
        seed(store, NPC, f"Akira giữ lời hứa lần thứ {i}", importance=8,
             hours_ago=2, now=now)
    llm = ScriptedLLM([
        {"questions": ["Akira có đáng tin không?"]},
        {"insight": "Akira đáng tin", "importance": 8, "source_indexes": [1]},
    ])
    with make_client(llm) as client:
        r = client.post(f"/npc/{NPC}/reflect", json={"force": True})
        created = r.json()["created"]
        assert len(created) == 1 and created[0]["source_ids"]

        # debug endpoint soi được reflection vừa ghi
        memories = client.get(f"/npc/{NPC}/memories").json()
        assert any(m["type"] == "reflection" for m in memories)
