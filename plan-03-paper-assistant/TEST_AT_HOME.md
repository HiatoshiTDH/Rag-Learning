# Bài test tổng thể khi về máy nhà

Toàn bộ code P1→P5 đã viết xong và pass 26 test offline. Tài liệu này là **thứ tự chạy để verify tổng thể trên máy thật** — làm từ trên xuống, mỗi bước có expected output. Ước lượng: ~30–45 phút (đa số là chờ GROBID parse).

> Đường tắt: `./scripts/smoke_test.sh` tự chạy bước 1→6 và in PASS/FAIL từng mục.

## Bước 0 — Clone & cài đặt (một lần)

```bash
git clone <repo> && cd Rag-Learning/plan-03-paper-assistant
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Bước 1 — Test offline (không cần docker/key)

```bash
EMBED_BACKEND=fake RERANK_BACKEND=fake python -m pytest tests/ -q
```

**Expected:** `26 passed`. Fail ở đây = lỗi code/môi trường Python, chưa liên quan gì tới docker hay API.

## Bước 2 — Dựng services

```bash
docker compose up -d
curl http://localhost:8070/api/isalive     # → true (GROBID cần ~30-60s khởi động lần đầu)
```

Mở http://localhost:6333/dashboard — thấy UI Qdrant là OK.

## Bước 3 — Điền cấu hình

```bash
cp .env.example .env
# Điền: ANTHROPIC_API_KEY (console.anthropic.com), VOYAGE_API_KEY (dash.voyageai.com)
python -c "from src.embedding import get_embedder; get_embedder(); print('Voyage OK')"
```

**Expected:** `Voyage OK`. Nếu muốn thử không tốn tiền embedding trước: `EMBED_BACKEND=fake` (nhưng kết quả search sẽ vô nghĩa về ngữ nghĩa — chỉ để kiểm tra pipeline chạy thông).

## Bước 4 — Ingest thật (P1 live)

Thêm 2–3 arXiv id vào `data/seed_papers.txt` (bắt đầu ít để nhanh), rồi:

```bash
python -m src.cli ingest
```

**Expected:** mỗi paper một dòng `  <id>: N section, M chunk`, kết thúc `Xong: ... chunk. Lỗi: không`.
Kiểm tra chéo:
- `python -m src.cli list` → ra danh sách paper
- Qdrant dashboard → collection `papers` → soi vài point: payload phải có `section`, `section_type` đúng
- Chạy lại `python -m src.cli ingest` lần 2 → **số chunk không tăng** (idempotent)

## Bước 5 — Hỏi thật (P2–P4 live)

```bash
# Câu hỏi thường (router tự xử lý)
python -m src.cli ask "Paper <id> giải quyết vấn đề gì?"

# Giới hạn section
python -m src.cli ask "phương pháp chính là gì?" --paper <id> --section-type method

# So sánh (cần >=2 paper đã ingest)
python -m src.cli compare "hai paper này khác nhau thế nào về cách đánh giá?" <id1> <id2>
```

**Expected:** câu trả lời + mục `Nguồn:` liệt kê `[n] Tên paper — Tên section`. Câu trả lời **không có citation nào** với câu hỏi nội dung = có vấn đề, xem Troubleshooting.

**Chi phí bước này:** vài cent (opus-5). Muốn rẻ khi thử đi thử lại: thêm `--no-expand` và/hoặc `ANSWER_MODEL=claude-sonnet-5` trong `.env`.

## Bước 6 — Golden set + đo baseline (P2.3–2.4)

```bash
cp data/golden_set.example.jsonl data/golden_set.jsonl
# Sửa thành 10-30 câu thật trên paper BẠN đã đọc (tăng dần, 10 câu là đủ để bắt đầu)

python -m src.cli eval --stage v1     --note "baseline vector thuần"
python -m src.cli eval --stage hybrid --note "+BM25/RRF"
python -m src.cli eval --stage rerank --note "+voyage rerank"
python -m src.cli eval --stage full   --note "+expansion"
```

**Expected:** 4 dòng mới trong `EXPERIMENTS.md`, recall tăng dần (hoặc ít nhất không giảm) qua từng stage. Đây chính là task 3.5 — từ giờ mọi thay đổi đều so với các con số này.

## Bước 7 — (Tùy chọn) Auto-ingest hằng tuần (P5.2)

```bash
# Bỏ comment/thêm keyword vào data/watch_keywords.txt rồi:
python -m src.cli watch

# Cron mỗi thứ 2, 8h sáng:
# 0 8 * * 1  cd /path/to/plan-03-paper-assistant && .venv/bin/python -m src.cli watch >> watch.log 2>&1
```

---

## Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|-------------|------------------------|------------|
| GROBID 503 / connection refused | Chưa khởi động xong (lần đầu tải model ~30-60s) | Chờ rồi `curl .../api/isalive` lại |
| GROBID lỗi với 1 paper cụ thể | PDF layout lạ/scan | Bỏ paper đó ra khỏi seed — đúng dự kiến trong PLAN (rủi ro #1) |
| Qdrant lỗi dimension mismatch | Đổi `EMBED_BACKEND` (fake 256 chiều ↔ voyage 1024 chiều) | Xóa collection: `docker compose down && docker volume rm plan-03-paper-assistant_qdrant_storage` (hoặc xóa `data/qdrant/` nếu dùng embedded) rồi ingest lại |
| `anthropic.AuthenticationError` | Key sai/thiếu trong `.env` | Kiểm tra `.env`, nhớ `source .venv/bin/activate` đúng thư mục |
| Voyage 401 | Như trên với `VOYAGE_API_KEY` | — |
| Trả lời không có citation | Câu hỏi ngoài phạm vi kho paper (đúng hành vi: model phải nói "không đề cập") hoặc retrieval trượt | Thử `ask --paper <id>` để khoanh vùng; nếu vẫn trượt → thêm case vào golden set và debug bằng `eval` |
| Hỏi tiếng Việt kết quả kém hơn hẳn tiếng Anh | Expansion chưa chạy (dùng `--no-expand`?) | Bỏ `--no-expand` — bản dịch EN nằm trong expansion |
| `Golden set trống` khi eval | Chưa copy example thành `golden_set.jsonl` | Bước 6 |

## Map sang PLAN.md

| Bước ở trên | Phase trong PLAN | Sau bước này phase được coi là |
|-------------|------------------|--------------------------------|
| 1 | (kiểm tra code) | — |
| 2–3 | P0 | ✅ hoàn tất |
| 4 | P1 | ✅ hoàn tất (phần live còn thiếu) |
| 5 | P2.2/2.5, P3, P4 | ✅ hoàn tất phần code; chất lượng tune tiếp bằng bước 6 |
| 6 | P2.3–2.4 + P3.5 | ✅ baseline có số |
| 7 | P5.2 | ✅ hoàn tất |

Sau khi cả 7 bước pass: dự án ở trạng thái "dùng thật hằng ngày được" — việc còn lại là mở rộng golden set và tune theo số liệu.
