# Plan 3 — Full Plan thực thi (Paper Assistant)

> Tài liệu này là **kế hoạch thực thi chi tiết** — chia phase, task, definition of done, ước lượng giờ.
> Kiến trúc & lý do thiết kế: xem [README.md](README.md). Chuẩn bị môi trường: xem [SETUP.md](SETUP.md).

## Nguyên tắc thực thi

1. **Mỗi phase kết thúc bằng một thứ chạy được** — không có phase nào "chỉ viết code chưa test được".
2. **Golden set có từ Phase 2**, trước khi tối ưu bất cứ thứ gì. Mọi thay đổi sau đó phải có số chứng minh.
3. Làm tuần tự P0 → P5. Trong một phase các task có thể xen kẽ.

## Tổng quan các phase

| Phase | Tên | Thời gian | Kết quả chạy được |
|-------|-----|-----------|-------------------|
| P0 | Chuẩn bị môi trường | 0.5 ngày | GROBID + Qdrant chạy local, API key hoạt động |
| P1 | Ingest pipeline | Tuần 1 | Index 10 paper, soi được chunk đúng section |
| P2 | Query v1 + Golden set | Tuần 2 | Hỏi → trả lời có citation đúng (vector search thuần) |
| P3 | Retrieval nâng cao | Tuần 2–3 | Hybrid + re-rank + parent-doc, recall đo được tăng |
| P4 | Query expansion + multi-paper | Tuần 3 | Hỏi tiếng Việt được; so sánh 2+ paper được |
| P5 | Đóng gói sử dụng hằng ngày | Tuần 4 | CLI + auto-ingest arXiv theo keyword |

---

## P0 — Chuẩn bị môi trường (0.5 ngày)

Checklist chi tiết trong [SETUP.md](SETUP.md). Tóm tắt:

- [ ] `docker compose up -d` → GROBID (8070) + Qdrant (6333) chạy
- [ ] `.env` có `ANTHROPIC_API_KEY` + `VOYAGE_API_KEY` (hoặc chọn phương án local-free)
- [ ] `pip install -r requirements.txt` trong venv
- [ ] Sanity check: curl GROBID trả `GROBID service is up`, mở Qdrant dashboard `localhost:6333/dashboard`
- [ ] Chọn sẵn **10 paper khởi đầu** theo hướng nghiên cứu của bạn (chọn paper đã đọc kỹ — cần cho golden set ở P2)

## P1 — Ingest pipeline (tuần 1, ~12–16h)

| # | Task | File | DoD | Giờ |
|---|------|------|-----|-----|
| 1.1 | Tải paper từ arXiv API theo id/keyword, lưu PDF + metadata | `src/ingest.py::fetch_arxiv` | 10 PDF trong `data/papers/`, metadata JSON kèm theo | 2 |
| 1.2 | Gọi GROBID, parse TEI XML ra cấu trúc (title, sections, paragraphs) | `src/ingest.py::parse_pdf` | In ra được cây section của 1 paper, đúng thứ tự, không lẫn 2 cột | 3 |
| 1.3 | Structure-aware chunking + chuẩn hóa `section_type` | `src/ingest.py::chunk_paper` | Chunk có đủ metadata; abstract là chunk riêng; References bị loại | 4 |
| 1.4 | Embedding batch + upsert Qdrant (payload đầy đủ) | `src/index.py` | Search thử 1 câu trên Qdrant dashboard ra chunk hợp lý | 3 |
| 1.5 | Lưu full-text section vào SQLite (cho parent-doc sau này) | `src/index.py` | Query SQLite theo `parent_section_id` ra đúng section | 2 |
| 1.6 | Script `python -m src.ingest_all` chạy trọn pipeline cho cả thư mục | mới | Chạy 1 lệnh index xong 10 paper, idempotent (chạy lại không duplicate) | 2 |

**Bẫy cần né ở P1** (chi tiết README mục 6): PDF 2 cột, References gây nhiễu, chunk cắt ngang đoạn.

## P2 — Query v1 + Golden set (tuần 2, ~10–14h)

| # | Task | File | DoD | Giờ |
|---|------|------|-----|-----|
| 2.1 | Vector search thuần: embed câu hỏi → top-8 chunk | `src/query.py::hybrid_search` (bản v1) | Trả về chunk + metadata + score | 2 |
| 2.2 | Generation với citations API (document blocks) | `src/answer.py::answer` | Câu trả lời kèm citation trỏ đúng paper/section, render ra text | 4 |
| 2.3 | **Golden set ~30 câu** trên 10 paper đã đọc kỹ | `tests/test_retrieval.py` | Mỗi câu có `expect_paper` (+ `expect_section_type` nếu rõ) | 3 |
| 2.4 | Script đo recall@8 + báo cáo | `tests/` | Chạy `pytest` ra con số baseline, ghi vào `EXPERIMENTS.md` | 2 |
| 2.5 | CLI tối thiểu: `python -m src.ask "câu hỏi"` | mới | Dùng được từ terminal | 1 |

**Cột mốc quan trọng:** con số recall baseline ở 2.4 là thước đo cho toàn bộ P3. Ghi lại cẩn thận.

## P3 — Retrieval nâng cao (tuần 2–3, ~12–16h)

