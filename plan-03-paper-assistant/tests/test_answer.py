"""Test offline cho tầng generation: build request (thuần), extract citations, router."""

from types import SimpleNamespace

import pytest

from src.answer import build_answer_request, extract_answer, route, system_prompt

SECTIONS = [
    {"paper_title": "Paper A", "section": "3. Method", "text": "AAA " * 50,
     "parent_section_id": "a#method", "paper_id": "a", "section_type": "method"},
    {"paper_title": "Paper B", "section": "4. Results", "text": "BBB " * 50,
     "parent_section_id": "b#results", "paper_id": "b", "section_type": "result"},
]


def test_build_request_document_blocks():
    req = build_answer_request("câu hỏi?", SECTIONS)
    content = req["messages"][0]["content"]
    docs = [b for b in content if b["type"] == "document"]
    assert len(docs) == 2
    assert all(b["citations"] == {"enabled": True} for b in docs)
    assert docs[0]["title"] == "Paper A — 3. Method"
    # Câu hỏi là block cuối cùng
    assert content[-1] == {"type": "text", "text": "câu hỏi?"}


def test_build_request_prompt_caching_on_last_doc():
    """Task 5.3 — cache_control trên document block cuối, không phải block khác."""
    req = build_answer_request("q", SECTIONS)
    docs = [b for b in req["messages"][0]["content"] if b["type"] == "document"]
    assert "cache_control" not in docs[0]
    assert docs[-1]["cache_control"] == {"type": "ephemeral"}


def test_extract_answer_numbers_citations():
    response = SimpleNamespace(content=[
        SimpleNamespace(type="text", text="Phương pháp X hoạt động như sau.", citations=[
            SimpleNamespace(document_title="Paper A — 3. Method", cited_text="X works by..."),
        ]),
        SimpleNamespace(type="text", text=" Kết quả đạt 95%.", citations=[
            SimpleNamespace(document_title="Paper B — 4. Results", cited_text="95% accuracy"),
        ]),
    ])
    result = extract_answer(response)
    assert "[1]" in result["text"] and "[2]" in result["text"]
    assert [c["title"] for c in result["citations"]] == ["Paper A — 3. Method", "Paper B — 4. Results"]


def test_build_generic_prompt_numbers_sources():
    from src.answer import build_generic_prompt

    prompt = build_generic_prompt("câu hỏi?", SECTIONS)
    assert "[1] Paper A — 3. Method" in prompt
    assert "[2] Paper B — 4. Results" in prompt
    assert prompt.rstrip().endswith("Câu hỏi: câu hỏi?")


def test_extract_generic_citations():
    from src.answer import extract_generic_citations

    result = extract_generic_citations(
        "Phương pháp X [1] đạt 95% [2]. Số lạc loài [9] phải bị bỏ qua.", SECTIONS
    )
    assert [c["n"] for c in result["citations"]] == [1, 2]
    assert result["citations"][0]["title"] == "Paper A — 3. Method"


# --------------------------------------------------- ngôn ngữ trả lời (language)

def test_system_prompt_default_matches_question_language():
    assert "ngôn ngữ của câu hỏi" in system_prompt("auto")


def test_system_prompt_en_forces_english_regardless_of_question():
    text = system_prompt("en")
    assert "tiếng Anh" in text and "BẤT KỂ" in text


def test_system_prompt_vi_forces_vietnamese():
    text = system_prompt("vi")
    assert "tiếng Việt" in text and "BẤT KỂ" in text


def test_system_prompt_invalid_language_raises():
    with pytest.raises(ValueError):
        system_prompt("fr")


def test_build_answer_request_hoi_tieng_viet_tra_loi_tieng_anh():
    """Kịch bản người dùng: hỏi tiếng Việt, muốn nhận lại tiếng Anh."""
    req = build_answer_request("Paper này giải quyết vấn đề gì?", SECTIONS, language="en")
    assert "tiếng Anh" in req["system"] and "BẤT KỂ" in req["system"]


def test_build_generic_prompt_language_en():
    from src.answer import build_generic_prompt

    prompt = build_generic_prompt("câu hỏi tiếng Việt?", SECTIONS, language="en")
    assert "tiếng Anh" in prompt


# ------------------------------------------------ hội thoại nhiều lượt (history)

