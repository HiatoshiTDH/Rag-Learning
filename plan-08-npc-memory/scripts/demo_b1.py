"""Bài test live kịch bản B1 — chạy trên máy nhà, CẦN API key (xem TEST_AT_HOME.md).

Ghi lời hứa + 30 sự kiện nhiễu vào một store tạm (embedding thật), hỏi NPC
(Claude Haiku thật), rồi chấm bằng LLM-as-judge: thoại có thể hiện việc
NPC nhớ lời hứa không. In PASS/FAIL.

Chạy:  python -m scripts.demo_b1
"""

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from qdrant_client import QdrantClient

from src import scoring
from src.dialogue import respond
from src.judge import judge_remembers
from src.llm import AnthropicLLM
from src.memory_store import MemoryRecord, MemoryStore

NPC = "blacksmith_tom"
PERSONA = ("Thợ rèn Tom, 52 tuổi. Cộc cằn nhưng tốt bụng, "
           "cực kỳ quý người giữ lời hứa.")


def main() -> int:
    llm = AnthropicLLM(timeout=30)
    now = datetime.now(timezone.utc)

    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(db_path=Path(tmp) / "demo.sqlite",
                            client=QdrantClient(":memory:"))

        print("1) Ghi lời hứa (5 giờ trước) + 30 sự kiện nhiễu ...")
        ts = now - timedelta(hours=5)
        promise = store.add(MemoryRecord.new(
            NPC, "observation", "Akira hứa sẽ mang thuốc chữa bệnh đến cho ta",
            importance=8, created_at=ts, participants=["player:akira"]))
        for i in range(30):
            store.add(MemoryRecord.new(
                NPC, "observation",
                f"Dân làng thứ {i} đi ngang qua quảng trường trước xưởng",
                importance=2, created_at=now - timedelta(minutes=30)))

        question = "Chào bác Tom, bác còn nhớ cháu đã hứa gì với bác không?"
        print(f"2) Người chơi hỏi: {question!r}")
        cands, relevance = store.candidates(NPC, question)
        memories = scoring.retrieve(cands, relevance, top_k=8, store=store)
        retrieved_ok = promise.id in [m.id for m in memories]
        print(f"   Retrieval: lời hứa {'CÓ' if retrieved_ok else 'KHÔNG'} trong top-8")

        print("3) NPC trả lời (streaming): ", end="", flush=True)
        reply_parts = []
        for event in respond(NPC, question, memories, persona=PERSONA,
                             relationship="warm", llm=llm):
            if event["type"] == "text":
                print(event["text"], end="", flush=True)
                reply_parts.append(event["text"])
        reply = "".join(reply_parts)
        print()

        print("4) LLM-as-judge chấm ...")
        verdict = judge_remembers(
            reply, "NPC nhớ rằng người chơi đã hứa mang thuốc cho mình", llm)
        print(f"   remembers={verdict['remembers']} — {verdict['reason']}")

        passed = retrieved_ok and verdict["remembers"]
        print(f"\n{'PASS' if passed else 'FAIL'} — kịch bản B1")
        return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