| # | Task | File | DoD | Giờ |
|---|------|------|-----|-----|
| 3.1 | BM25 index trên toàn bộ chunk + RRF gộp với vector | `src/query.py` | Recall@8 ≥ baseline (kỳ vọng tăng với câu hỏi chứa thuật ngữ/tên riêng) | 4 |
| 3.2 | Metadata filter (paper_id, section_type) khi câu hỏi nêu rõ | `src/query.py` | Hỏi "trong paper X..." chỉ search paper X | 2 |
| 3.3 | Re-ranking top-40 → top-8 | `src/query.py::rerank` | Recall@8 tăng so với 3.1, ghi số vào `EXPERIMENTS.md` | 3 |
| 3.4 | Parent-document retrieval (chunk → cả section, dedupe) | `src/query.py::to_parent_sections` | Chất lượng câu trả lời cải thiện trên các câu hỏi "giải thích cách..." | 3 |
| 3.5 | Chạy lại golden set sau mỗi thay đổi, chốt cấu hình tốt nhất | `EXPERIMENTS.md` | Bảng so sánh: v1 / +BM25 / +rerank / +parent-doc | 2 |

## P4 — Query expansion + multi-paper (tuần 3, ~8–12h)

| # | Task | File | DoD | Giờ |
|---|------|------|-----|-----|
| 4.1 | Query expansion: 2–3 biến thể + bản dịch tiếng Anh | `src/query.py::expand_query` | Hỏi tiếng Việt, recall tương đương hỏi tiếng Anh | 3 |
| 4.2 | Map-reduce cho câu so sánh: retrieve/tóm tắt từng paper → tổng hợp | `src/answer.py::compare_papers` | "So sánh cách A và B đo X" ra bảng so sánh có citation cả 2 phía | 4 |
| 4.3 | Router đơn giản: câu hỏi 1-paper vs nhiều-paper vs tổng quan | `src/answer.py` | Tự chọn flow đúng cho 3 loại câu trong golden set | 3 |

## P5 — Đóng gói dùng hằng ngày (tuần 4, ~8–12h)

| # | Task | File | DoD | Giờ |
|---|------|------|-----|-----|
| 5.1 | CLI hoàn chỉnh: `ask`, `ingest`, `list`, `compare` | `src/cli.py` | `--help` đầy đủ, lỗi rõ ràng | 3 |
| 5.2 | Auto-ingest: cron/script quét arXiv theo keyword hằng tuần | mới | Chạy định kỳ, chỉ ingest paper mới (dedupe theo arXiv id) | 3 |
| 5.3 | Prompt caching cho phần hệ thống + tài liệu lặp lại | `src/answer.py` | `cache_read_input_tokens > 0` ở request thứ 2 trở đi | 2 |
| 5.4 | (Tùy chọn) UI web tối giản — chỉ làm nếu CLI thấy thiếu | mới | — | 4 |

---

## Rủi ro & phương án

| Rủi ro | Xác suất | Ảnh hưởng | Phương án |
|--------|----------|-----------|-----------|
| GROBID parse hỏng với một số paper (layout lạ, scan) | Cao | Vừa | Bỏ qua paper lỗi ở v1, log lại; đừng cố xử lý mọi PDF |
| Recall thấp với câu hỏi tiếng Việt | Cao | Cao | 4.1 là bắt buộc, không phải tùy chọn; luôn có bản dịch EN trong biến thể query |
| Chi phí API vượt dự kiến | Thấp | Thấp | Xem bảng chi phí SETUP.md; bật prompt caching (5.3); dev bằng bộ 10 paper nhỏ |
| Bảng số liệu trong paper không trích được | Chắc chắn | Thấp | Chấp nhận ở v1 (ghi rõ giới hạn); nâng cấp bằng vision model sau (giao Plan 11) |
| Tune retrieval bằng cảm tính, không hội tụ | Vừa | Cao | Golden set từ P2 + `EXPERIMENTS.md`; không merge thay đổi nào thiếu số |

## Quyết định kỹ thuật đã chốt (decision log)

| Quyết định | Chọn | Lý do | Xem lại khi |
|-----------|------|-------|-------------|
| Parser PDF | GROBID | Chuyên cho paper học thuật, ra TEI XML có section | GROBID lỗi >20% số paper |
| Vector DB | Qdrant | Payload filtering mạnh, chạy docker local dễ | Cần managed/cloud |
| Embedding | voyage-3 (option: bge-m3 local) | Đa ngôn ngữ, chất lượng tốt | Chi phí thành vấn đề → bge-m3 |
| Re-ranker | voyage-rerank-2 (option: bge-reranker-v2-m3 local) | Cùng hệ sinh thái Voyage | Như trên |
| LLM trả lời | claude-opus-5 | Chất lượng tổng hợp + citations tốt nhất | Cost cao → claude-sonnet-5 cho câu đơn giản |
| Metadata store | SQLite | Đủ cho single-user, zero-config | Nhiều user → Postgres (+pgvector cân nhắc gộp luôn vector) |

## Ngoài phạm vi (chốt để không phình)

- Trích bảng số liệu/hình vẽ (→ Plan 11)
- Citation graph giữa các paper (→ Plan 9)
- Multi-user, phân quyền
- Fine-tune embedding

## Theo dõi thí nghiệm

Tạo `EXPERIMENTS.md` từ P2, mỗi dòng một lần chạy golden set:

```
| Ngày | Cấu hình | recall@8 | Ghi chú |
|------|----------|----------|---------|
| ...  | v1 vector-only | 0.xx | baseline |
| ...  | +BM25 RRF      | 0.xx | ... |
```
