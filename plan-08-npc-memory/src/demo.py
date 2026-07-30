"""P3.5 — Demo hội thoại trong terminal, không cần game engine.

    python -m src.demo

Lệnh trong phiên:
  /event <text>      bơm một sự kiện vào memory (VD: /event Người chơi tặng tôi 50 vàng)
  /memories          soi ký ức hiện tại của NPC
  /reflect           ép chạy reflection
  /quit              thoát
Còn lại: gõ gì là nói với NPC cái đó.
"""

from src.memory_store import MemoryStore
from src.reflection import reflect
from src.scoring import retrieve, score_importance_batch
from src.dialogue import respond

NPC_ID = "blacksmith_tom"
PERSONA = ("Tom, thợ rèn trung niên của làng Eldermoor. Cục cằn nhưng tốt bụng, "
           "quý người giữ lời hứa, ghét kẻ trộm cắp. Đang lo lắng vì mỏ sắt cạn.")


def main() -> None:
    store = MemoryStore()
    print(f"— Nói chuyện với {NPC_ID} (gõ /quit để thoát, /help xem lệnh) —")

    while True:
        try:
            line = input("Bạn: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue

        if line == "/quit":
            break
        if line == "/help":
            print(__doc__)
        elif line.startswith("/event "):
            text = line[len("/event "):]
            imp = score_importance_batch([{"text": text}], PERSONA)[0]
            store.add(npc_id=NPC_ID, type="observation", text=text, importance=imp)
            print(f"  [đã ghi, importance={imp}]")
        elif line == "/memories":
            for r in store.recent(NPC_ID, limit=15):
                print(f"  [{r.type}][imp {r.importance}] {r.text}")
        elif line == "/reflect":
            for r in reflect(store, NPC_ID):
                print(f"  [nhận định] {r.text}  (nguồn: {len(r.source_ids)} ký ức)")
        else:
            memories = retrieve(store.candidates(NPC_ID, line))
            store.touch([m.id for m in memories])
            result = respond(PERSONA, memories, line)
            print(f"{NPC_ID}: {result['text']}")
            for a in result["actions"]:
                print(f"  [action ĐƯỢC DUYỆT] {a}")
            for a in result["rejected"]:
                print(f"  [action BỊ TỪ CHỐI] {a}")
            store.add(npc_id=NPC_ID, type="dialogue",
                      text=f'Người chơi nói: "{line}" — tôi đáp: "{result["text"]}"',
                      importance=3, participants=["player:demo"])


if __name__ == "__main__":
    main()
