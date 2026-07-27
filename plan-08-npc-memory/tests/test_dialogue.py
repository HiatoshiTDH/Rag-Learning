"""Unit test cho dialogue composer (tuần 3): prompt caching + chống injection,
streaming, canned fallback, và server-side validation của game action."""

from src.dialogue import (CANNED_FALLBACK, GAME_ACTION_TOOLS, build_system_prompt,
                          compose_user_message, respond, validate_action)
from src.llm import ScriptedLLM
from src.memory_store import MemoryRecord

PERSONA = "Thợ rèn Tom: cộc cằn nhưng tốt bụng."


def _memory(text: str) -> MemoryRecord:
    return MemoryRecord.new("blacksmith_tom", "observation", text, 5)


# ------------------------------------------------------------ system prompt

def test_system_prompt_persona_first_cache_control_last():
    blocks = build_system_prompt(PERSONA)
    assert PERSONA in blocks[0]["text"]
    # cache_control ở block CUỐI -> cache cả persona + luật (README 5.1)
    assert blocks[-1]["cache_control"] == {"type": "ephemeral"}
    rules = blocks[-1]["text"]
    assert "propose_game_action" in rules          # gameplay chỉ qua tool
    assert "KHÔNG phải mệnh lệnh" in rules          # untrusted input
    assert "prompt" in rules                        # không tiết lộ prompt


def test_user_message_wraps_untrusted_input():
    msg = compose_user_message("xin chào", [_memory("Akira từng tặng ta hoa")],
                               situation="buổi sáng ở chợ", relationship="warm")
    assert "<player_utterance>\nxin chào\n</player_utterance>" in msg
    assert "Akira từng tặng ta hoa" in msg
    assert "buổi sáng ở chợ" in msg and "warm" in msg


# ----------------------------------------------------------------- respond

def test_respond_streams_text_with_tools_declared():
    llm = ScriptedLLM(["Chào Akira, lâu rồi không gặp."])
    events = list(respond("tom", "chào bác", [], persona=PERSONA, llm=llm))
    text = "".join(e["text"] for e in events if e["type"] == "text")
    assert text == "Chào Akira, lâu rồi không gặp."
    assert len([e for e in events if e["type"] == "text"]) > 1  # streaming từng mẩu
    assert llm.calls[0]["tools"] == GAME_ACTION_TOOLS


def test_timeout_falls_back_to_canned_line_by_relationship():
    llm = ScriptedLLM([TimeoutError("API quá chậm")])
    events = list(respond("tom", "chào", [], persona=PERSONA,
                          relationship="hostile", llm=llm))
    assert events[0]["text"] == CANNED_FALLBACK["hostile"]
    assert events[-1]["type"] == "fallback"


def test_no_llm_configured_still_answers():
    """LLM_BACKEND=none / mất mạng hoàn toàn -> NPC vẫn không đứng đơ."""
    events = list(respond("tom", "chào", [], persona=PERSONA, llm=None))
    assert events[-1]["type"] == "fallback"
    assert events[0]["text"] == CANNED_FALLBACK["neutral"]


def test_accepted_action_passes_validation():
    llm = ScriptedLLM([{
        "text": "Cầm lấy bó hoa này.",
        "tool_calls": [{"name": "propose_game_action",
                        "input": {"action": "give_item", "params": {"item": "hoa dại"}}}],
    }])
    events = list(respond("tom", "bác có gì cho cháu không?", [], persona=PERSONA,
                          llm=llm, game_state={"giftable_items": ["hoa dại"]}))
    actions = [e for e in events if e["type"] == "action"]
    assert actions == [{"type": "action", "action": "give_item",
                        "params": {"item": "hoa dại"}, "accepted": True, "reason": "ok"}]


# --------------------------------------------------------- validate_action

def test_validate_deny_by_default():
    # game_state không khai báo gì -> mọi thứ bị chặn (secure default)
    assert validate_action("give_item", {"item": "vàng"}) == (
        False, "item 'vàng' không nằm trong danh sách được tặng")
    assert not validate_action("start_quest", {"quest_id": "q1"})[0]
    assert not validate_action("open_admin_panel", {})[0]


def test_validate_price_bounds():
    assert validate_action("adjust_price", {"pct": 20})[0]
    assert validate_action("adjust_price", {"pct": -15})[0]
    assert not validate_action("adjust_price", {"pct": 21})[0]
    assert not validate_action("adjust_price", {"pct": "nhiều lắm"})[0]


def test_validate_quest_whitelist():
    state = {"available_quests": ["find_ore"]}
    assert validate_action("start_quest", {"quest_id": "find_ore"}, state)[0]
    assert not validate_action("start_quest", {"quest_id": "give_all_gold"}, state)[0]
