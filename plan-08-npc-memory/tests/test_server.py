"""Test the memory service over HTTP/WebSocket (TestClient — still offline)."""

import pytest
from fastapi.testclient import TestClient

from src import config
from src.llm import ScriptedLLM
from src.relationship import RelationshipTracker
from src.server import create_app
from tests.conftest import seed

NPC = "blacksmith_tom"
PERSONAS = {NPC: "Blacksmith Tom: gruff but kind-hearted, values people who keep their word."}


@pytest.fixture
def make_client(store, tmp_path, monkeypatch):
    """Factory: make_client(llm) -> TestClient with a temp store/relationships."""
    monkeypatch.setattr(config, "DIALOGUE_LOG", tmp_path / "dialogue_log.jsonl")
    relationships = RelationshipTracker(tmp_path / "memories.sqlite")

    def _make(llm=None):
        app = create_app(store=store, llm=llm, relationships=relationships,
                         personas=PERSONAS)
        return TestClient(app)

    return _make


def test_event_fixed_importance_and_relationship(make_client, store):
    with make_client() as client:  # llm=None: importance from the fixed table
        r = client.post(f"/npc/{NPC}/event", json={
            "kind": "player_gift", "text": "Akira gave me a bouquet of flowers",
            "participants": ["player:akira"]})
        assert r.status_code == 200
        body = r.json()
        assert body["importance"] == 7      # FIXED_IMPORTANCE table, no LLM needed
        assert body["affinity"] == 2        # relationship warms up
        assert store.get(body["id"]).text == "Akira gave me a bouquet of flowers"

        r = client.post(f"/npc/{NPC}/event", json={
            "kind": "player_attack_npc", "text": "Akira swung a sword at me",
            "participants": ["player:akira"]})
        assert r.json()["importance"] == 9
        assert r.json()["affinity"] == -4   # 2 - 6 -> turns cold (B2)


def test_prefetch_returns_relevant_ids(make_client, store, now):
    promise = seed(store, NPC, "Akira promised to bring me medicine for my illness",
                   importance=8, hours_ago=5, now=now)
    with make_client() as client:
        r = client.post(f"/npc/{NPC}/prefetch",
                        json={"context": "Akira approaches, once promised medicine"})
        assert r.status_code == 200
        assert promise.id in r.json()["memory_ids"]


def test_ws_talk_streams_reply_and_records_dialogue(make_client, store, now):
    seed(store, NPC, "Akira promised to bring me medicine for my illness", importance=8,
         hours_ago=5, now=now)
    llm = ScriptedLLM(["Ah, the medicine... so you do remember your promise?"])
    with make_client(llm) as client:
        with client.websocket_connect(f"/npc/{NPC}/talk") as ws:
            ws.send_json({"utterance": "I brought you the medicine",
                          "player_id": "akira"})
            pieces, event = [], ws.receive_json()
            while event["type"] != "done":
                if event["type"] == "text":
                    pieces.append(event["text"])
                event = ws.receive_json()
        assert "".join(pieces) == "Ah, the medicine... so you do remember your promise?"

        # the retrieved memory must be in the prompt sent to the LLM
        assert "medicine" in llm.calls[0]["messages"][0]["content"]
        # the exchange is recorded as a type=dialogue memory
        dialogues = [m for m in store.recent(NPC) if m.type == "dialogue"]
        assert len(dialogues) == 1 and "akira" in dialogues[0].text
        # and the conversation is logged (for exploit review later)
        assert config.DIALOGUE_LOG.exists()


def test_ws_talk_without_llm_falls_back(make_client):
    with make_client(llm=None) as client:
        with client.websocket_connect(f"/npc/{NPC}/talk") as ws:
            ws.send_json({"utterance": "hello", "player_id": "akira"})
            types = []
            event = ws.receive_json()
            while event["type"] != "done":
                types.append(event["type"])
                event = ws.receive_json()
        assert "fallback" in types  # the NPC never freezes


def test_reflect_endpoint_forced(make_client, store, now):
    for i in range(3):
        seed(store, NPC, f"Akira kept a promise, time {i}", importance=8,
             hours_ago=2, now=now)
    llm = ScriptedLLM([
        {"questions": ["Is Akira trustworthy?"]},
        {"insight": "Akira is trustworthy", "importance": 8, "source_indexes": [1]},
    ])
    with make_client(llm) as client:
        r = client.post(f"/npc/{NPC}/reflect", json={"force": True})
        created = r.json()["created"]
        assert len(created) == 1 and created[0]["source_ids"]

        # the debug endpoint shows the freshly written reflection
        memories = client.get(f"/npc/{NPC}/memories").json()
        assert any(m["type"] == "reflection" for m in memories)
