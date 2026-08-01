"""P2 (2.2) + P4 (4.2, 4.3) — Generation với citations API của Claude.

Mỗi section retrieve được đưa vào như một `document` block với citations bật
-> response kèm citation có cấu trúc (đúng document, đúng đoạn), không parse tay.

build_answer_request() là hàm thuần (không gọi mạng) để test offline cấu trúc request.
"""

import re

from src import config
from src.query import retrieve

# Ngôn ngữ TRẢ LỜI tách biệt với ngôn ngữ CÂU HỎI (config.ANSWER_LANGUAGE hoặc
# tham số `language` truyền tay — VD: hỏi tiếng Việt, muốn nhận lại tiếng Anh
# để giữ thuật ngữ chuẩn xác cho việc viết paper/proposal).
_LANGUAGE_INSTRUCTIONS = {
    "auto": "Trả lời bằng đúng ngôn ngữ của câu hỏi.",
    "en": ("Luôn trả lời bằng tiếng Anh (English), BẤT KỂ câu hỏi được hỏi bằng "
          "tiếng Việt hay ngôn ngữ nào khác. Giữ nguyên thuật ngữ kỹ thuật gốc, "
          "không dịch ngược lại tiếng Việt."),
    "vi": "Luôn trả lời bằng tiếng Việt, BẤT KỂ câu hỏi được hỏi bằng tiếng Anh hay ngôn ngữ nào khác.",
}


def _language_instruction(language: str | None) -> str:
    language = language or config.ANSWER_LANGUAGE
    if language not in _LANGUAGE_INSTRUCTIONS:
        raise ValueError(f"language không hợp lệ: {language!r} (auto | en | vi)")
    return _LANGUAGE_INSTRUCTIONS[language]


def system_prompt(language: str | None = None) -> str:
    """`language`: None -> dùng config.ANSWER_LANGUAGE; hoặc truyền tay "auto"/"en"/"vi"."""
    return f"""Bạn là trợ lý nghiên cứu, trả lời DỰA HOÀN TOÀN trên các tài liệu được cung cấp.
Quy tắc:
- Chỉ nói những gì có căn cứ trong tài liệu. Không đủ căn cứ thì nói rõ "các paper trong kho không đề cập".
- {_language_instruction(language)}
- Khi nêu phương pháp/số liệu, luôn gắn với paper cụ thể (citations sẽ tự đính kèm)."""


# ------------------------------------------- hội thoại nhiều lượt (follow-up)

_REWRITE_PROMPT = """Dưới đây là hội thoại đang diễn ra với trợ lý nghiên cứu và câu hỏi tiếp theo.
Viết lại câu hỏi tiếp theo thành MỘT câu hỏi độc lập, tự chứa đầy đủ ngữ cảnh
(thay mọi tham chiếu như "nó", "paper đó", "phương pháp này" bằng tên cụ thể).
Giữ nguyên ngôn ngữ của câu hỏi. Chỉ in ra câu hỏi đã viết lại, không giải thích.

Hội thoại:
{history}

Câu hỏi tiếp theo: {question}"""


def rewrite_followup(question: str, history: list[dict] | None, llm=None) -> str:
    """Câu hỏi phụ thuộc ngữ cảnh ("còn về X thì sao?") -> câu độc lập để RETRIEVAL
    tìm đúng đoạn. Chỉ tốn 1 call model rẻ (EXPAND_MODEL) và chỉ khi có history.

    Câu hỏi gốc vẫn được giữ trong messages gửi model trả lời — bản viết lại
    chỉ phục vụ tầng tìm kiếm.
    """
    if not history:
        return question
    if llm is None:
        from src.llm import complete

        def llm(prompt: str) -> str:
            return complete(prompt, model=config.EXPAND_MODEL, max_tokens=200)

    hist_text = "\n".join(
        f'Người dùng: {h["question"]}\nTrợ lý: {h["answer"][:500]}'
        for h in history[-3:]  # 3 lượt gần nhất là đủ ngữ cảnh
    )
    rewritten = llm(_REWRITE_PROMPT.format(history=hist_text, question=question)).strip()
    return rewritten or question


# ----------------------------------------------------- build request (thuần)

