"""Tuần 3 — FastAPI memory service, tách khỏi game process.

Game client (Unity/Roblox) chỉ gọi HTTP/WebSocket vào đây — không bao giờ
gọi Claude API trực tiếp từ main thread của game (gây hitch/freeze).

Endpoints dự kiến:
  POST /npc/{npc_id}/event      -- ghi observation (game event -> memory)
  POST /npc/{npc_id}/prefetch   -- người chơi vào trigger radius: retrieve
                                   ký ức + dựng prompt TRƯỚC khi họ bấm nói
  WS   /npc/{npc_id}/talk       -- hội thoại streaming
"""

# TODO(tuần 3): from fastapi import FastAPI; app = FastAPI(); nối các module lại.
