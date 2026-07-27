"""Week 3 — FastAPI memory service, separate from the game process.

The game client (Unity/Roblox) only talks HTTP/WebSocket to this service — it
never calls the Claude API from the game's main thread (hitches/freezes).

Endpoints:
  POST /npc/{npc_id}/event      -- write an observation (game event -> memory)
  POST /npc/{npc_id}/prefetch   -- player entered the trigger radius: retrieve
                                   memories + pre-build context BEFORE they press talk
  WS   /npc/{npc_id}/talk       -- streaming dialogue (typewriter-style)
  POST /npc/{npc_id}/reflect    -- run reflection (called periodically by a worker/ops)
  GET  /npc/{npc_id}/memories   -- debug: inspect the memory stream

Run: uvicorn src.server:app --port 8080
"""

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from src import config, reflection, scoring
from src.dialogue import respond
from src.llm import LLM, get_llm
from src.memory_store import MemoryRecord, MemoryStore
from src.relationship import RelationshipTracker

DEFAULT_PERSONA = "A friendly villager, plain-spoken, fond of decent people."


def _load_personas() -> dict[str, str]:
    for path in (config.PERSONAS_FILE, config.PERSONAS_EXAMPLE):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {}


class EventIn(BaseModel):
    kind: str = ""                      # "player_gift", "player_attack_npc"... (scoring.FIXED_IMPORTANCE)
    text: str = Field(min_length=1)     # "Akira gave me a bouquet of flowers"
    participants: list[str] = []        # ["player:akira"]
    type: str = "observation"


class PrefetchIn(BaseModel):
    context: str = Field(min_length=1)  # location/situation as the player approaches


class ReflectIn(BaseModel):
    force: bool = False                 # true: skip the importance threshold


def create_app(store: MemoryStore | None = None, llm: LLM | None = None,
               relationships: RelationshipTracker | None = None,
               personas: dict[str, str] | None = None) -> FastAPI:
    """Factory — tests inject a fake store/llm; in production leave None and
    the lifespan builds the real ones."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.store is None:
            app.state.store = MemoryStore()
        if app.state.relationships is None:
            app.state.relationships = RelationshipTracker(app.state.store.db_path)
        if app.state.llm is None:
            app.state.llm = get_llm(timeout=config.DIALOGUE_TIMEOUT)
        yield

    app = FastAPI(title="NPC Memory Service", lifespan=lifespan)
    app.state.store = store
    app.state.llm = llm
    app.state.relationships = relationships
    app.state.personas = personas if personas is not None else _load_personas()
    app.state.prefetch = {}  # npc_id -> {"memories": [...], "context": str}

    def persona_of(npc_id: str) -> str:
        return app.state.personas.get(npc_id, DEFAULT_PERSONA)

    def player_ids(participants: list[str]) -> list[str]:
        return [p.split(":", 1)[1] for p in participants if p.startswith("player:")]

    # ------------------------------------------------------------- events

    @app.post("/npc/{npc_id}/event")
    def post_event(npc_id: str, event: EventIn):
        """Write one observation. Filtering at the source is the game's job:
        only send on interactions/gameplay events, never every frame."""
        importance = scoring.score_importance_batch(
            [{"kind": event.kind, "text": event.text}],
            persona_of(npc_id), llm=app.state.llm)[0]
        record = MemoryRecord.new(
            npc_id=npc_id, type=event.type, text=event.text,
            importance=importance, participants=event.participants)
        app.state.store.add(record)

        affinity = None
        for player in player_ids(event.participants):
            affinity = app.state.relationships.apply_event(npc_id, player, event.kind)
        return {"id": record.id, "importance": importance, "affinity": affinity}

    # ----------------------------------------------------------- prefetch

    @app.post("/npc/{npc_id}/prefetch")
    def prefetch(npc_id: str, body: PrefetchIn):
        """Player entered the trigger radius: retrieve ahead of time so the
        talk button doesn't wait on vector search (README 5.1)."""
        cands, relevance = app.state.store.candidates(npc_id, body.context)
        memories = scoring.retrieve(cands, relevance, top_k=12, store=app.state.store)
        app.state.prefetch[npc_id] = {"memories": memories, "context": body.context}
        return {"memory_ids": [m.id for m in memories], "count": len(memories)}

    # --------------------------------------------------------------- talk

    @app.websocket("/npc/{npc_id}/talk")
    async def talk(ws: WebSocket, npc_id: str):
        """Each client message: {"utterance": str, "player_id": str?,
        "situation": str?}. The server streams back every dialogue.respond
        event and ends the turn with {"type": "done"}."""
        await ws.accept()
        store: MemoryStore = app.state.store
        try:
            while True:
                msg = await ws.receive_json()
                utterance = msg.get("utterance", "")
                player_id = msg.get("player_id", "player")
                situation = msg.get("situation", "")

                cached = app.state.prefetch.pop(npc_id, None)
                if cached is not None:
                    memories = cached["memories"]
                else:
                    cands, relevance = store.candidates(npc_id, utterance)
                    memories = scoring.retrieve(cands, relevance, top_k=12, store=store)

                rel_label = app.state.relationships.label(npc_id, player_id)
                reply_parts: list[str] = []
                for event in respond(
                        npc_id, utterance, memories,
                        persona=persona_of(npc_id), relationship=rel_label,
                        situation=situation, llm=app.state.llm):
                    if event["type"] == "text":
                        reply_parts.append(event["text"])
                    await ws.send_json(event)
                await ws.send_json({"type": "done"})

                # the exchange is itself a memory (type=dialogue) + logged for exploit review
                reply = "".join(reply_parts)
                store.add(MemoryRecord.new(
                    npc_id=npc_id, type="dialogue",
                    text=f"{player_id} said: \"{utterance}\" — I replied: \"{reply}\"",
                    importance=scoring.DEFAULT_IMPORTANCE,
                    participants=[f"player:{player_id}"]))
                _log_dialogue(npc_id, player_id, utterance, reply)
        except WebSocketDisconnect:
            pass

    # ------------------------------------------------------------ reflect

    @app.post("/npc/{npc_id}/reflect")
    def run_reflection(npc_id: str, body: ReflectIn | None = None):
        if app.state.llm is None:
            raise HTTPException(503, "LLM_BACKEND=none — reflection unavailable")
        force = bool(body and body.force)
        if force:
            created = reflection.reflect(npc_id, app.state.store, app.state.llm)
        else:
            created = reflection.maybe_reflect(npc_id, app.state.store, app.state.llm)
        return {"created": [{"id": r.id, "text": r.text, "source_ids": r.source_ids}
                            for r in created]}

    # -------------------------------------------------------------- debug

    @app.get("/npc/{npc_id}/memories")
    def list_memories(npc_id: str, limit: int = 20):
        return [{"id": m.id, "type": m.type, "text": m.text,
                 "importance": m.importance,
                 "created_at": m.created_at.isoformat(),
                 "source_ids": m.source_ids}
                for m in app.state.store.recent(npc_id, limit=limit)]

    return app


def _log_dialogue(npc_id: str, player_id: str, utterance: str, reply: str) -> None:
    """Log every conversation — for reviewing exploits/injection later (README 5.3)."""
    config.DIALOGUE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with config.DIALOGUE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "npc_id": npc_id, "player_id": player_id,
            "utterance": utterance, "reply": reply,
        }, ensure_ascii=False) + "\n")


app = create_app()
