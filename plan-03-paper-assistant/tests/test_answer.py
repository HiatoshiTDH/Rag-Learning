"""Offline tests for the generation layer: build request (pure), citation extraction, router."""

from types import SimpleNamespace

from src.answer import build_answer_request, extract_answer, route

SECTIONS = [
    {"paper_title": "Paper A", "section": "3. Method", "text": "AAA " * 50,
     "parent_section_id": "a#method", "paper_id": "a", "section_type": "method"},
    {"paper_title": "Paper B", "section": "4. Results", "text": "BBB " * 50,
     "parent_section_id": "b#results", "paper_id": "b", "section_type": "result"},
]


def test_build_request_document_blocks():
    req = build_answer_request("the question?", SECTIONS)
    content = req["messages"][0]["content"]
    docs = [b for b in content if b["type"] == "document"]
    assert len(docs) == 2
    assert all(b["citations"] == {"enabled": True} for b in docs)
    assert docs[0]["title"] == "Paper A — 3. Method"
    # The question is the last block
    assert content[-1] == {"type": "text", "text": "the question?"}


def test_build_request_prompt_caching_on_last_doc():
    """Task 5.3 — cache_control on the last document block, not any other."""
    req = build_answer_request("q", SECTIONS)
    docs = [b for b in req["messages"][0]["content"] if b["type"] == "document"]
    assert "cache_control" not in docs[0]
    assert docs[-1]["cache_control"] == {"type": "ephemeral"}


def test_extract_answer_numbers_citations():
    response = SimpleNamespace(content=[
        SimpleNamespace(type="text", text="Method X works as follows.", citations=[
            SimpleNamespace(document_title="Paper A — 3. Method", cited_text="X works by..."),
        ]),
        SimpleNamespace(type="text", text=" The result reaches 95%.", citations=[
            SimpleNamespace(document_title="Paper B — 4. Results", cited_text="95% accuracy"),
        ]),
    ])
    result = extract_answer(response)
    assert "[1]" in result["text"] and "[2]" in result["text"]
    assert [c["title"] for c in result["citations"]] == ["Paper A — 3. Method", "Paper B — 4. Results"]


def test_router_heuristics():
    known = ["2304.03442", "2308.00001"]
    # Vietnamese comparison phrasings are deliberate data — the router supports
    # questions asked in Vietnamese (see _COMPARE_WORDS in src/answer.py).
    assert route("so sánh 2304.03442 và 2308.00001", known)["kind"] == "compare"
    assert route("2304.03442 dùng phương pháp gì?", known)["kind"] == "single"
    assert route("các hướng tiếp cận memory retrieval?", known)["kind"] == "general"
    # A comparison word with no ids mentioned -> general (nothing to compare)
    assert route("so sánh các phương pháp", known)["kind"] == "general"