def test_rewrite_followup_no_history_is_passthrough():
    from src.answer import rewrite_followup

    calls = []
    q = rewrite_followup("câu hỏi độc lập?", None, llm=lambda p: calls.append(p) or "x")
    assert q == "câu hỏi độc lập?" and calls == []   # không history -> không tốn call nào


def test_rewrite_followup_uses_history():
    from src.answer import rewrite_followup

    seen = {}
    def llm(prompt):
        seen["prompt"] = prompt
        return "Hạn chế của phương pháp memory stream trong Generative Agents là gì?"

    out = rewrite_followup("còn hạn chế thì sao?",
                           [{"question": "Generative Agents dùng memory thế nào?",
                             "answer": "Dùng memory stream..."}], llm=llm)
    assert "Generative Agents" in out
    assert "memory stream" in seen["prompt"]         # history có mặt trong prompt rewrite


def test_build_answer_request_with_history_turns():
    req = build_answer_request("câu tiếp?", SECTIONS,
                               history=[{"question": "câu 1?", "answer": "trả lời 1"}])
    msgs = req["messages"]
    assert len(msgs) == 3
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == "câu 1?" and msgs[1]["content"] == "trả lời 1"
    # Lượt cuối vẫn là documents + câu hỏi hiện tại
    assert msgs[2]["content"][-1] == {"type": "text", "text": "câu tiếp?"}


def test_build_generic_prompt_with_history():
    from src.answer import build_generic_prompt

    prompt = build_generic_prompt("còn X?", SECTIONS,
                                  history=[{"question": "q1", "answer": "a1"}])
    assert "Hội thoại trước" in prompt and "q1" in prompt


# --------------------------------------------------------- usage & chi phí

def test_usage_from_response_with_cost():
    from src.answer import usage_from_response

    resp = SimpleNamespace(usage=SimpleNamespace(
        input_tokens=10_000, output_tokens=1_000, cache_read_input_tokens=50_000))
    u = usage_from_response(resp, "claude-opus-5")
    # 10K*$5/M + 50K*$0.5/M + 1K*$25/M = 0.05 + 0.025 + 0.025 = 0.1
    assert u["cost_usd"] == 0.1


def test_usage_from_response_unknown_model_no_cost():
    from src.answer import usage_from_response

    resp = SimpleNamespace(usage=SimpleNamespace(
        input_tokens=10, output_tokens=5, cache_read_input_tokens=0))
    u = usage_from_response(resp, "qwen2.5:14b")
    assert u["cost_usd"] is None and u["input_tokens"] == 10


def test_format_answer_shows_usage():
    from src.answer import format_answer

    out = format_answer({"text": "x", "citations": [],
                         "usage": {"input_tokens": 12345, "output_tokens": 678,
                                   "cache_read_input_tokens": 0, "cost_usd": 0.0789}})
    assert "12,345 in" in out and "$0.0789" in out


# --------------------------------------------------------------- answer_stream

def test_answer_stream_fallback_backend(monkeypatch):
    """Backend không phải anthropic: 1 delta trọn gói + 1 done, citations vẫn có."""
    import src.answer as m
    from src import config

    monkeypatch.setattr(config, "LLM_BACKEND", "openai_compat")
    monkeypatch.setattr(m, "retrieve", lambda *a, **k: SECTIONS)
    monkeypatch.setattr("src.llm.complete",
                        lambda *a, **k: "Phương pháp X [1] cho kết quả [2].")

    events = list(m.answer_stream("hỏi gì đó?"))
    assert [e["type"] for e in events] == ["delta", "done"]
    assert events[-1]["citations"] and events[-1]["usage"] is None


def test_answer_stream_empty_retrieval(monkeypatch):
    import src.answer as m

    monkeypatch.setattr(m, "retrieve", lambda *a, **k: [])
    events = list(m.answer_stream("hỏi gì đó?"))
    assert len(events) == 1 and events[0]["type"] == "done"


def test_router_heuristics():
    known = ["2304.03442", "2308.00001"]
    assert route("so sánh 2304.03442 và 2308.00001", known)["kind"] == "compare"
    assert route("2304.03442 dùng phương pháp gì?", known)["kind"] == "single"
    assert route("các hướng tiếp cận memory retrieval?", known)["kind"] == "general"
    # Từ 'so sánh' nhưng không nêu id nào -> general (không có gì để compare)
    assert route("so sánh các phương pháp", known)["kind"] == "general"
