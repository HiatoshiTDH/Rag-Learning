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
    row = (f'| {date.today()} | {result["stage"]} '
           f'| {result["recall"]:.2f}@{result["top_k"]} | {result["n"]} | {note} |\n')
    with open(path, "a") as f:
        f.write(row)


def print_report(result: dict) -> None:
    print(f'Stage: {result["stage"]}  —  recall@{result["top_k"]} = '
          f'{result["recall"]:.2%}  ({result["n"] - len(result["failures"])}/{result["n"]})')
    if result["failures"]:
        print("Case fail:")
        for q in result["failures"]:
            print(f"  - {q}")
