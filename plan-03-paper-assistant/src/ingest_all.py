"""Task 1.6 — run the full pipeline: python -m src.ingest_all

Reads data/seed_papers.txt -> download PDFs -> GROBID -> chunk -> index.
Idempotent: existing PDF/TEI files are reused; upserts create no duplicates.
"""

import json
import sys

from lxml import etree

from src import config
from src.embedding import get_embedder
from src.index import get_qdrant, save_metadata, upsert_chunks
from src.ingest import chunk_paper, fetch_by_ids, grobid_parse, parse_tei, read_seed_file


def ingest_one(arxiv_id: str, embedder, client) -> int:
    safe_id = arxiv_id.replace("/", "_")
    pdf_path = config.PAPERS_DIR / f"{safe_id}.pdf"
    tei_path = config.PAPERS_DIR / f"{safe_id}.tei.xml"
    meta_path = config.PAPERS_DIR / f"{safe_id}.json"

    if not pdf_path.exists():
        fetch_by_ids([arxiv_id])

    # Cache the GROBID result — re-parsing the PDF is the slowest step
    if tei_path.exists():
        tei = etree.fromstring(tei_path.read_bytes())
    else:
        tei = grobid_parse(pdf_path)
        tei_path.write_bytes(etree.tostring(tei))

    fallback = json.loads(meta_path.read_text()) if meta_path.exists() else None
    paper = parse_tei(tei, paper_id=arxiv_id, fallback_meta=fallback)
    chunks = chunk_paper(paper)

    save_metadata(paper, chunks)
    n = upsert_chunks(chunks, embedder=embedder, client=client)
    print(f"  {arxiv_id}: {len(paper.sections)} sections, {n} chunks")
    return n


def main() -> None:
    ids = read_seed_file()
    if not ids:
        sys.exit(f"No papers in {config.SEED_FILE} yet — add arXiv ids first (SETUP.md section 4).")

    embedder = get_embedder()
    client = get_qdrant()
    print(f"Ingesting {len(ids)} papers (embedder: {type(embedder).__name__})")

    total, failed = 0, []
    for arxiv_id in ids:
        try:
            total += ingest_one(arxiv_id, embedder, client)
        except Exception as e:  # log a bad paper and move on — don't kill the batch
            failed.append(arxiv_id)
            print(f"  {arxiv_id}: ERROR — {e}")

    print(f"\nDone: {total} chunks. Errors: {failed or 'none'}")


if __name__ == "__main__":
    main()
