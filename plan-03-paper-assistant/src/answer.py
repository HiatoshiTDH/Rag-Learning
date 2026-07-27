"""P2 (2.2) + P4 (4.2, 4.3) — Generation with Claude's citations API.

Each retrieved section goes in as a `document` block with citations enabled
-> the response carries structured citations (right document, right passage),
no manual parsing.

build_answer_request() is a pure function (no network) so the request
structure can be tested offline.
"""

import re

from src import config
from src.query import retrieve

SYSTEM_PROMPT = """You are a research assistant; answer ENTIRELY based on the provided documents.
Rules:
- Only state what the documents support. If the grounding is insufficient, say clearly "the papers in the corpus do not cover this".
- Answer in the same language as the question.
- When citing methods/numbers, always tie them to a specific paper (citations attach automatically)."""


# ----------------------------------------------------- build request (pure)

def build_answer_request(question: str, sections: list[dict],
                         model: str | None = None, max_tokens: int = 4096) -> dict:
    """Build the Messages API request — separated out so tests need no network.

    Prompt caching (task 5.3): cache_control goes on the LAST document block —
    asking several questions over the same section set (deep-diving one paper)
    costs only ~10% for the document part from the second request on.
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

    With citations enabled the text splits into multiple blocks; grounded
    blocks carry a .citations array. Number [n] by document-title appearance.
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
    """Render CLI text: the answer + a source list."""
    out = result["text"]
    if result["citations"]:
        out += "\n\nSources:\n" + "\n".join(
            f'  [{c["n"]}] {c["title"]}' for c in result["citations"]
        )
    return out


# ------------------------------------------------------------ API call (2.2)

def answer(question: str, filters: dict | None = None, **retrieve_kwargs) -> dict:
    """Ordinary question: retrieve -> 1 Claude call with citations."""
    import anthropic

    sections = retrieve(question, filters=filters, **retrieve_kwargs)
    if not sections:
        return {"text": "No relevant passages found in the paper corpus.", "citations": []}
    request = build_answer_request(question, sections)
    response = anthropic.Anthropic().messages.create(**request)
    result = extract_answer(response)
    result["sections"] = sections
    return result


# ------------------------------------------------ multi-paper comparison (4.2)

_MAP_PROMPT = """Based on the excerpts from the paper "{title}", summarize this paper's
perspective on the following question (3-5 bullet points, using only information
from the excerpts):

{question}"""

_REDUCE_PROMPT = """Comparison question: {question}

Per-paper perspective summaries:

{summaries}

Directly compare the papers above on the question. Lay out similarities,
differences, and when each approach applies. Answer in the question's language."""


def compare_papers(question: str, paper_ids: list[str], llm=None, **retrieve_kwargs) -> dict:
    """Map-reduce: retrieve + summarize each paper separately (map) -> 1 synthesis call (reduce)."""
    if llm is None:
        from src.llm import complete

        def llm(prompt: str, max_tokens: int = 1500) -> str:
            return complete(prompt, model=config.ANSWER_MODEL, max_tokens=max_tokens,
                            system=SYSTEM_PROMPT)

    summaries = []
    for pid in paper_ids:
        sections = retrieve(question, filters={"paper_id": pid}, top_k=5, **retrieve_kwargs)
        if not sections:
            summaries.append(f"### {pid}\n(no relevant passages found)")
            continue
        title = sections[0]["paper_title"]
        excerpt = "\n\n".join(s["text"][:3000] for s in sections)
        summary = llm(_MAP_PROMPT.format(title=title, question=question) + "\n\n" + excerpt)
        summaries.append(f"### {title} ({pid})\n{summary}")

    text = llm(_REDUCE_PROMPT.format(question=question, summaries="\n\n".join(summaries)))
    return {"text": text, "citations": [], "per_paper": summaries}


# ------------------------------------------------------------- router (4.3)

# Vietnamese comparison words are kept deliberately — the assistant supports
# questions asked in Vietnamese (see the multilingual expansion feature).
_COMPARE_WORDS = re.compile(r"\b(so sánh|khác nhau|khác gì|compare|versus|vs\.?|difference)\b", re.I)


def route(question: str, known_paper_ids: list[str]) -> dict:
    """Heuristic v1: what kind of question is this?

    - "compare": mentions >=2 paper_ids, or a comparison word + >=1 id
    - "single":  mentions exactly 1 paper_id -> filter to that paper
    - "general": everything else -> search the whole corpus
    """
    mentioned = [pid for pid in known_paper_ids if pid in question]
    if len(mentioned) >= 2:
        return {"kind": "compare", "paper_ids": mentioned}
    if _COMPARE_WORDS.search(question) and len(mentioned) >= 1:
        return {"kind": "compare", "paper_ids": mentioned}
    if len(mentioned) == 1:
        return {"kind": "single", "paper_ids": mentioned}
    return {"kind": "general", "paper_ids": []}
