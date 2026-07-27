"""Embedder interface + 2 backends: Voyage AI (real) and Hash (test/offline).

Switch backends via the EMBED_BACKEND env var (voyage | fake). Note: changing
the backend changes the vector dimension -> delete data/qdrant (or the
collection) and re-index.
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
    """Bag-of-words hashing, deterministic — for tests and offline dev.

    No real semantics (only shared tokens match); never use it to evaluate
    retrieval quality.
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
    """voyage-3: multilingual, 1024 dims. Different input_type for document/query."""

    MODEL = "voyage-3"

    def __init__(self):
        import voyageai

        if not config.VOYAGE_API_KEY:
            raise RuntimeError(
                "VOYAGE_API_KEY missing from .env — or set EMBED_BACKEND=fake for offline dev."
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
    raise ValueError(f"Invalid EMBED_BACKEND: {config.EMBED_BACKEND!r} (voyage | fake)")
