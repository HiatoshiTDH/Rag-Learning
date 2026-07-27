"""P2 (2.4) + P3 (3.5) — Measure recall@k on the golden set, log to EXPERIMENTS.md.

Golden set: data/golden_set.jsonl — one JSON per line:
  {"question": "...", "expect_paper": "2304.03442", "expect_section_type": "method"}
(expect_section_type is optional; see data/golden_set.example.jsonl)

Run: python -m src.cli eval --stage full
Stages to measure each layer (task 3.5):
  v1     = pure vector search, no expansion, no rerank
  hybrid = + BM25/RRF
  rerank = + re-ranking
  full   = + query expansion (default)
"""

import json
from datetime import date
from pathlib import Path

from src import config
from src.query import retrieve
from src.rerank import NoopReranker


STAGES = {
    #        expand, hybrid, reranker (None = follow the RERANK_BACKEND config)
    "v1":     (False, False, NoopReranker()),   # pure vector — baseline
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
    """A case passes when the expected paper (and section_type, if set) is in the top-k."""
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
    """Run the golden set through retrieve with the stage config; return recall@k + failed cases."""
    cases = cases if cases is not None else load_golden_set()
    if not cases:
        raise SystemExit(
            f"Golden set empty ({config.GOLDEN_SET}) — create one from data/golden_set.example.jsonl first."
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
    """Task 3.5 — append one row to EXPERIMENTS.md (creating it with a header if missing)."""
    path = config.EXPERIMENTS_FILE
    if not path.exists():
        path.write_text(
            "# Retrieval experiment log\n\n"
            "Every chunking/embedding/re-rank change -> run `python -m src.cli eval` and record it.\n\n"
            "| Date | Stage | recall@k | n cases | Note |\n"
            "|------|-------|----------|---------|------|\n"
        )
    row = (f'| {date.today()} | {result["stage"]} '
           f'| {result["recall"]:.2f}@{result["top_k"]} | {result["n"]} | {note} |\n')
    with open(path, "a") as f:
        f.write(row)


def print_report(result: dict) -> None:
    print(f'Stage: {result["stage"]}  —  recall@{result["top_k"]} = '
          f'{result["recall"]:.2%}  ({result["n"] - len(result["failures"])}/{result["n"]})')
    if result["failures"]:
        print("Failed cases:")
        for q in result["failures"]:
            print(f"  - {q}")
