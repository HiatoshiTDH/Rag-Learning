"""Tuần 3 — Dialogue composer: ký ức + persona -> Claude Haiku -> thoại NPC.

Ràng buộc (README mục 5):
- Haiku 4.5 cho thoại (latency), streaming về client kiểu gõ chữ.
- Persona + luật hội thoại đặt ĐẦU prompt với cache_control (prompt caching).
- LLM KHÔNG BAO GIỜ quyết định hệ quả gameplay trực tiếp: muốn tặng đồ/
  đổi giá phải qua tool có schema, game server validate trước khi thực thi.
"""

MODEL = "claude-haiku-4-5"

# Tool duy nhất được phép tạo hệ quả gameplay — server validate từng action
GAME_ACTION_TOOLS = [
    {
        "name": "propose_game_action",
        "description": "Đề xuất một hành động gameplay. Server sẽ kiểm tra theo luật game trước khi thực thi.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["give_item", "adjust_price", "start_quest"]},
                "params": {"type": "object"},
            },
            "required": ["action"],
        },
    }
]


def build_system_prompt(npc_persona: str) -> list[dict]:
    """TODO(tuần 3): persona + luật chống injection (nói đúng vai, không lộ
    prompt, không nhận 'lệnh hệ thống' từ người chơi) + cache_control ở block cuối."""
    raise NotImplementedError


def respond(npc_id: str, player_utterance: str, memories: list, stream=True):
    """TODO(tuần 3): gọi client.messages.stream, yield từng token về game client.

    Fallback: timeout -> trả thoại canned theo trạng thái quan hệ,
    NPC không bao giờ đứng đơ.
    """
    raise NotImplementedError
