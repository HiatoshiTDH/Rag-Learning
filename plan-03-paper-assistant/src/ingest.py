"""P1 — Ingest: arXiv -> PDF -> GROBID -> TEI XML -> chunks có cấu trúc.

Chạy GROBID trước khi dùng phần parse PDF:
    docker compose up -d      # xem SETUP.md

Ba tầng tách bạch để test được từng tầng:
  fetch_*        : mạng (arXiv)         — cần internet
  grobid_parse   : mạng (GROBID local)  — cần docker
  parse_tei/chunk: thuần dữ liệu        — test offline bằng fixture
"""

import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests
from lxml import etree

from src import config

ARXIV_API = "https://export.arxiv.org/api/query"
TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}

# Chuẩn hóa tên section về loại cố định để filter được khi query
SECTION_TYPES = ["abstract", "intro", "related_work", "method", "experiment", "result", "conclusion", "other"]
_SECTION_KEYWORDS = [
    ("related_work", ["related work", "background", "prior work"]),
    ("intro", ["introduction"]),
    ("method", ["method", "approach", "architecture", "proposed", "model"]),
    ("experiment", ["experiment", "setup", "implementation"]),
    ("result", ["result", "evaluation", "analysis", "ablation"]),
    ("conclusion", ["conclusion", "discussion", "future work", "limitation"]),
]
_REFERENCE_HEADS = ("reference", "bibliography", "acknowledg")


@dataclass
class Section:
    title: str
    paragraphs: list[str]


@dataclass
class Paper:
    paper_id: str
    title: str
    authors: list[str]
    year: int
    abstract: str
    sections: list[Section] = field(default_factory=list)


@dataclass
class Chunk:
    chunk_id: str          # "2309.12345#3-method#0"
    paper_id: str
    title: str
    authors: list[str]
    year: int
    section: str           # "3. Method"
    section_type: str      # một trong SECTION_TYPES
    text: str
    parent_section_id: str # để làm parent-document retrieval


# ---------------------------------------------------------------- fetch (mạng)

def read_seed_file(path: Path | None = None) -> list[str]:
    """Đọc data/seed_papers.txt — bỏ dòng trống và comment (#)."""
    path = path or config.SEED_FILE
    ids = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            ids.append(line)
    return ids