def build_answer_request(question: str, sections: list[dict],
                         model: str | None = None, max_tokens: int = 4096,
                         language: str | None = None,
                         history: list[dict] | None = None) -> dict:
    """Dựng request Messages API — tách riêng để test không cần gọi mạng.

    Prompt caching (task 5.3): cache_control đặt trên document block CUỐI —
    hỏi nhiều câu trên cùng bộ section (hội thoại đào sâu 1 paper) chỉ trả
    ~10% giá cho phần tài liệu từ request thứ 2.

    `language`: None -> config.ANSWER_LANGUAGE; hoặc "auto"/"en"/"vi" (xem system_prompt()).
    `history`: các lượt trước [{"question", "answer"}] -> thành cặp turn user/assistant
    đứng trước lượt hiện tại (assistant turn GIỮA hội thoại hợp lệ — chỉ prefill
    ở turn CUỐI mới bị API cấm).
    """
    messages: list[dict] = []
    for h in history or []:
        messages.append({"role": "user", "content": h["question"]})
        messages.append({"role": "assistant", "content": h["answer"]})

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
    messages.append({"role": "user", "content": content})

    return {
        "model": model or config.ANSWER_MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt(language),
        "messages": messages,
    }


# ------------------------------------------------------ usage & chi phí (B4)

# USD / 1M token (input, output) — cache read tính 10% giá input.
# Giá thay đổi theo thời gian: đây là ước lượng hiển thị, không phải hóa đơn.
_PRICES_PER_MTOK = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def usage_from_response(response, model: str) -> dict | None:
    """Bóc usage từ response + ước tính chi phí. Model ngoài bảng giá (Ollama...) -> cost None."""
    u = getattr(response, "usage", None)
    if u is None:
        return None
    usage = {
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
    }
    prices = _PRICES_PER_MTOK.get(model)
    usage["cost_usd"] = (
        round((usage["input_tokens"] * prices[0]
               + usage["cache_read_input_tokens"] * prices[0] * 0.1
               + usage["output_tokens"] * prices[1]) / 1e6, 4)
        if prices else None
    )
    return usage


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
    """Render ra text cho CLI: câu trả lời + danh mục nguồn + chi phí."""
    out = result["text"]
    if result["citations"]:
        out += "\n\nNguồn:\n" + "\n".join(
            f'  [{c["n"]}] {c["title"]}' for c in result["citations"]
        )
    usage = result.get("usage")
    if usage:
        line = (f'\n\n({usage["input_tokens"]:,} in'
                + (f' + {usage["cache_read_input_tokens"]:,} cache' if usage["cache_read_input_tokens"] else "")
                + f' / {usage["output_tokens"]:,} out')
        if usage.get("cost_usd") is not None:
            line += f' ≈ ${usage["cost_usd"]:.4f}'
        out += line + ")"
    return out


# ---------------------------- generic path (LLM_BACKEND=openai_compat, thuần)

_GENERIC_PROMPT = """Trả lời câu hỏi CHỈ dựa trên các nguồn được đánh số dưới đây.
Sau mỗi ý lấy từ nguồn nào, ghi số nguồn dạng [1], [2]... Không đủ căn cứ thì nói rõ.
{language_instruction}
{history_block}
{sources}

Câu hỏi: {question}"""


def build_generic_prompt(question: str, sections: list[dict], language: str | None = None,
                         history: list[dict] | None = None) -> str:
    """Citation qua prompt — cho model không có citations API (Ollama/Groq/Gemini...).

    Kém tin cậy hơn citations API của Claude (model có thể ghi nhầm số) —
    đó là trade-off đã chấp nhận khi chạy local/free, xem SETUP.md.
    """
    sources = "\n\n".join(
        f'[{i + 1}] {sec["paper_title"]} — {sec["section"]}\n{sec["text"]}'
        for i, sec in enumerate(sections)
    )
    history_block = ""
    if history:
        turns = "\n".join(
            f'Người dùng: {h["question"]}\nTrợ lý: {h["answer"][:500]}'
            for h in history[-3:]
        )
        history_block = f"\nHội thoại trước đó (để hiểu ngữ cảnh câu hỏi):\n{turns}\n"
    return _GENERIC_PROMPT.format(sources=sources, question=question,
                                  language_instruction=_language_instruction(language),
                                  history_block=history_block)


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

def _retrieve_for(question: str, filters, history, rewrite_llm, retrieve_kwargs) -> list[dict]:
    """Bước tìm kiếm chung cho answer()/answer_stream(): follow-up thì viết lại
    thành câu độc lập trước khi retrieve (câu gốc vẫn đưa cho model trả lời)."""
    retrieval_q = rewrite_followup(question, history, llm=rewrite_llm)
    return retrieve(retrieval_q, filters=filters, **retrieve_kwargs)


