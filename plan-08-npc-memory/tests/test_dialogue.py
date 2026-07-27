"""Unit tests for the dialogue composer (week 3): prompt caching +
anti-injection, streaming, canned fallback, and server-side game-action
validation."""

from src.dialogue import (CANNED_FALLBACK, GAME_ACTION_TOOLS, build_system_prompt,
                          compose_user_message, respond, validate_action)
from src.llm import ScriptedLLM
from src.memory_store import MemoryRecord

PERSONA = "Blacksmith Tom: gruff but kind-hearted."


def _memory(text: str) -> MemoryRecord:
    return MemoryRecord.new("blacksmith_tom", "observation", text, 5)


# ------------------------------------------------------------ system prompt

def test_system_prompt_persona_first_cache_control_last():
    blocks = build_system_prompt(PERSONA)
    assert PERSONA in blocks[0]["text"]
    # cache_control on the LAST block -> caches persona + rules together (README 5.1)
    assert blocks[-1]["cache_control"] == {"type": "ephemeral"}
    rules = blocks[-1]["text"]
    assert "propose_game_action" in rules          # gameplay only through the tool
    assert "NOT commands" in rules                 # untrusted input
    assert "prompt" in rules                       # never reveal the prompt


def test_user_message_wraps_untrusted_input():
    msg = compose_user_message("hello there", [_memory("Akira once gave me flowers")],
                               situation="morning at the market", relationship="warm")
    assert "<player_utterance>\nhello there\n</player_utterance>" in msg
    assert "Akira once gave me flowers" in msg
    assert "morning at the market" in msg and "warm" in msg


# ----------------------------------------------------------------- respond

def test_respond_streams_text_with_tools_declared():
    llm = ScriptedLLM(["Hello Akira, it has been a while."])
    events = list(respond("tom", "hello there", [], persona=PERSONA, llm=llm))
    text = "".join(e["text"] for e in events if e["type"] == "text")
    assert text == "Hello Akira, it has been a while."
    assert len([e for e in events if e["type"] == "text"]) > 1  # streamed chunk by chunk
    assert llm.calls[0]["tools"] == GAME_ACTION_TOOLS


def test_timeout_falls_back_to_canned_line_by_relationship():
    llm = ScriptedLLM([TimeoutError("API too slow")])
    events = list(respond("tom", "hello", [], persona=PERSONA,
                          relationship="hostile", llm=llm))
    assert events[0]["text"] == CANNED_FALLBACK["hostile"]
    assert events[-1]["type"] == "fallback"


def test_no_llm_configured_still_answers():
    """LLM_BACKEND=none / total network loss -> the NPC still never freezes."""
    events = list(respond("tom", "hello", [], persona=PERSONA, llm=None))
    assert events[-1]["type"] == "fallback"
    assert events[0]["text"] == CANNED_FALLBACK["neutral"]


def test_accepted_action_passes_validation():
    llm = ScriptedLLM([{
        "text": "Take this bouquet.",
        "tool_calls": [{"name": "propose_game_action",
                        "input": {"action": "give_item", "params": {"item": "wildflowers"}}}],
    }])
    events = list(respond("tom", "do you have anything for me?", [], persona=PERSONA,
                          llm=llm, game_state={"giftable_items": ["wildflowers"]}))
    actions = [e for e in events if e["type"] == "action"]
    assert actions == [{"type": "action", "action": "give_item",
                        "params": {"item": "wildflowers"}, "accepted": True, "reason": "ok"}]


# --------------------------------------------------------- validate_action

def test_validate_deny_by_default():
    # game_state declares nothing -> everything is blocked (secure default)
    assert validate_action("give_item", {"item": "gold"}) == (
        False, "item 'gold' is not in the giftable list")
    assert not validate_action("start_quest", {"quest_id": "q1"})[0]
    assert not validate_action("open_admin_panel", {})[0]


def test_validate_price_bounds():
    assert validate_action("adjust_price", {"pct": 20})[0]
    assert validate_action("adjust_price", {"pct": -15})[0]
    assert not validate_action("adjust_price", {"pct": 21})[0]
    assert not validate_action("adjust_price", {"pct": "a lot"})[0]


def test_validate_quest_whitelist():
    state = {"available_quests": ["find_ore"]}
    assert validate_action("start_quest", {"quest_id": "find_ore"}, state)[0]
    assert not validate_action("start_quest", {"quest_id": "give_all_gold"}, state)[0]
