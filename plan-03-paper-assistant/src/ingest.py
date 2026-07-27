"""P1 — Ingest: arXiv -> PDF -> GROBID -> TEI XML -> structured chunks.

Start GROBID before using the PDF-parsing part:
    docker compose up -d      # see SETUP.md

Three separate layers so each can be tested on its own:
  fetch_*        : network (arXiv)         — needs internet
  grobid_parse   : network (local GROBID)  — needs docker
  parse_tei/chunk: pure data               — tested offline via fixtures
"""

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests
from lxml import etree

from src import config

ARXIV_API = "https://export.arxiv.org/api/query"
TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}

# Normalize section titles to fixed types so queries can filter on them
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
    section_type: str      # one of SECTION_TYPES
    text: str
    parent_section_id: str # for parent-document retrieval


# -------------------------------------------------------------- fetch (network)

def read_seed_file(path: Path | None = None) -> list[str]:
    """Read data/seed_papers.txt — skip blank lines and comments (#)."""
    path = path or config.SEED_FILE
    ids = []
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            ids.append(line)
    return ids


def fetch_by_ids(arxiv_ids: list[str], out_dir: Path | None = None) -> list[Path]:
    """Task 1.1 — download PDF + metadata JSON for each arXiv id.

    Idempotent: ids that already have a PDF are skipped. Be polite to arXiv:
    sleep 3s between downloads.
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
            raise ValueError(f"arXiv id not found: {arxiv_id}")

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
    """Search by keyword (+category, e.g. cs.RO) then download — returns arXiv ids."""
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


# ------------------------------------------------------------- GROBID (docker)

def grobid_parse(pdf_path: Path) -> etree._Element:
    """Task 1.2 — POST the PDF to GROBID, return the TEI XML root.

    Note: don't use plain pdf-to-text — two-column papers get their lines interleaved.
    """
    with open(pdf_path, "rb") as f:
        r = requests.post(
            f"{config.GROBID_URL}/api/processFulltextDocument",
            files={"input": f},
            timeout=120,
        )
    if r.status_code != 200:
        raise RuntimeError(
            f"GROBID error {r.status_code} on {pdf_path.name} — is GROBID running? (docker compose up -d)"
        )
    return etree.fromstring(r.content)


# ------------------------------------------------ parse TEI (pure, testable)

def parse_tei(tei: etree._Element, paper_id: str, fallback_meta: dict | None = None) -> Paper:
    """TEI XML -> Paper. `fallback_meta` (arXiv JSON) fills fields GROBID missed."""
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
    # Only take divs inside <body> — <back> (References) is dropped automatically
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


# --------------------------------------------------- chunking (pure, testable)

def _section_type(section_title: str) -> str:
    low = section_title.lower()
    for stype, keywords in _SECTION_KEYWORDS:
        if any(k in low for k in keywords):
            return stype
    return "other"


def _slug(text: str, max_len: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:max_len] or "section"


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _split_long(text: str, max_tokens: int) -> list[str]:
    """Only overly long paragraphs get split further — by sentence, packed to the limit."""
    if _est_tokens(text) <= max_tokens:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
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
    """Task 1.3 — structure-aware chunking (rules: README section 3.3).

    - Chunk unit = a paragraph within a section; only paragraphs >800 tokens
      get split by sentence.
    - The abstract is always its own chunk.
    - References/Acknowledgements are dropped (in case they leak into the body).
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
            continue  # References wreck retrieval with noise — never index them
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
