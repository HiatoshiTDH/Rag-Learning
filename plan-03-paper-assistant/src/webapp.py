"""P5 (5.4) — UI web tối giản: hỏi đáp + so sánh paper trên trình duyệt.

Chạy:  uvicorn src.webapp:app --port 8090   ->  mở http://localhost:8090
Một trang HTML tĩnh (không CDN, tự chứa) + 3 API JSON mỏng bọc quanh answer.py.
"""

import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from src.answer import answer as answer_fn
from src.answer import answer_stream as answer_stream_fn
from src.answer import compare_papers as compare_fn
from src.index import list_papers
from src.ingest import add_local_pdf
from src.ingest_all import ingest_one
from src.settings import apply_settings, get_settings, test_connection

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


@app.get("/api/status")
def api_status():
    """Chip trạng thái trên header UI: backend nào đang chạy, bao nhiêu paper."""
    from src import config

    model = (config.OPENAI_COMPAT_MODEL if config.LLM_BACKEND == "openai_compat"
             else config.ANSWER_MODEL)
    return {
        "llm_backend": config.LLM_BACKEND,
        "answer_model": model,
        "embed_backend": config.EMBED_BACKEND,
        "rerank_backend": config.RERANK_BACKEND,
        "papers": len(list_papers()),
        "demo": False,
    }


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


@app.post("/api/upload")
def api_upload(file: UploadFile):
    """Upload PDF từ trình duyệt -> add_local_pdf -> parse GROBID + index luôn.

    Đồng bộ (chờ GROBID parse xong, ~10-30s) — UI hiển thị trạng thái chờ.
    """
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Chỉ nhận file .pdf")
    # Ghi ra file tạm GIỮ NGUYÊN tên gốc (paper_id dẫn xuất từ tên file)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_pdf = Path(tmp) / Path(file.filename).name
        tmp_pdf.write_bytes(file.file.read())
        paper_id = add_local_pdf(tmp_pdf)
    try:
        from src.embedding import get_embedder
        from src.index import get_qdrant

        chunks = ingest_one(paper_id, get_embedder(), get_qdrant())
    except Exception as e:
        raise HTTPException(
            502, f"Đã nhận PDF ({paper_id}) nhưng index lỗi: {e}. "
                 f"GROBID đã chạy chưa? (docker compose up -d)")
    return {"paper_id": paper_id, "chunks": chunks}


@app.get("/api/settings")
def api_settings_get():
    return get_settings()


@app.post("/api/settings")
def api_settings_post(body: dict):
    try:
        return apply_settings(body)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/settings/test")
def api_settings_test():
    return test_connection()
