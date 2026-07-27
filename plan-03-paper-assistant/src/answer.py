"""Tuần 2-3 — Generation với citations API của Claude.

Mỗi section retrieve được đưa vào như một `document` block với
citations bật -> response tự kèm citation có cấu trúc, không phải parse tay.
"""

MODEL = "claude-opus-5"


def answer(question: str, sections: list[dict]) -> dict:
    """TODO(tuần 2): gọi client.messages.create với content dạng:

    [
      {"type": "document",
       "source": {"type": "text", "media_type": "text/plain", "data": sec["text"]},
       "title": f'{sec["title"]} — {sec["section"]}',
       "citations": {"enabled": True}},
      ...,
      {"type": "text", "text": question},
    ]

    Trả về: {"text": ..., "citations": [...]} để render footnote/link.
    """
    raise NotImplementedError


def compare_papers(question: str, paper_ids: list[str]) -> dict:
    """TODO(tuần 3): map-reduce cho câu hỏi so sánh nhiều paper —
    retrieve + tóm tắt riêng từng paper (map), rồi một call tổng hợp (reduce)."""
    raise NotImplementedError
