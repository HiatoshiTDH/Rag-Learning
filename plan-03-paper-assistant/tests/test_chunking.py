"""Test offline cho task 1.2 (parse TEI) + 1.3 (chunking) — dùng fixture, không cần GROBID."""

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
    # References nằm trong <back> — không được lọt vào sections
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
    # Đoạn dài ~1500 token phải bị cắt thành >=2 chunk, cộng đoạn ngắn thứ hai
    assert len(method) >= 3
    for c in method:
        assert len(c.text) // 4 <= config.MAX_CHUNK_TOKENS + 50  # nới nhẹ vì cắt theo câu
    # Không cắt giữa câu: mỗi chunk kết thúc bằng dấu câu
    assert all(c.text.rstrip()[-1] in ".!?" for c in method)


def test_chunk_ids_unique_and_parent_consistent():
    chunks = chunk_paper(_paper())
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    for c in chunks:
        assert c.chunk_id.startswith(c.parent_section_id)


# ------------------------------------------------- tiếng Nhật / CJK (nhóm A.3)

def test_est_tokens_cjk_denser_than_latin():
    """Chữ CJK đặc hơn Latin — len//4 sẽ đánh giá thấp ~3x và không bao giờ cắt đúng."""
    from src.ingest import _est_tokens

    jp = "ロボットの記憶検索機構を提案する。" * 100
    assert _est_tokens(jp) > len(jp) // 4 * 2


def test_split_long_japanese_paragraph():
    """Văn bản Nhật không có space sau dấu câu — regex [.!?]\\s+ thuần sẽ không bao giờ cắt."""
    from src import config
    from src.ingest import Paper, Section, chunk_paper

    jp_par = ("本研究では、身体性エージェントのための長期記憶検索機構を提案する。"
              "重要度と新しさと関連性を統合したスコアリング関数を用いる。") * 40
    paper = Paper(paper_id="jp.001", title="日本語論文", authors=["山田太郎"],
                  year=2024, abstract="要約。",
                  sections=[Section(title="3. 提案手法", paragraphs=[jp_par])])
    chunks = [c for c in chunk_paper(paper) if c.section_type != "abstract"]
    assert len(chunks) >= 2                        # đoạn dài PHẢI bị cắt
    from src.ingest import _est_tokens
    for c in chunks:
        assert _est_tokens(c.text) <= config.MAX_CHUNK_TOKENS + 100
        assert c.text.rstrip()[-1] in "。！？.!?"    # không cắt giữa câu


# ---------------------------------------------------------- PDF local (nhóm B.2)

def test_add_local_pdf(tmp_path, monkeypatch):
    from src import config
    from src.ingest import add_local_pdf

    src_pdf = tmp_path / "My Cool Paper (2024).pdf"
    src_pdf.write_bytes(b"%PDF-fake")
    out_dir = tmp_path / "papers"

    paper_id = add_local_pdf(src_pdf, out_dir=out_dir)
    assert paper_id.startswith("local-")
    assert (out_dir / f"{paper_id}.pdf").exists()
    meta = (out_dir / f"{paper_id}.json").read_text()
    assert "My Cool Paper" in meta

    # id tự đặt
    pid2 = add_local_pdf(src_pdf, paper_id="my-thesis", out_dir=out_dir)
    assert pid2 == "my-thesis" and (out_dir / "my-thesis.pdf").exists()


def test_add_local_pdf_missing_file(tmp_path):
    import pytest

    from src.ingest import add_local_pdf

    with pytest.raises(FileNotFoundError):
        add_local_pdf(tmp_path / "khong-ton-tai.pdf", out_dir=tmp_path)
