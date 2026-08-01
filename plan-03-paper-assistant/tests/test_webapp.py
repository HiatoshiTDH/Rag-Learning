"""Test UI web (5.4) — TestClient + mock answer/compare, không gọi LLM thật."""

import pytest
from fastapi.testclient import TestClient

from src import webapp


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(webapp, "list_papers", lambda: [
        {"paper_id": "2304.03442", "title": "Generative Agents", "year": 2023},
    ])
    monkeypatch.setattr(webapp, "answer_fn",
                        lambda q, filters=None, expand=True, language=None, history=None: {
        "text": f"trả lời cho: {q}",
        "citations": [{"n": 1, "title": "Generative Agents — 3. Method"}],
        "usage": {"input_tokens": 100, "output_tokens": 50,
                  "cache_read_input_tokens": 0, "cost_usd": 0.002},
        "sections": [{"paper_title": "Generative Agents", "section": "3. Method",
                      "text": "...", "parent_section_id": "x", "paper_id": "2304.03442",
                      "section_type": "method"}],
        "_filters": filters,
    })
    monkeypatch.setattr(webapp, "compare_fn", lambda q, ids, language=None: {
        "text": f"so sánh {len(ids)} paper", "per_paper": ["### A", "### B"],
    })
    return TestClient(webapp.app)


def test_home_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Paper Assistant" in r.text and "/api/ask" in r.text


def test_api_papers(client):
    assert client.get("/api/papers").json()[0]["paper_id"] == "2304.03442"


def test_api_ask_shape_and_filters(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(webapp, "answer_fn",
                        lambda q, filters=None, expand=True, language=None, history=None:
                        captured.update(filters=filters, expand=expand) or
                        {"text": "ok", "citations": [], "sections": []})
    r = client.post("/api/ask", json={"question": "q?", "paper_id": "2304.03442",
                                      "section_type": "method", "expand": False})
    assert r.status_code == 200
    assert set(r.json()) == {"text", "citations", "usage", "sections"}
    assert captured["filters"] == {"paper_id": "2304.03442", "section_type": "method"}
    assert captured["expand"] is False


def test_api_ask_no_filters_passes_none(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(webapp, "answer_fn",
                        lambda q, filters=None, expand=True, language=None, history=None:
                        captured.update(filters=filters) or
                        {"text": "ok", "citations": [], "sections": []})
    client.post("/api/ask", json={"question": "q?"})
    assert captured["filters"] is None


def test_api_ask_language_param_forwarded(client, monkeypatch):
    """Hỏi tiếng Việt nhưng chọn language=en -> phải truyền tới answer_fn."""
    captured = {}
    monkeypatch.setattr(webapp, "answer_fn",
                        lambda q, filters=None, expand=True, language=None, history=None:
                        captured.update(language=language) or
                        {"text": "ok", "citations": [], "sections": []})
    client.post("/api/ask", json={"question": "Paper này nói gì?", "language": "en"})
    assert captured["language"] == "en"


def test_api_ask_empty_language_becomes_none(client, monkeypatch):
    """Không chọn gì ở dropdown ("") -> None, để answer() dùng config.ANSWER_LANGUAGE."""
    captured = {}
    monkeypatch.setattr(webapp, "answer_fn",
                        lambda q, filters=None, expand=True, language=None, history=None:
                        captured.update(language=language) or
                        {"text": "ok", "citations": [], "sections": []})
    client.post("/api/ask", json={"question": "q?"})
    assert captured["language"] is None


def test_api_compare(client):
    r = client.post("/api/compare",
                    json={"question": "khác gì?", "paper_ids": ["a", "b"]})
    assert r.status_code == 200 and r.json()["text"] == "so sánh 2 paper"


def test_api_compare_language_forwarded(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(webapp, "compare_fn",
                        lambda q, ids, language=None:
                        captured.update(language=language) or {"text": "ok", "per_paper": []})
    client.post("/api/compare", json={"question": "q?", "paper_ids": ["a", "b"], "language": "vi"})
    assert captured["language"] == "vi"


def test_api_ask_history_forwarded(client, monkeypatch):
    """Hội thoại nhiều lượt: history từ UI phải tới answer_fn nguyên vẹn."""
    captured = {}
    monkeypatch.setattr(webapp, "answer_fn",
                        lambda q, filters=None, expand=True, language=None, history=None:
                        captured.update(history=history) or
                        {"text": "ok", "citations": [], "sections": []})
    hist = [{"question": "paper nói gì?", "answer": "nói về memory."}]
    client.post("/api/ask", json={"question": "còn hạn chế thì sao?", "history": hist})
    assert captured["history"] == hist


def test_api_ask_empty_history_becomes_none(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(webapp, "answer_fn",
                        lambda q, filters=None, expand=True, language=None, history=None:
                        captured.update(history=history) or
                        {"text": "ok", "citations": [], "sections": []})
    client.post("/api/ask", json={"question": "q?"})
    assert captured["history"] is None


def test_api_ask_stream_sse(client, monkeypatch):
    """Endpoint streaming: các event delta rồi done, đúng định dạng SSE data: {json}."""
    def fake_stream(q, filters=None, expand=True, language=None, history=None):
        yield {"type": "delta", "text": "Phương pháp "}
        yield {"type": "delta", "text": "X hoạt động..."}
        yield {"type": "done", "text": "Phương pháp X hoạt động... [1]",
               "citations": [{"n": 1, "title": "Paper A — Method"}],
               "usage": {"input_tokens": 10, "output_tokens": 5,
                         "cache_read_input_tokens": 0, "cost_usd": 0.001}}
    monkeypatch.setattr(webapp, "answer_stream_fn", fake_stream)

    r = client.post("/api/ask_stream", json={"question": "q?"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = [l for l in r.text.split("\n\n") if l.startswith("data: ")]
    assert len(events) == 3
    import json as _json
    parsed = [_json.loads(e[6:]) for e in events]
    assert [p["type"] for p in parsed] == ["delta", "delta", "done"]
    assert parsed[-1]["citations"][0]["n"] == 1
    assert parsed[-1]["usage"]["cost_usd"] == 0.001
