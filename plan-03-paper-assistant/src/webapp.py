"""P5 (5.4) — UI web tối giản: hỏi đáp + so sánh paper trên trình duyệt.

Chạy:  uvicorn src.webapp:app --port 8090   ->  mở http://localhost:8090
Một trang HTML tĩnh (không CDN, tự chứa) + 3 API JSON mỏng bọc quanh answer.py.
"""

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from src.answer import answer as answer_fn
from src.answer import answer_stream as answer_stream_fn
from src.answer import compare_papers as compare_fn
from src.index import list_papers

app = FastAPI(title="paper-assistant-ui")

_STATIC = Path(__file__).parent / "static"


class AskIn(BaseModel):
    question: str
    paper_id: str = ""
    section_type: str = ""
    expand: bool = True
    language: str = ""      # "" -> None (dùng config.ANSWER_LANGUAGE) | "auto"/"en"/"vi"
    history: list[dict] = []  # [{"question", "answer"}] — hội thoại nhiều lượt


class CompareIn(BaseModel):
    question: str
    paper_ids: list[str]
    language: str = ""


def _ask_filters(body: AskIn) -> dict | None:
    filters = {}
    if body.paper_id:
        filters["paper_id"] = body.paper_id
    if body.section_type:
        filters["section_type"] = body.section_type
    return filters or None


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (_STATIC / "index.html").read_text()


@app.get("/api/papers")
def api_papers():
    return list_papers()


@app.post("/api/ask")
def api_ask(body: AskIn):
    result = answer_fn(body.question, filters=_ask_filters(body), expand=body.expand,
                       language=body.language or None, history=body.history or None)
    return {
        "text": result["text"],
        "citations": result["citations"],
        "usage": result.get("usage"),
        "sections": [
            {"title": f'{s["paper_title"]} — {s["section"]}'}
            for s in result.get("sections", [])
        ],
    }


@app.post("/api/ask_stream")
def api_ask_stream(body: AskIn):
    """SSE: event delta (từng mẩu text) rồi event done (text chốt + citations + usage).

    UI hiển thị delta chạy dần, khi done thì thay bằng bản text đã gắn số citation.
    """
    def gen():
        for event in answer_stream_fn(body.question, filters=_ask_filters(body),
                                      expand=body.expand, language=body.language or None,
                                      history=body.history or None):
            if event["type"] == "done":  # sections không cần cho UI, giữ payload gọn
                event = {k: v for k, v in event.items() if k != "sections"}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/compare")
def api_compare(body: CompareIn):
    result = compare_fn(body.question, body.paper_ids, language=body.language or None)
    return {"text": result["text"], "per_paper": result.get("per_paper", [])}
