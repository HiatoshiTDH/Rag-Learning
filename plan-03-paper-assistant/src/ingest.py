"""Tuần 1 — Ingest pipeline: PDF -> GROBID -> TEI XML -> chunks có cấu trúc.

Chạy GROBID trước khi dùng:
    docker run -p 8070:8070 lfoppiano/grobid:0.8.0
"""

from dataclasses import dataclass, field

GROBID_URL = "http://localhost:8070/api/processFulltextDocument"

# Chuẩn hóa tên section về các loại cố định để filter được khi query
SECTION_TYPES = ["abstract", "intro", "related_work", "method", "experiment", "result", "conclusion"]


@dataclass
class Chunk:
    chunk_id: str          # "2309.12345#method#3"
    paper_id: str
    title: str
    authors: list[str]
    year: int
    section: str           # "3. Method"
    section_type: str      # một trong SECTION_TYPES
    text: str
    parent_section_id: str # để làm parent-document retrieval


def fetch_arxiv(keyword: str, category: str, max_results: int = 20) -> list[str]:
    """TODO(tuần 1): gọi arXiv API, tải PDF về data/papers/, trả về list đường dẫn."""
    raise NotImplementedError


def parse_pdf(pdf_path: str) -> "lxml.etree._Element":
    """TODO(tuần 1): POST PDF lên GROBID, trả về TEI XML đã parse.

    Lưu ý: đừng dùng pdf-to-text thường — paper 2 cột sẽ bị trộn dòng.
    """
    raise NotImplementedError


def chunk_paper(tei_xml, paper_id: str) -> list[Chunk]:
    """TODO(tuần 1): structure-aware chunking.

    Quy tắc (xem README mục 3.3):
    - Đơn vị chunk = đoạn văn trong section, không cắt ngang đoạn.
    - Đoạn > 800 token mới cắt tiếp theo câu.
    - Abstract luôn là một chunk riêng.
    - KHÔNG index phần References như văn bản thường.
    """
    raise NotImplementedError