def answer(question: str, filters: dict | None = None, language: str | None = None,
           history: list[dict] | None = None, rewrite_llm=None, **retrieve_kwargs) -> dict:
    """Câu hỏi thường: retrieve -> 1 call LLM.

    - LLM_BACKEND=anthropic:     citations API (có cấu trúc, tin cậy).
    - LLM_BACKEND=openai_compat: citation qua prompt đánh số nguồn.
    `language`: None -> config.ANSWER_LANGUAGE; hoặc "auto"/"en"/"vi" để hỏi
    một ngôn ngữ nhưng nhận lại ngôn ngữ khác (VD: hỏi tiếng Việt, trả lời tiếng Anh).
    `history`: các lượt trước [{"question", "answer"}] -> hội thoại nhiều lượt
    ("còn về X thì sao?" hiểu được ngữ cảnh). Kết quả kèm `usage` (token + ước tính $).
    """
    sections = _retrieve_for(question, filters, history, rewrite_llm, retrieve_kwargs)
    if not sections:
        return {"text": "Không tìm thấy đoạn nào liên quan trong kho paper.",
                "citations": [], "usage": None}

    if config.LLM_BACKEND == "openai_compat":
        from src.llm import complete

        text = complete(build_generic_prompt(question, sections, language=language,
                                             history=history),
                        model=config.ANSWER_MODEL, max_tokens=2048,
                        system=system_prompt(language))
        result = extract_generic_citations(text, sections)
        result["usage"] = None  # endpoint compat không trả usage qua wrapper hiện tại
    else:
        import anthropic

        request = build_answer_request(question, sections, language=language, history=history)
        response = anthropic.Anthropic().messages.create(**request)
        result = extract_answer(response)
        result["usage"] = usage_from_response(response, request["model"])

    result["sections"] = sections
    return result


def answer_stream(question: str, filters: dict | None = None, language: str | None = None,
                  history: list[dict] | None = None, rewrite_llm=None, **retrieve_kwargs):
    """Bản streaming của answer() — generator sinh các event dict:

      {"type": "delta", "text": ...}   từng mẩu text khi model đang viết
      {"type": "done", "text", "citations", "usage"}   bản chốt cuối cùng

    Text trong delta CHƯA có đánh số citation [n] — event "done" mang bản text
    hoàn chỉnh đã gắn số, UI thay thế nội dung stream bằng bản này khi kết thúc.
    Backend không phải anthropic: không stream được -> 1 delta trọn gói rồi done.
    """
    sections = _retrieve_for(question, filters, history, rewrite_llm, retrieve_kwargs)
    if not sections:
        yield {"type": "done", "text": "Không tìm thấy đoạn nào liên quan trong kho paper.",
               "citations": [], "usage": None}
        return

    if config.LLM_BACKEND == "anthropic":
        import anthropic

        request = build_answer_request(question, sections, language=language, history=history)
        with anthropic.Anthropic().messages.stream(**request) as stream:
            for delta in stream.text_stream:
                yield {"type": "delta", "text": delta}
            response = stream.get_final_message()
        result = extract_answer(response)
        yield {"type": "done", **result, "usage": usage_from_response(response, request["model"])}
    else:
        from src.llm import complete

        text = complete(build_generic_prompt(question, sections, language=language,
                                             history=history),
                        model=config.ANSWER_MODEL, max_tokens=2048,
                        system=system_prompt(language))
        result = extract_generic_citations(text, sections)
        yield {"type": "delta", "text": result["text"]}
        yield {"type": "done", **result, "usage": None}


# ------------------------------------------------- so sánh nhiều paper (4.2)

_MAP_PROMPT = """Dựa trên các trích đoạn từ paper "{title}", tóm tắt góc nhìn của paper này
cho câu hỏi sau (3-5 gạch đầu dòng, chỉ dùng thông tin trong trích đoạn):

{question}"""

_REDUCE_PROMPT = """Câu hỏi so sánh: {question}

Tóm tắt góc nhìn của từng paper:

{summaries}

So sánh trực tiếp các paper trên theo câu hỏi. Trình bày điểm giống, điểm khác,
và điều kiện áp dụng của mỗi cách tiếp cận. {language_instruction}"""


def compare_papers(question: str, paper_ids: list[str], llm=None, language: str | None = None,
                   **retrieve_kwargs) -> dict:
    """Map-reduce: retrieve + tóm tắt riêng từng paper (map) -> 1 call tổng hợp (reduce).

    `language` áp dụng cho cả bước map và reduce (cùng system prompt) — xem answer().
    """
    if llm is None:
        from src.llm import complete

        def llm(prompt: str, max_tokens: int = 1500) -> str:
            return complete(prompt, model=config.ANSWER_MODEL, max_tokens=max_tokens,
                            system=system_prompt(language))

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

    text = llm(_REDUCE_PROMPT.format(question=question, summaries="\n\n".join(summaries),
                                     language_instruction=_language_instruction(language)))
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
