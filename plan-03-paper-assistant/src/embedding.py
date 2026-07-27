"""Embedder interface + 2 backend: Voyage AI (thật) và Hash (test/offline).

Đổi backend qua env EMBED_BACKEND (voyage | fake). Lưu ý: đổi backend là đổi
số chiều vector -> phải xóa data/qdrant (hoặc collection) và index lại.
"""

import hashlib
import re
from typing import Protocol

from src import config


class Embedder(Protocol):
    dim: int

    def embed_docs(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class HashEmbedder:
    """Bag-of-words hashing, deterministic — cho test và dev offline.

    Không có ngữ nghĩa thật (chỉ trùng từ mới match), tuyệt đối không dùng
    để đánh giá chất lượng retrieval.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in re.findall(r"[a-z0-9]+", text.lower()):
            idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dim
            vec[idx] += 1.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    def embed_docs(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class VoyageEmbedder:
    """voyage-3: đa ngôn ngữ, 1024 chiều. input_type document/query khác nhau."""

    MODEL = "voyage-3"

    def __init__(self):
        import voyageai

        if not config.VOYAGE_API_KEY:
            raise RuntimeError(
                "Thiếu VOYAGE_API_KEY trong .env — hoặc đặt EMBED_BACKEND=fake để dev offline."
            )
        self.client = voyageai.Client(api_key=config.VOYAGE_API_KEY)
        self.dim = 1024

    def embed_docs(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 128):  # batch limit
            batch = texts[i : i + 128]
            out.extend(self.client.embed(batch, model=self.MODEL, input_type="document").embeddings)
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.client.embed([text], model=self.MODEL, input_type="query").embeddings[0]


def get_embedder() -> Embedder:
    if config.EMBED_BACKEND == "fake":
        return HashEmbedder()
    if config.EMBED_BACKEND == "voyage":
        return VoyageEmbedder()
    raise ValueError(f"EMBED_BACKEND không hợp lệ: {config.EMBED_BACKEND!r} (voyage | fake)")
