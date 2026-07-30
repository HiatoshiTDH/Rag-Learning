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


class LocalEmbedder:
    """bge-m3 chạy local qua sentence-transformers — $0, đa ngôn ngữ Việt/Nhật/Anh tốt.

    Lần đầu sẽ tải model ~2.3GB về ~/.cache/huggingface. CPU chạy được
    (chậm hơn), GPU thì nhanh. Cần: pip install sentence-transformers
    """

    MODEL = "BAAI/bge-m3"

    def __init__(self):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError(
                "EMBED_BACKEND=local cần sentence-transformers: pip install sentence-transformers"
            ) from e
        self.model = SentenceTransformer(self.MODEL)
        self.dim = self.model.get_sentence_embedding_dimension()  # 1024

    def embed_docs(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode([text], normalize_embeddings=True)[0].tolist()


def get_embedder() -> Embedder:
    if config.EMBED_BACKEND == "fake":
        return HashEmbedder()
    if config.EMBED_BACKEND == "voyage":
        return VoyageEmbedder()
    if config.EMBED_BACKEND == "local":
        return LocalEmbedder()
    raise ValueError(f"EMBED_BACKEND không hợp lệ: {config.EMBED_BACKEND!r} (voyage | local | fake)")
