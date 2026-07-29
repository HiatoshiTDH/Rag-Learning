"""P2 (2.2) + P4 (4.2, 4.3) — Generation với citations API của Claude.

Mỗi section retrieve được đưa vào như một `document` block với citations bật
-> response kèm citation có cấu trúc (đúng document, đúng đoạn), không parse tay.

build_answer_request() là hàm thuần (không gọi mạng) để test offline cấu trúc request.
"""

import re

from src import config
from src.query import retrieve

SYSTEM_PROMPT = """Bạn là trợ lý nghiên cứu, trả lời DỰA HOÀN TOÀN trên các tài liệu được cung cấp.
Quy tắc:
- Chỉ nói những gì có căn cứ trong tài liệu. Không đủ căn cứ thì nói rõ "các paper trong kho không đề cập".
- Trả lời bằng đúng ngôn ngữ của câu hỏi.
- Khi nêu phương pháp/số liệu, luôn gắn với paper cụ thể (citations sẽ tự đính kèm)."""


# ----------------------------------------------------- build request (thuần)

def build_answer_request(question: str, sections: list[dict],
                         model: str | None = None, max_tokens: int = 4096) -> dict:
    """Dựng request Messages API — tách riêng để test không cần gọi mạng.

    Prompt caching (task 5.3): cache_control đặt trên document block CUỐI —
    hỏi nhiều câu trên cùng bộ section (hội thoại đào sâu 1 paper) chỉ trả
    ~10% giá cho phần tài liệu từ request thứ 2.
    """
    content: list[dict] = []
    for i, sec in enumerate(sections):
        block = {
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": sec["text"]},
            "title": f'{sec["paper_title"]} — {sec["section"]}',
            "citations": {"enabled": True},
        }
        if i == len(sections) - 1:
            block["cache_control"] = {"type": "ephemeral"}
        content.append(block)
    content.append({"type": "text", "text": question})

    return {
        "model": model or config.ANSWER_MODEL,
        "max_tokens": max_tokens,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": content}],
    }


def extract_answer(response) -> dict:
    """Response -> {"text", "citations": [{"title", "cited_text"}]}.

    Với citations bật, text bị chia thành nhiều block; block nào có căn cứ
    mang mảng .citations. Đánh số [n] theo document title xuất hiện.
    """
    text_parts: list[str] = []
    citations: list[dict] = []
    title_no: dict[str, int] = {}

    for block in response.content:
        if getattr(block, "type", None) != "text":
            continue
        part = block.text
        for cit in (getattr(block, "citations", None) or []):
            title = getattr(cit, "document_title", "") or ""
            if title not in title_no:
                title_no[title] = len(title_no) + 1
                citations.append({
                    "n": title_no[title],
                    "title": title,
                    "cited_text": (getattr(cit, "cited_text", "") or "")[:200],
                })
            part += f" [{title_no[title]}]"
        text_parts.append(part)

    return {"text": "".join(text_parts), "citations": citations}


def format_answer(result: dict) -> str:
    """Render ra text cho CLI: câu trả lời + danh mục nguồn."""
    out = result["text"]
    if result["citations"]:
        out += "\n\nNguồn:\n" + "\n".join(
            f'  [{c["n"]}] {c["title"]}' for c in result["citations"]
        )
    return out


# ---------------------------- generic path (LLM_BACKEND=openai_compat, thuần)

_GENERIC_PROMPT = """Trả lời câu hỏi CHỈ dựa trên các nguồn được đánh số dưới đây.
Sau mỗi ý lấy từ nguồn nào, ghi số nguồn dạng [1], [2]... Không đủ căn cứ thì nói rõ.
Trả lời bằng đúng ngôn ngữ của câu hỏi.

{sources}

Câu hỏi: {question}"""


def build_generic_prompt(question: str, sections: list[dict]) -> str:
    """Citation qua prompt — cho model không có citations API (Ollama/Groq/Gemini...).

    Kém tin cậy hơn citations API của Claude (model có thể ghi nhầm số) —
    đó là trade-off đã chấp nhận khi chạy local/free, xem SETUP.md.
    """
    sources = "\n\n".join(
        f'[{i + 1}] {sec["paper_title"]} — {sec["section"]}\n{sec["text"]}'
        for i, sec in enumerate(sections)
    )
    return _GENERIC_PROMPT.format(sources=sources, question=question)


