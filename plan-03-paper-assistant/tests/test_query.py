"""Offline tests for P3-P4: BM25, RRF, hybrid, rerank, parent-doc, expansion, retrieve."""

from pathlib import Path

import pytest
from lxml import etree
from qdrant_client import QdrantClient

from src.embedding import HashEmbedder
from src.index import save_metadata, upsert_chunks
from src.ingest import chunk_paper, parse_tei
from src.query import (bm25_search, expand_query, hybrid_search, retrieve,
                       rrf_fuse, to_parent_sections)
from src.rerank import FakeReranker, NoopReranker

FIXTURE = Path(__file__).parent / "fixtures" / "sample_tei.xml"


@pytest.fixture
def env(tmp_path):
    """Index the fixture paper into in-memory Qdrant + temp SQLite."""
    paper = parse_tei(etree.fromstring(FIXTURE.read_bytes()), paper_id="2308.00001")
    chunks = chunk_paper(paper)
    embedder = HashEmbedder()
    client = QdrantClient(":memory:")
    db_path = tmp_path / "metadata.sqlite"
    save_metadata(paper, chunks, db_path=db_path)
    upsert_chunks(chunks, embedder=embedder, client=client)
    return dict(chunks=chunks, embedder=embedder, client=client, db_path=db_path)


# ------------------------------------------------------------------- BM25/RRF

def test_bm25_finds_exact_term(env):
    hits = bm25_search("importance score ten point scale", top_k=5, db_path=env["db_path"])
    assert hits and hits[0]["section_type"] == "method"


def test_bm25_respects_filters(env):
    hits = bm25_search("memory retrieval", top_k=10,
                       filters={"section_type": "abstract"}, db_path=env["db_path"])
    assert hits and all(h["section_type"] == "abstract" for h in hits)


def test_rrf_fuse_rewards_agreement():
    a = [{"chunk_id": "x", "v": 1}, {"chunk_id": "y", "v": 1}]
    b = [{"chunk_id": "y", "v": 1}, {"chunk_id": "z", "v": 1}]
    fused = rrf_fuse([a, b])
    # y appears in both rankings -> must come first
    assert fused[0]["chunk_id"] == "y"
    assert {f["chunk_id"] for f in fused} == {"x", "y", "z"}


def test_hybrid_search_merges_both(env):
    hits = hybrid_search(["importance score rated by a language model"],
                         embedder=env["embedder"], client=env["client"], db_path=env["db_path"])
    assert hits and hits[0]["section_type"] == "method"


# -------------------------------------------------------------------- rerank

def test_fake_reranker_orders_by_overlap():
    cands = [
        {"chunk_id": "a", "text": "completely unrelated content about weather"},
        {"chunk_id": "b", "text": "recency decay and importance weighting for retrieval"},
    ]
    top = FakeReranker().rerank("importance weighting retrieval", cands, top_k=1)
    assert top[0]["chunk_id"] == "b"


def test_noop_reranker_keeps_order():
    cands = [{"chunk_id": "a", "text": "x"}, {"chunk_id": "b", "text": "y"}]
    assert NoopReranker().rerank("anything", cands, top_k=1)[0]["chunk_id"] == "a"


# ---------------------------------------------------------------- parent-doc

def test_to_parent_sections_dedupes(env):
    method_chunks = [c for c in env["chunks"] if c.section_type == "method"]
    as_dicts = [{"parent_section_id": c.parent_section_id} for c in method_chunks]
    sections = to_parent_sections(as_dicts, db_path=env["db_path"])
    assert len(sections) == 1  # many chunks of one section -> exactly one section
    assert sections[0]["section"] == "3. Method"


# ----------------------------------------------------------------- expansion

def test_expand_query_with_injected_llm():
    # The Vietnamese question is deliberate data — it exercises the multilingual
    # expansion feature (first variant should be an English translation).
    fake_llm = lambda prompt: "memory retrieval for agents\nrecency importance relevance scoring"
    queries = expand_query("NPC nhớ bằng cách nào?", n=2, llm=fake_llm)
    assert queries[0] == "NPC nhớ bằng cách nào?"      # original question always first
    assert len(queries) == 3


# ------------------------------------------------------- retrieve (combined)

def test_retrieve_full_pipeline_offline(env):
    fake_llm = lambda prompt: "importance score language model rating"
    sections = retrieve(
        "How is the importance score produced?",
        embedder=env["embedder"], client=env["client"], db_path=env["db_path"],
        reranker=FakeReranker(), llm=fake_llm,
    )
    assert sections and sections[0]["section"] == "3. Method"


def test_retrieve_v1_mode(env):
    """Eval's baseline mode: no expansion, no hybrid, no rerank."""
    chunks = retrieve(
        "memory retrieval for embodied agents",
        expand=False, hybrid=False, parent=False, reranker=NoopReranker(),
        embedder=env["embedder"], client=env["client"], db_path=env["db_path"],
    )
    assert chunks and all("chunk_id" in c for c in chunks)
