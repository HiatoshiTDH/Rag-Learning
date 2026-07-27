"""Shared fixtures — every test runs OFFLINE: HashEmbedder + in-memory Qdrant +
temp SQLite + ScriptedLLM. No docker, no API keys."""

from datetime import datetime, timedelta, timezone

import pytest
from qdrant_client import QdrantClient

from src import config
from src.embedding import HashEmbedder
from src.memory_store import MemoryRecord, MemoryStore


@pytest.fixture(autouse=True)
def _force_offline(monkeypatch):
    """Tests are always offline regardless of .env — no accidental API spend from pytest."""
    monkeypatch.setattr(config, "EMBED_BACKEND", "fake")
    monkeypatch.setattr(config, "LLM_BACKEND", "none")


@pytest.fixture
def store(tmp_path) -> MemoryStore:
    return MemoryStore(
        db_path=tmp_path / "memories.sqlite",
        client=QdrantClient(":memory:"),
        embedder=HashEmbedder(),
    )


@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc)


def seed(store: MemoryStore, npc_id: str, text: str, importance: int,
         hours_ago: float = 0.0, type: str = "observation",
         now: datetime | None = None) -> MemoryRecord:
    """Write one memory backdated by `hours_ago` hours."""
    ts = (now or datetime.now(timezone.utc)) - timedelta(hours=hours_ago)
    return store.add(MemoryRecord.new(npc_id, type, text, importance, created_at=ts))