def fetch_by_ids(arxiv_ids: list[str], out_dir: Path | None = None) -> list[Path]:
    """Task 1.1 — tải PDF + metadata JSON cho từng arXiv id.

    Idempotent: id nào đã có PDF thì bỏ qua. Lịch sự với arXiv: nghỉ 3s giữa các lượt tải.
    """
    out_dir = out_dir or config.PAPERS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_paths: list[Path] = []

    for arxiv_id in arxiv_ids:
        safe_id = arxiv_id.replace("/", "_")
        pdf_path = out_dir / f"{safe_id}.pdf"
        meta_path = out_dir / f"{safe_id}.json"
        pdf_paths.append(pdf_path)
        if pdf_path.exists() and meta_path.exists():
            continue

        r = requests.get(ARXIV_API, params={"id_list": arxiv_id, "max_results": 1}, timeout=30)
        r.raise_for_status()
        entry = etree.fromstring(r.content).find("a:entry", ATOM_NS)
        if entry is None:
            raise ValueError(f"arXiv không tìm thấy id: {arxiv_id}")

        meta = {
            "paper_id": arxiv_id,
            "title": " ".join(entry.findtext("a:title", "", ATOM_NS).split()),
            "authors": [n.text for n in entry.findall("a:author/a:name", ATOM_NS)],
            "year": int(entry.findtext("a:published", "0000", ATOM_NS)[:4]),
            "abstract": " ".join(entry.findtext("a:summary", "", ATOM_NS).split()),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

        pdf_url = next(
            (l.get("href") for l in entry.findall("a:link", ATOM_NS) if l.get("title") == "pdf"),
            f"https://arxiv.org/pdf/{arxiv_id}",
        )
        pdf = requests.get(pdf_url, timeout=60)
        pdf.raise_for_status()
        pdf_path.write_bytes(pdf.content)
        time.sleep(3)

    return pdf_paths


def fetch_arxiv(keyword: str, category: str = "", max_results: int = 20) -> list[str]:
    """Tìm theo keyword (+category, VD cs.RO) rồi tải — trả về list arXiv id."""
    query = f"all:{keyword}" + (f" AND cat:{category}" if category else "")
    r = requests.get(
        ARXIV_API,
        params={"search_query": query, "max_results": max_results, "sortBy": "submittedDate"},
        timeout=30,
    )
    r.raise_for_status()
    ids = []
    for entry in etree.fromstring(r.content).findall("a:entry", ATOM_NS):
        raw = entry.findtext("a:id", "", ATOM_NS)          # http://arxiv.org/abs/2304.03442v2
        m = re.search(r"abs/([^v]+)", raw)
        if m:
            ids.append(m.group(1))
    fetch_by_ids(ids)
    return ids


def add_local_pdf(pdf_path: Path | str, paper_id: str | None = None,
                  out_dir: Path | None = None) -> str:
    """Đăng ký một PDF ngoài arXiv (journal, Google Scholar, paper mua...) vào kho.

    Copy PDF vào data/papers/ + tạo metadata tối thiểu (title từ tên file — GROBID
    sẽ bóc title thật khi parse, metadata này chỉ là fallback). Trả về paper_id
    dạng "local-<slug>" để dùng với ingest_one / filter / golden set.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Không thấy file: {pdf_path}")
    out_dir = out_dir or config.PAPERS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    paper_id = paper_id or f"local-{_slug(pdf_path.stem)}"
    safe_id = paper_id.replace("/", "_")
    dest = out_dir / f"{safe_id}.pdf"
    if pdf_path.resolve() != dest.resolve():
        shutil.copy(pdf_path, dest)

    meta_path = out_dir / f"{safe_id}.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps({
            "paper_id": paper_id,
            "title": pdf_path.stem.replace("-", " ").replace("_", " "),
            "authors": [], "year": 0, "abstract": "",
        }, ensure_ascii=False, indent=2))
    return paper_id


# ------------------------------------------------------------- GROBID (docker)

def grobid_parse(pdf_path: Path) -> etree._Element:
    """Task 1.2 — POST PDF lên GROBID, trả về TEI XML root.

    Lưu ý: đừng dùng pdf-to-text thường — paper 2 cột sẽ bị trộn dòng.
    """
    with open(pdf_path, "rb") as f:
        r = requests.post(
            f"{config.GROBID_URL}/api/processFulltextDocument",
            files={"input": f},
            timeout=120,
        )
    if r.status_code != 200:
        raise RuntimeError(
            f"GROBID lỗi {r.status_code} với {pdf_path.name} — GROBID đã chạy chưa? (docker compose up -d)"
        )
    return etree.fromstring(r.content)


# ------------------------------------------------- parse TEI (thuần, test được)

def parse_tei(tei: etree._Element, paper_id: str, fallback_meta: dict | None = None) -> Paper:
    """TEI XML -> Paper. `fallback_meta` (JSON từ arXiv) bù khi GROBID thiếu trường."""
    fb = fallback_meta or {}

    title = " ".join(("".join(tei.xpath(".//tei:titleStmt/tei:title//text()", namespaces=TEI_NS))).split())
    authors = []
    for pers in tei.xpath(".//tei:sourceDesc//tei:author/tei:persName", namespaces=TEI_NS):
        name = " ".join("".join(pers.itertext()).split())
        if name:
            authors.append(name)

    year = 0
    when = tei.xpath(".//tei:publicationStmt/tei:date/@when", namespaces=TEI_NS)
    if when and when[0][:4].isdigit():
        year = int(when[0][:4])

    abstract = " ".join(
        " ".join("".join(p.itertext()).split())
        for p in tei.xpath(".//tei:profileDesc/tei:abstract//tei:p", namespaces=TEI_NS)
    ).strip()

    sections: list[Section] = []
    # Chỉ lấy div trong <body> — <back> (References) tự động bị loại
    for i, div in enumerate(tei.xpath(".//tei:text/tei:body/tei:div", namespaces=TEI_NS)):
        head_el = div.find("tei:head", TEI_NS)
        head = " ".join("".join(head_el.itertext()).split()) if head_el is not None else f"Section {i + 1}"
        n = head_el.get("n") if head_el is not None else None
        section_title = f"{n} {head}".strip() if n else head
        paragraphs = [
            " ".join("".join(p.itertext()).split())
            for p in div.findall("tei:p", TEI_NS)
        ]
        paragraphs = [p for p in paragraphs if p]
        if paragraphs:
            sections.append(Section(title=section_title, paragraphs=paragraphs))

    return Paper(
        paper_id=paper_id,
        title=title or fb.get("title", ""),
        authors=authors or fb.get("authors", []),
        year=year or fb.get("year", 0),
        abstract=abstract or fb.get("abstract", ""),
        sections=sections,
    )


# ---------------------------------------------------- chunking (thuần, test được)

def _section_type(section_title: str) -> str:
    low = section_title.lower()
    for stype, keywords in _SECTION_KEYWORDS:
        if any(k in low for k in keywords):
            return stype
    return "other"


def _slug(text: str, max_len: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:max_len] or "section"


def _est_tokens(text: str) -> int:
    """~4 ký tự/token cho chữ Latin; chữ CJK (Nhật/Trung) đặc hơn nhiều (~0.6 token/ký tự)
    — nếu đếm chung len//4 thì đoạn tiếng Nhật 3200 ký tự bị coi là 800 token trong khi
    thực tế ~2000, và không bao giờ được cắt đúng cỡ."""
    ascii_len = sum(1 for c in text if c.isascii())
    return max(1, ascii_len // 4 + int((len(text) - ascii_len) * 0.6))


def _split_long(text: str, max_tokens: int) -> list[str]:
    """Đoạn quá dài mới cắt tiếp — cắt theo câu, gom tới ngưỡng.

    Nhận cả dấu câu CJK (。！？, không có khoảng trắng theo sau) — regex chỉ có
    [.!?]\\s+ sẽ không bao giờ cắt được văn bản tiếng Nhật.
    """
    if _est_tokens(text) <= max_tokens:
        return [text]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|(?<=[。！？])", text) if s.strip()]
    parts, current = [], ""
    for s in sentences:
        if current and _est_tokens(current + " " + s) > max_tokens:
            parts.append(current)
            current = s
        else:
            current = f"{current} {s}".strip()
    if current:
        parts.append(current)
    return parts


def chunk_paper(paper: Paper) -> list[Chunk]:
    """Task 1.3 — structure-aware chunking (quy tắc: README mục 3.3).

    - Đơn vị chunk = đoạn văn trong section; đoạn >800 token mới cắt theo câu.
    - Abstract luôn là một chunk riêng.
    - References/Acknowledgements bị loại (phòng khi lọt vào body).
    """
    common = dict(paper_id=paper.paper_id, title=paper.title, authors=paper.authors, year=paper.year)
    chunks: list[Chunk] = []

    if paper.abstract:
        chunks.append(Chunk(
            chunk_id=f"{paper.paper_id}#abstract#0",
            section="Abstract", section_type="abstract",
            text=paper.abstract,
            parent_section_id=f"{paper.paper_id}#abstract",
            **common,
        ))

    seen_slugs: dict[str, int] = {}
    for section in paper.sections:
        if any(k in section.title.lower() for k in _REFERENCE_HEADS):
            continue  # References gây nhiễu retrieval khủng khiếp — không index
        slug = _slug(section.title)
        seen_slugs[slug] = seen_slugs.get(slug, 0) + 1
        if seen_slugs[slug] > 1:
            slug = f"{slug}-{seen_slugs[slug]}"
        parent_id = f"{paper.paper_id}#{slug}"

        idx = 0
        for paragraph in section.paragraphs:
            for part in _split_long(paragraph, config.MAX_CHUNK_TOKENS):
                chunks.append(Chunk(
                    chunk_id=f"{parent_id}#{idx}",
                    section=section.title,
                    section_type=_section_type(section.title),
                    text=part,
                    parent_section_id=parent_id,
                    **common,
                ))
                idx += 1

    return chunks
