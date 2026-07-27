"""Live scenario-B1 test — run at home, REQUIRES API keys (see TEST_AT_HOME.md).

Writes a promise + 30 noise events into a temp store (real embeddings), asks
the NPC (real Claude Haiku), then grades with LLM-as-judge: does the reply
show the NPC remembers the promise. Prints PASS/FAIL.

Run:  python -m scripts.demo_b1
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
PERSONA = ("Blacksmith Tom, 52 years old. Gruff but kind-hearted, "
           "values people who keep their word above all.")


def main() -> int:
    llm = AnthropicLLM(timeout=30)
    now = datetime.now(timezone.utc)

    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(db_path=Path(tmp) / "demo.sqlite",
                            client=QdrantClient(":memory:"))

        print("1) Writing the promise (5 hours ago) + 30 noise events ...")
        ts = now - timedelta(hours=5)
        promise = store.add(MemoryRecord.new(
            NPC, "observation", "Akira promised to bring me medicine for my illness",
            importance=8, created_at=ts, participants=["player:akira"]))
        for i in range(30):
            store.add(MemoryRecord.new(
                NPC, "observation",
                f"Villager number {i} walked across the square outside the workshop",
                importance=2, created_at=now - timedelta(minutes=30)))

        question = "Hello Tom, do you remember what I promised you?"
        print(f"2) Player asks: {question!r}")
        cands, relevance = store.candidates(NPC, question)
        memories = scoring.retrieve(cands, relevance, top_k=8, store=store)
        retrieved_ok = promise.id in [m.id for m in memories]
        print(f"   Retrieval: promise {'IS' if retrieved_ok else 'IS NOT'} in the top-8")

        print("3) NPC replies (streaming): ", end="", flush=True)
        reply_parts = []
        for event in respond(NPC, question, memories, persona=PERSONA,
                             relationship="warm", llm=llm):
            if event["type"] == "text":
                print(event["text"], end="", flush=True)
                reply_parts.append(event["text"])
        reply = "".join(reply_parts)
        print()

        print("4) LLM-as-judge grading ...")
        verdict = judge_remembers(
            reply, "the NPC remembers that the player promised to bring medicine", llm)
        print(f"   remembers={verdict['remembers']} — {verdict['reason']}")

        passed = retrieved_ok and verdict["remembers"]
        print(f"\n{'PASS' if passed else 'FAIL'} — scenario B1")
        return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
