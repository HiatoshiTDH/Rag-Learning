"""P5 (5.2) — Auto-ingest: quét arXiv theo keyword, chỉ ingest paper CHƯA có.

Keyword khai báo trong data/watch_keywords.txt, mỗi dòng:
    <keyword> [| category]
Ví dụ:
    exoskeleton control | cs.RO
    retrieval augmented generation

Chạy tay:  python -m src.cli watch
Cron tuần: 0 8 * * 1  cd /path/to/plan-03-paper-assistant && .venv/bin/python -m src.cli watch
"""

from src import config
from src.embedding import get_embedder
from src.index import get_qdrant, list_papers
from src.ingest import ARXIV_API, ATOM_NS
from src.ingest_all import ingest_one


def read_watch_file() -> list[tuple[str, str]]:
    if not config.WATCH_FILE.exists():
        return []
    entries = []
    for line in config.WATCH_FILE.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        keyword, _, category = (part.strip() for part in line.partition("|"))
        entries.append((keyword, category))
    return entries


def search_ids(keyword: str, category: str, max_results: int = 10) -> list[str]:
    import re

    import requests
    from lxml import etree

    query = f"all:{keyword}" + (f" AND cat:{category}" if category else "")
    r = requests.get(ARXIV_API, params={
        "search_query": query, "max_results": max_results,
        "sortBy": "submittedDate", "sortOrder": "descending",
    }, timeout=30)
    r.raise_for_status()
    ids = []
    for entry in etree.fromstring(r.content).findall("a:entry", ATOM_NS):
        m = re.search(r"abs/([^v]+)", entry.findtext("a:id", "", ATOM_NS))
        if m:
            ids.append(m.group(1))
    return ids


def main() -> None:
    entries = read_watch_file()
    if not entries:
        raise SystemExit(f"Chưa có keyword nào trong {config.WATCH_FILE} — xem docstring file này.")

    existing = {p["paper_id"] for p in list_papers()}
    embedder, client = get_embedder(), get_qdrant()
    new_count = 0

    for keyword, category in entries:
        found = search_ids(keyword, category)
        fresh = [pid for pid in found if pid not in existing]
        print(f'"{keyword}"{f" [{category}]" if category else ""}: '
              f"{len(found)} kết quả, {len(fresh)} mới")
        for pid in fresh:
            try:
                ingest_one(pid, embedder, client)
                existing.add(pid)
                new_count += 1
            except Exception as e:
                print(f"  {pid}: LỖI — {e}")

    print(f"\nIngest thêm {new_count} paper mới.")


if __name__ == "__main__":
    main()