def extract_generic_citations(text: str, sections: list[dict]) -> dict:
    """Gom các [n] model đã ghi trong câu trả lời -> danh mục nguồn tương ứng."""
    used = sorted({int(m) for m in re.findall(r"\[(\d+)\]", text)})
    citations = [
        {"n": n, "title": f'{sections[n - 1]["paper_title"]} — {sections[n - 1]["section"]}'}
        for n in used
        if 1 <= n <= len(sections)
    ]
    return {"text": text, "citations": citations}


# ------------------------------------------------------------ gọi API (2.2)

def answer(question: str, filters: dict | None = None, **retrieve_kwargs) -> dict:
    """Câu hỏi thường: retrieve -> 1 call LLM.

    - LLM_BACKEND=anthropic:     citations API (có cấu trúc, tin cậy).
    - LLM_BACKEND=openai_compat: citation qua prompt đánh số nguồn.
    """
    sections = retrieve(question, filters=filters, **retrieve_kwargs)
    if not sections:
        return {"text": "Không tìm thấy đoạn nào liên quan trong kho paper.", "citations": []}

    if config.LLM_BACKEND == "openai_compat":
        from src.llm import complete

        text = complete(build_generic_prompt(question, sections),
                        model=config.ANSWER_MODEL, max_tokens=2048, system=SYSTEM_PROMPT)
        result = extract_generic_citations(text, sections)
    else:
        import anthropic

        request = build_answer_request(question, sections)
        response = anthropic.Anthropic().messages.create(**request)
        result = extract_answer(response)

    result["sections"] = sections
    return result


# ------------------------------------------------- so sánh nhiều paper (4.2)

_MAP_PROMPT = """Dựa trên các trích đoạn từ paper "{title}", tóm tắt góc nhìn của paper này
cho câu hỏi sau (3-5 gạch đầu dòng, chỉ dùng thông tin trong trích đoạn):

{question}"""

_REDUCE_PROMPT = """Câu hỏi so sánh: {question}

Tóm tắt góc nhìn của từng paper:

{summaries}

So sánh trực tiếp các paper trên theo câu hỏi. Trình bày điểm giống, điểm khác,
và điều kiện áp dụng của mỗi cách tiếp cận. Trả lời bằng ngôn ngữ của câu hỏi."""


def compare_papers(question: str, paper_ids: list[str], llm=None, **retrieve_kwargs) -> dict:
    """Map-reduce: retrieve + tóm tắt riêng từng paper (map) -> 1 call tổng hợp (reduce)."""
    if llm is None:
        from src.llm import complete

        def llm(prompt: str, max_tokens: int = 1500) -> str:
            return complete(prompt, model=config.ANSWER_MODEL, max_tokens=max_tokens,
                            system=SYSTEM_PROMPT)

    summaries = []
    for pid in paper_ids:
        sections = retrieve(question, filters={"paper_id": pid}, top_k=5, **retrieve_kwargs)
        if not sections:
            summaries.append(f"### {pid}\n(không tìm thấy đoạn liên quan)")
            continue
        title = sections[0]["paper_title"]
        excerpt = "\n\n".join(s["text"][:3000] for s in sections)
        summary = llm(_MAP_PROMPT.format(title=title, question=question) + "\n\n" + excerpt)
        summaries.append(f"### {title} ({pid})\n{summary}")

    text = llm(_REDUCE_PROMPT.format(question=question, summaries="\n\n".join(summaries)))
    return {"text": text, "citations": [], "per_paper": summaries}


# ------------------------------------------------------------- router (4.3)

_COMPARE_WORDS = re.compile(r"\b(so sánh|khác nhau|khác gì|compare|versus|vs\.?|difference)\b", re.I)


def route(question: str, known_paper_ids: list[str]) -> dict:
    """Heuristic v1: câu hỏi thuộc loại nào?

    - "compare": nhắc >=2 paper_id, hoặc có từ so sánh + >=1 id
    - "single":  nhắc đúng 1 paper_id -> filter paper đó
    - "general": còn lại -> search toàn kho
    """
    mentioned = [pid for pid in known_paper_ids if pid in question]
    if len(mentioned) >= 2:
        return {"kind": "compare", "paper_ids": mentioned}
    if _COMPARE_WORDS.search(question) and len(mentioned) >= 1:
        return {"kind": "compare", "paper_ids": mentioned}
    if len(mentioned) == 1:
        return {"kind": "single", "paper_ids": mentioned}
    return {"kind": "general", "paper_ids": []}
