"""P3 (task 3.3) — Re-ranking: bước cải thiện chất lượng rõ nhất so với công sức.

Backend chọn qua env RERANK_BACKEND: voyage | fake | none.
"""

import re

from src import config


class FakeReranker:
    """Chấm theo tỉ lệ trùng từ — deterministic, cho test/dev offline."""

    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        q_tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        if not q_tokens:
            return candidates[:top_k]

        def overlap(c: dict) -> float:
            d_tokens = set(re.findall(r"[a-z0-9]+", c["text"].lower()))
            return len(q_tokens & d_tokens) / len(q_tokens)

        ranked = sorted(candidates, key=overlap, reverse=True)
        return ranked[:top_k]


class VoyageReranker:
    MODEL = "rerank-2"

    def __init__(self):
        import voyageai

        if not config.VOYAGE_API_KEY:
            raise RuntimeError("Thiếu VOYAGE_API_KEY — hoặc đặt RERANK_BACKEND=fake/none.")
        self.client = voyageai.Client(api_key=config.VOYAGE_API_KEY)

    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        if not candidates:
            return []
        result = self.client.rerank(
            query, [c["text"] for c in candidates], model=self.MODEL, top_k=top_k
        )
        return [candidates[r.index] for r in result.results]


class NoopReranker:
    """Không re-rank — giữ thứ tự hiện có, chỉ cắt top-k (để đo baseline)."""

    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        return candidates[:top_k]


def get_reranker():
    backend = config.RERANK_BACKEND
    if backend == "fake":
        return FakeReranker()
    if backend == "none":
        return NoopReranker()
    if backend == "voyage":
        return VoyageReranker()
    raise ValueError(f"RERANK_BACKEND không hợp lệ: {backend!r} (voyage | fake | none)")
