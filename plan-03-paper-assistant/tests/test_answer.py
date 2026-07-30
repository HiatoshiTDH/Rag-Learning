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


def test_router_heuristics():
    known = ["2304.03442", "2308.00001"]
    assert route("so sánh 2304.03442 và 2308.00001", known)["kind"] == "compare"
    assert route("2304.03442 dùng phương pháp gì?", known)["kind"] == "single"
    assert route("các hướng tiếp cận memory retrieval?", known)["kind"] == "general"
    # Từ 'so sánh' nhưng không nêu id nào -> general (không có gì để compare)
    assert route("so sánh các phương pháp", known)["kind"] == "general"
