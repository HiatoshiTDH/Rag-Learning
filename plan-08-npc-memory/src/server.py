"""P3.4 — FastAPI memory service, tách khỏi game process.

Game engine (Unity/Roblox) chỉ gọi HTTP — không bao giờ gọi LLM từ main thread.

  POST /npc/{npc_id}/event      ghi observation (kèm chấm importance)
  POST /npc/{npc_id}/prefetch   player vào trigger radius: retrieve + cache sẵn
  POST /npc/{npc_id}/talk       một lượt thoại (ghi dialogue vào memory luôn)
  POST /npc/{npc_id}/reflect    ép chạy reflection (bình thường tự trigger)
  GET  /npc/{npc_id}/memories   soi ký ức (debug)

Chạy:  uvicorn src.server:app --port 8080
"""

from functools import lru_cache

from fastapi import FastAPI
from pydantic import BaseModel

from src import config
from src.dialogue import respond
from src.memory_store import MemoryStore
from src.reflection import reflect, should_reflect
from src.scoring import retrieve, score_importance_batch

app = FastAPI(title="npc-memory-service")

# Persona đăng ký lúc khởi động — game thật sẽ load từ data của nó
PERSONAS: dict[str, str] = {
    "blacksmith_tom": ("Tom, thợ rèn trung niên của làng Eldermoor. Cục cằn nhưng tốt bụng, "
                       "quý người giữ lời hứa, ghét kẻ trộm cắp. Đang lo lắng vì mỏ sắt cạn."),
}

# Cache prefetch: npc_id -> memories đã retrieve sẵn (P5 sẽ key thêm player_id)
_prefetched: dict[str, list] = {}


@lru_cache(maxsize=1)
def get_store() -> MemoryStore:
    """Singleton — test override bằng app.dependency_overrides hoặc monkeypatch."""
    return MemoryStore()


class EventIn(BaseModel):
    text: str
    event_type: str = ""            # khớp FIXED_IMPORTANCE thì khỏi gọi LLM
    participants: list[str] = []


class TalkIn(BaseModel):
    player_utterance: str
    player_id: str = "player"


@app.post("/npc/{npc_id}/event")
def post_event(npc_id: str, event: EventIn):
    store = get_store()
    persona = PERSONAS.get(npc_id, "một NPC trong game")
    importance = score_importance_batch(
        [{"event_type": event.event_type, "text": event.text}], persona
    )[0]
    record = store.add(npc_id=npc_id, type="observation", text=event.text,
                       importance=importance, participants=event.participants)
    reflected = False
    if should_reflect(store, npc_id):
        reflect(store, npc_id)      # v1 sync; P5 chuyển background task
        reflected = True
    return {"memory_id": record.id, "importance": importance, "reflected": reflected}


@app.post("/npc/{npc_id}/prefetch")
def post_prefetch(npc_id: str, body: TalkIn):
    """Gọi khi player vào trigger radius — retrieve trước khi họ bấm nói chuyện."""
    store = get_store()
    context = f"{body.player_id} đến gần bắt chuyện. {body.player_utterance}".strip()
    memories = retrieve(store.candidates(npc_id, context))
    _prefetched[npc_id] = memories
    return {"prefetched": len(memories)}


@app.post("/npc/{npc_id}/talk")
def post_talk(npc_id: str, body: TalkIn):
    store = get_store()
    persona = PERSONAS.get(npc_id, "một NPC trong game")

    memories = _prefetched.pop(npc_id, None)
    if memories is None:
        memories = retrieve(store.candidates(npc_id, body.player_utterance))
    store.touch([m.id for m in memories])

    result = respond(persona, memories, body.player_utterance)

    # Lượt thoại tự nó là một ký ức
    store.add(npc_id=npc_id, type="dialogue",
              text=f'{body.player_id} nói: "{body.player_utterance}" — tôi đáp: "{result["text"]}"',
              importance=3, participants=[f"player:{body.player_id}"])
    return result


@app.post("/npc/{npc_id}/reflect")
def post_reflect(npc_id: str):
    written = reflect(get_store(), npc_id)
    return {"insights": [r.text for r in written]}


@app.get("/npc/{npc_id}/memories")
def get_memories(npc_id: str, limit: int = 20):
    return [
        {"id": r.id, "type": r.type, "text": r.text, "importance": r.importance,
         "created_at": r.created_at.isoformat(), "source_ids": r.source_ids}
        for r in get_store().recent(npc_id, limit=limit)
    ]
