"""Test UI web (5.4) — TestClient + mock answer/compare, không gọi LLM thật."""

import pytest
from fastapi.testclient import TestClient

from src import webapp


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(webapp, "list_papers", lambda: [
        {"paper_id": "2304.03442", "title": "Generative Agents", "year": 2023},
    ])
    monkeypatch.setattr(webapp, "answer_fn", lambda q, filters=None, expand=True: {
        "text": f"trả lời cho: {q}",
        "citations": [{"n": 1, "title": "Generative Agents — 3. Method"}],
        "sections": [{"paper_title": "Generative Agents", "section": "3. Method",
                      "text": "...", "parent_section_id": "x", "paper_id": "2304.03442",
                      "section_type": "method"}],
        "_filters": filters,
    })
    monkeypatch.setattr(webapp, "compare_fn", lambda q, ids: {
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
                        lambda q, filters=None, expand=True:
                        captured.update(filters=filters, expand=expand) or
                        {"text": "ok", "citations": [], "sections": []})
    r = client.post("/api/ask", json={"question": "q?", "paper_id": "2304.03442",
                                      "section_type": "method", "expand": False})
    assert r.status_code == 200
    assert set(r.json()) == {"text", "citations", "sections"}
    assert captured["filters"] == {"paper_id": "2304.03442", "section_type": "method"}
    assert captured["expand"] is False


def test_api_ask_no_filters_passes_none(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(webapp, "answer_fn",
                        lambda q, filters=None, expand=True:
                        captured.update(filters=filters) or
                        {"text": "ok", "citations": [], "sections": []})
    client.post("/api/ask", json={"question": "q?"})
    assert captured["filters"] is None


def test_api_compare(client):
    r = client.post("/api/compare",
                    json={"question": "khác gì?", "paper_ids": ["a", "b"]})
    assert r.status_code == 200 and r.json()["text"] == "so sánh 2 paper"
