"""Tuần 3 — FastAPI memory service, tách khỏi game process.

Game client (Unity/Roblox) chỉ gọi HTTP/WebSocket vào đây — không bao giờ
gọi Claude API trực tiếp từ main thread của game (gây hitch/freeze).

Endpoints:
  POST /npc/{npc_id}/event      -- ghi observation (game event -> memory)
  POST /npc/{npc_id}/prefetch   -- người chơi vào trigger radius: retrieve
                                   ký ức + dựng sẵn context TRƯỚC khi họ bấm nói
  WS   /npc/{npc_id}/talk       -- hội thoại streaming (kiểu gõ chữ)
  POST /npc/{npc_id}/reflect    -- chạy reflection (worker/ops gọi định kỳ)
  GET  /npc/{npc_id}/memories   -- debug: soi stream ký ức

Chạy: uvicorn src.server:app --port 8080
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

DEFAULT_PERSONA = "Một dân làng thân thiện, nói năng mộc mạc, quý người tử tế."


def _load_personas() -> dict[str, str]:
    for path in (config.PERSONAS_FILE, config.PERSONAS_EXAMPLE):
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {}


class EventIn(BaseModel):
    kind: str = ""                      # "player_gift", "player_attack_npc"... (scoring.FIXED_IMPORTANCE)
    text: str = Field(min_length=1)     # "Akira tặng ta một bó hoa"
    participants: list[str] = []        # ["player:akira"]
    type: str = "observation"


class PrefetchIn(BaseModel):
    context: str = Field(min_length=1)  # địa điểm/tình huống lúc người chơi lại gần


class ReflectIn(BaseModel):
    force: bool = False                 # true: bỏ qua ngưỡng importance


def create_app(store: MemoryStore | None = None, llm: LLM | None = None,
               relationships: RelationshipTracker | None = None,
               personas: dict[str, str] | None = None) -> FastAPI:
    """Factory — test inject store/llm fake; chạy thật thì để None, lifespan tự dựng."""

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
        """Ghi 1 observation. Lọc tại nguồn là việc của game: chỉ gửi khi có
        tương tác/sự kiện gameplay, không gửi mọi frame."""
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
        """Người chơi vào trigger radius: retrieve trước để lúc bấm nói không
        phải chờ vector search (README 5.1)."""
        cands, relevance = app.state.store.candidates(npc_id, body.context)
        memories = scoring.retrieve(cands, relevance, top_k=12, store=app.state.store)
        app.state.prefetch[npc_id] = {"memories": memories, "context": body.context}
        return {"memory_ids": [m.id for m in memories], "count": len(memories)}

    # --------------------------------------------------------------- talk

    @app.websocket("/npc/{npc_id}/talk")
    async def talk(ws: WebSocket, npc_id: str):
        """Mỗi message client gửi: {"utterance": str, "player_id": str?,
        "situation": str?}. Server stream về từng event của dialogue.respond,
        kết thúc lượt bằng {"type": "done"}."""
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

                # lượt thoại cũng là ký ức (type=dialogue) + log để xử lý khai thác
                reply = "".join(reply_parts)
                store.add(MemoryRecord.new(
                    npc_id=npc_id, type="dialogue",
                    text=f"{player_id} nói: \"{utterance}\" — ta đáp: \"{reply}\"",
                    importance=scoring.DEFAULT_IMPORTANCE,
                    participants=[f"player:{player_id}"]))
                _log_dialogue(npc_id, player_id, utterance, reply)
        except WebSocketDisconnect:
            pass

    # ------------------------------------------------------------ reflect

    @app.post("/npc/{npc_id}/reflect")
    def run_reflection(npc_id: str, body: ReflectIn | None = None):
        if app.state.llm is None:
            raise HTTPException(503, "LLM_BACKEND=none — không chạy reflection được")
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
    """Ghi log toàn bộ hội thoại — xử lý khai thác/injection về sau (README 5.3)."""
    config.DIALOGUE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with config.DIALOGUE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "npc_id": npc_id, "player_id": player_id,
            "utterance": utterance, "reply": reply,
        }, ensure_ascii=False) + "\n")


app = create_app()
