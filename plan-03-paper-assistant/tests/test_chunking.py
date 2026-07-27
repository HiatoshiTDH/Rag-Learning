"""Offline tests for task 1.2 (TEI parsing) + 1.3 (chunking) — fixture-based, no GROBID needed."""

from pathlib import Path

from lxml import etree

from src import config
from src.ingest import chunk_paper, parse_tei

FIXTURE = Path(__file__).parent / "fixtures" / "sample_tei.xml"


def _paper():
    tei = etree.fromstring(FIXTURE.read_bytes())
    return parse_tei(tei, paper_id="2308.00001")


def test_parse_tei_metadata():
    paper = _paper()
    assert paper.title == "Memory Retrieval for Embodied Agents"
    assert paper.authors == ["Alice Nguyen", "Bob Tanaka"]
    assert paper.year == 2023
    assert "long-term memory retrieval" in paper.abstract


def test_parse_tei_sections_exclude_back():
    paper = _paper()
    titles = [s.title for s in paper.sections]
    assert titles == ["1. Introduction", "2. Related Work", "3. Method"]
    # References live in <back> — they must not leak into sections
    assert not any("cited paper" in p for s in paper.sections for p in s.paragraphs)


def test_abstract_is_own_chunk():
    chunks = chunk_paper(_paper())
    abstract_chunks = [c for c in chunks if c.section_type == "abstract"]
    assert len(abstract_chunks) == 1
    assert abstract_chunks[0].chunk_id == "2308.00001#abstract#0"


def test_section_types_normalized():
    chunks = chunk_paper(_paper())
    types = {c.section: c.section_type for c in chunks}
    assert types["1. Introduction"] == "intro"
    assert types["2. Related Work"] == "related_work"
    assert types["3. Method"] == "method"


def test_long_paragraph_split_by_sentence():
    chunks = chunk_paper(_paper())
    method = [c for c in chunks if c.section_type == "method"]
    # The ~1500-token paragraph must split into >=2 chunks, plus the second short paragraph
    assert len(method) >= 3
    for c in method:
        assert len(c.text) // 4 <= config.MAX_CHUNK_TOKENS + 50  # slight slack for sentence splits
    # No mid-sentence cuts: every chunk ends with punctuation
    assert all(c.text.rstrip()[-1] in ".!?" for c in method)


def test_chunk_ids_unique_and_parent_consistent():
    chunks = chunk_paper(_paper())
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    for c in chunks:
        assert c.chunk_id.startswith(c.parent_section_id)
