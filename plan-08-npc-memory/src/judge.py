"""LLM-as-judge for the test harness (README section 7).

Assertions like "does the reply SHOW the NPC remembers X?" — no hard string
matching, since LLM dialogue differs every run. Offline tests use ScriptedLLM;
the live suite (TEST_AT_HOME) uses the real backend.
"""

from src import config
from src.llm import LLM

_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "remembers": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["remembers", "reason"],
    "additionalProperties": False,
}


def judge_remembers(reply: str, expectation: str, llm: LLM,
                    model: str = config.SCORING_MODEL) -> dict:
    """expectation example: 'the NPC remembers the player promised to bring medicine'.

    Returns {"remembers": bool, "reason": str}.
    """
    return llm.complete_json(
        f"A game NPC replied to a player as follows:\n\n"
        f"\"{reply}\"\n\n"
        f"Does this reply show the following: {expectation}?\n"
        f"Judge only the reply's content; do not extrapolate.",
        model=model, schema=_JUDGE_SCHEMA,
    )
