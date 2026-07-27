"""Test offline cho task 1.4 + 1.5 — Qdrant in-memory + HashEmbedder, không cần docker/API key."""

from pathlib import Path

import pytest
from lxml import etree
from qdrant_client import QdrantClient

from src.embedding import HashEmbedder
from src.index import get_section, save_metadata, search, upsert_chunks
from src.ingest import chunk_paper, parse_tei

FIXTURE = Path(__file__).parent / "fixtures" / "sample_tei.xml"


@pytest.fixture
def indexed(tmp_path):
    paper = parse_tei(etree.fromstring(FIXTURE.read_bytes()), paper_id="2308.00001")
    chunks = chunk_paper(paper)
    embedder = HashEmbedder()
    client = QdrantClient(":memory:")
    db_path = tmp_path / "metadata.sqlite"
    save_metadata(paper, chunks, db_path=db_path)
    n = upsert_chunks(chunks, embedder=embedder, client=client)
    return dict(chunks=chunks, embedder=embedder, client=client, db_path=db_path, n=n)


def test_upsert_counts_match(indexed):
    assert indexed["n"] == len(indexed["chunks"])


def test_upsert_idempotent(indexed):
    """Task 1.6 yêu cầu chạy lại không duplicate — uuid5(chunk_id) bảo đảm điều đó."""
    upsert_chunks(indexed["chunks"], embedder=indexed["embedder"], client=indexed["client"])
    count = indexed["client"].count("papers").count
    assert count == len(indexed["chunks"])


def test_search_finds_relevant_section(indexed):
    hits = search("importance score rated by a language model",
                  top_k=3, embedder=indexed["embedder"], client=indexed["client"])
    assert hits and hits[0]["section_type"] == "method"


def test_search_with_filter(indexed):
    hits = search("memory retrieval", top_k=5,
                  filters={"section_type": "abstract"},
                  embedder=indexed["embedder"], client=indexed["client"])
    assert hits and all(h["section_type"] == "abstract" for h in hits)


def test_parent_section_lookup(indexed):
    """Task 1.5 — full section cho parent-document retrieval ở P3."""
    method_chunk = next(c for c in indexed["chunks"] if c.section_type == "method")
    section = get_section(method_chunk.parent_section_id, db_path=indexed["db_path"])
    assert section is not None
    assert section["section"] == "3. Method"
    # Section phải chứa đủ nội dung của mọi chunk con
    for c in indexed["chunks"]:
        if c.parent_section_id == method_chunk.parent_section_id:
            assert c.text in section["text"]
