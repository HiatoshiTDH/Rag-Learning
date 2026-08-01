"""Task 1.6 — chạy trọn pipeline: python -m src.ingest_all

Đọc data/seed_papers.txt -> tải PDF -> GROBID -> chunk -> index.
Idempotent: PDF/TEI đã có thì dùng lại; upsert không tạo duplicate.
"""

import json
import sys

from lxml import etree

from src import config
from src.embedding import get_embedder
from src.index import delete_paper, get_qdrant, load_chunks, save_metadata, upsert_chunks
from src.ingest import chunk_paper, fetch_by_ids, grobid_parse, parse_tei, read_seed_file


def ingest_one(arxiv_id: str, embedder, client) -> int:
    safe_id = arxiv_id.replace("/", "_")
    pdf_path = config.PAPERS_DIR / f"{safe_id}.pdf"
    tei_path = config.PAPERS_DIR / f"{safe_id}.tei.xml"
    meta_path = config.PAPERS_DIR / f"{safe_id}.json"

    if not pdf_path.exists():
        if arxiv_id.startswith("local-"):
            raise FileNotFoundError(
                f"PDF của paper local {arxiv_id!r} không có trong {config.PAPERS_DIR} "
                f"— thêm lại bằng: python -m src.cli add <đường-dẫn-pdf>"
            )
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

    # So sánh với những gì đã index: giống hệt -> bỏ qua (đỡ tốn tiền embedding);
    # khác (đổi chunking/MAX_CHUNK_TOKENS) -> XÓA SẠCH rồi index lại — nếu chỉ
    # upsert đè, chunk_id mới không trùng chunk_id cũ và rác cũ nằm lại trong
    # Qdrant, làm méo mọi số recall về sau.
    existing = {c["chunk_id"]: c["text"] for c in load_chunks(filters={"paper_id": arxiv_id})}
    fresh = {c.chunk_id: c.text for c in chunks}
    if existing == fresh:
        print(f"  {arxiv_id}: không đổi, bỏ qua ({len(fresh)} chunk đã index)")
        return 0
    if existing:
        delete_paper(arxiv_id, client=client)
        print(f"  {arxiv_id}: chunking đổi — xóa {len(existing)} chunk cũ, index lại")

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
