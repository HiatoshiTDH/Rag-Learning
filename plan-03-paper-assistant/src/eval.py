"""P2 (2.4) + P3 (3.5) — Đo recall@k trên golden set, ghi kết quả vào EXPERIMENTS.md.

Golden set: data/golden_set.jsonl — mỗi dòng một JSON:
  {"question": "...", "expect_paper": "2304.03442", "expect_section_type": "method"}
(expect_section_type là tùy chọn; xem data/golden_set.example.jsonl)

Chạy: python -m src.cli eval --stage full
Stages để đo từng tầng (task 3.5):
  v1     = vector search thuần, không expand, không rerank
  hybrid = + BM25/RRF
  rerank = + re-ranking
  full   = + query expansion (mặc định)
"""

import json
from datetime import date
from pathlib import Path

from src import config
from src.query import retrieve
from src.rerank import NoopReranker


STAGES = {
    #        expand, hybrid, reranker (None = theo config RERANK_BACKEND)
    "v1":     (False, False, NoopReranker()),   # vector thuần — baseline
    "hybrid": (False, True,  NoopReranker()),   # + BM25/RRF
    "rerank": (False, True,  None),             # + re-ranking
    "full":   (True,  True,  None),             # + query expansion
}


def load_golden_set(path: Path | None = None) -> list[dict]:
    path = path or config.GOLDEN_SET
    if not path.exists():
        return []
    cases = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            cases.append(json.loads(line))
    return cases


def hit(case: dict, results: list[dict]) -> bool:
    """Một case pass khi paper kỳ vọng (và section_type nếu có) nằm trong top-k."""
    for r in results:
        if r["paper_id"] != case["expect_paper"]:
            continue
        want_type = case.get("expect_section_type")
        if want_type and r["section_type"] != want_type:
            continue
        return True
    return False


def run_eval(stage: str = "full", top_k: int = 8, cases: list[dict] | None = None,
             **retrieve_kwargs) -> dict:
    """Chạy golden set qua retrieve với cấu hình stage, trả recall@k + list case fail."""
    cases = cases if cases is not None else load_golden_set()
    if not cases:
        raise SystemExit(
            f"Golden set trống ({config.GOLDEN_SET}) — tạo theo data/golden_set.example.jsonl trước."
        )
    expand, hybrid, reranker = STAGES[stage]

    hits, failures = 0, []
    for case in cases:
        results = retrieve(case["question"], top_k=top_k, expand=expand, hybrid=hybrid,
                           parent=False, reranker=reranker, **retrieve_kwargs)
        if hit(case, results):
            hits += 1
        else:
            failures.append(case["question"])

    recall = hits / len(cases)
    return {"stage": stage, "top_k": top_k, "n": len(cases), "recall": recall, "failures": failures}


# ----------------------------------------- faithfulness (mượn từ Plan 12, bản rút gọn)

_JUDGE_PROMPT = """Bạn là giám khảo chấm độ BÁM SÁT NGUỒN (faithfulness) của một câu trả lời RAG.

Câu hỏi: {question}

Các nguồn model được cung cấp:
{sources}

Câu trả lời của model:
{answer}

Tiêu chí: MỌI ý chính trong câu trả lời phải có căn cứ trong nguồn. Câu trả lời
kiểu "các paper không đề cập" được tính là bám sát. Diễn giải lại bằng lời khác
vẫn tính là có căn cứ; thêm số liệu/kết luận không có trong nguồn là KHÔNG.

In đúng định dạng:
PHÁN QUYẾT: PASS hoặc FAIL
LÝ DO: <một câu>"""


def judge_faithfulness(question: str, answer_text: str, sections: list[dict],
                       llm=None) -> dict:
    """LLM-as-judge: câu trả lời có bám sát các section đã retrieve không?

    Đo tầng GENERATION — bổ khuyết cho recall@k (chỉ đo tầng retrieval: tìm đúng
    đoạn không đảm bảo model không bịa khi tổng hợp).
    """
    if llm is None:
        from src.llm import complete

        def llm(prompt: str) -> str:
            return complete(prompt, model=config.ANSWER_MODEL, max_tokens=300)

    sources = "\n\n".join(
        f'[{i + 1}] {s["paper_title"]} — {s["section"]}\n{s["text"][:2000]}'
        for i, s in enumerate(sections)
    )
    raw = llm(_JUDGE_PROMPT.format(question=question, sources=sources, answer=answer_text))

    verdict, reason = None, ""
    for line in raw.splitlines():
        up = line.upper()
        if up.startswith("PHÁN QUYẾT") or up.startswith("PHAN QUYET"):
            verdict = "PASS" in up.split(":", 1)[-1]
        elif up.startswith("LÝ DO") or up.startswith("LY DO"):
            reason = line.split(":", 1)[-1].strip()
    if verdict is None:  # judge trả sai định dạng -> tìm token trần; vẫn mù mờ thì FAIL an toàn
        up = raw.upper()
        verdict = "PASS" in up and "FAIL" not in up
    return {"faithful": bool(verdict), "reason": reason or raw[:200]}


def run_faithfulness_eval(n: int = 5, cases: list[dict] | None = None,
                          answer_fn=None, judge_llm=None) -> dict:
    """Chạy answer() thật trên n case đầu của golden set rồi chấm bằng judge.

    LƯU Ý: mỗi case = 1 call answer (opus) + 1 call judge -> có chi phí thật,
    vì thế mặc định chỉ 5 case. answer_fn/judge_llm inject được để test offline.
    """
    cases = (cases if cases is not None else load_golden_set())[:n]
    if not cases:
        raise SystemExit(
            f"Golden set trống ({config.GOLDEN_SET}) — tạo theo data/golden_set.example.jsonl trước."
        )
    if answer_fn is None:
        from src.answer import answer as answer_fn

    passed, failures = 0, []
    for case in cases:
        result = answer_fn(case["question"])
        verdict = judge_faithfulness(case["question"], result["text"],
                                     result.get("sections", []), llm=judge_llm)
        if verdict["faithful"]:
            passed += 1
        else:
            failures.append(f'{case["question"]} — {verdict["reason"]}')

    return {"stage": "faithfulness", "top_k": None, "n": len(cases),
            "recall": passed / len(cases), "failures": failures}


def log_experiment(result: dict, note: str = "") -> None:
    """Task 3.5 — append một dòng vào EXPERIMENTS.md (tạo file kèm header nếu chưa có)."""
    path = config.EXPERIMENTS_FILE
    if not path.exists():
        path.write_text(
            "# Nhật ký thí nghiệm retrieval\n\n"
            "Mỗi lần đổi chunking/embedding/re-rank -> chạy `python -m src.cli eval` và ghi lại.\n\n"
            "| Ngày | Stage | recall@k | n case | Ghi chú |\n"
            "|------|-------|----------|--------|--------|\n"
        )
    metric = f'{result["recall"]:.2f}'
    if result.get("top_k"):
        metric += f'@{result["top_k"]}'
    row = f'| {date.today()} | {result["stage"]} | {metric} | {result["n"]} | {note} |\n'
    with open(path, "a") as f:
        f.write(row)


def print_report(result: dict) -> None:
    metric = f'recall@{result["top_k"]}' if result.get("top_k") else "tỉ lệ pass"
    print(f'Stage: {result["stage"]}  —  {metric} = '
          f'{result["recall"]:.2%}  ({result["n"] - len(result["failures"])}/{result["n"]})')
    if result["failures"]:
        print("Case fail:")
        for q in result["failures"]:
            print(f"  - {q}")
