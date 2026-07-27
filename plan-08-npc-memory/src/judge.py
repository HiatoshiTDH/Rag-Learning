"""LLM-as-judge cho test harness (README mục 7).

Assert kiểu "câu trả lời CÓ THỂ HIỆN việc nhớ X không?" — không so khớp
chuỗi cứng vì thoại LLM mỗi lần một khác. Test offline dùng ScriptedLLM;
bài test live (TEST_AT_HOME) dùng backend thật.
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
    """expectation ví dụ: 'NPC nhớ người chơi từng hứa mang thuốc'.

    Trả về {"remembers": bool, "reason": str}.
    """
    return llm.complete_json(
        f"Một NPC trong game trả lời người chơi như sau:\n\n"
        f"\"{reply}\"\n\n"
        f"Câu trả lời này có thể hiện điều sau không: {expectation}?\n"
        f"Chỉ xét nội dung câu trả lời, không suy diễn thêm.",
        model=model, schema=_JUDGE_SCHEMA,
    )
