"""Task 1.6 — chạy trọn pipeline: python -m src.ingest_all

Đọc data/seed_papers.txt -> tải PDF -> GROBID -> chunk -> index.
Idempotent: PDF/TEI đã có thì dùng lại; upsert không tạo duplicate.
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

    # Cache kết quả GROBID — parse lại PDF là bước chậm nhất
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
    print(f"  {arxiv_id}: {len(paper.sections)} section, {n} chunk")
    return n


def main() -> None:
    ids = read_seed_file()
    if not ids:
        sys.exit(f"Chưa có paper nào trong {config.SEED_FILE} — thêm arXiv id vào trước (SETUP.md mục 4).")

    embedder = get_embedder()
    client = get_qdrant()
    print(f"Ingest {len(ids)} paper (embedder: {type(embedder).__name__})")

    total, failed = 0, []
    for arxiv_id in ids:
        try:
            total += ingest_one(arxiv_id, embedder, client)
        except Exception as e:  # paper lỗi thì log và đi tiếp — đừng chết cả batch
            failed.append(arxiv_id)
            print(f"  {arxiv_id}: LỖI — {e}")

    print(f"\nXong: {total} chunk. Lỗi: {failed or 'không'}")


if __name__ == "__main__":
    main()
