# Plan 3 — Những thứ cần chuẩn bị (SETUP)

Mọi thứ cần có trước khi bắt đầu P1 trong [PLAN.md](PLAN.md). Làm xong hết phần này = xong Phase 0.

## 1. Phần mềm trên máy

| Thứ | Phiên bản | Ghi chú |
|-----|-----------|---------|
| Python | 3.11+ | dùng venv |
| Docker + Docker Compose | mới nhất | chạy GROBID và Qdrant |
| Git | — | — |
| RAM trống | ~5 GB | GROBID ngốn ~4 GB khi parse |

## 2. Services local (docker compose)

Đã có sẵn [`docker-compose.yml`](docker-compose.yml) trong folder này:

```bash
docker compose up -d

# Sanity check
curl http://localhost:8070/api/isalive     # GROBID → true
# Qdrant dashboard: mở http://localhost:6333/dashboard
```

| Service | Port | Vai trò |
|---------|------|---------|
| GROBID | 8070 | Parse PDF học thuật → TEI XML |
| Qdrant | 6333 (HTTP) / 6334 (gRPC) | Vector DB, data lưu ở volume `qdrant_storage` |

## 3. API keys

Copy [`.env.example`](.env.example) thành `.env` rồi điền:

| Key | Lấy ở đâu | Dùng cho |
|-----|-----------|----------|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys | Generation (trả lời + citations), query expansion |
| `VOYAGE_API_KEY` | dash.voyageai.com | Embedding (`voyage-3`) + re-rank (`voyage-rerank-2`) |

### Phương án local-free (không cần Voyage)

Nếu muốn tránh chi phí embedding hoặc muốn dữ liệu không rời máy:

- Embedding: `bge-m3` qua `sentence-transformers` (mạnh cho đa ngôn ngữ Việt/Nhật/Anh)
- Re-rank: `bge-reranker-v2-m3`
- Cần thêm: `pip install sentence-transformers` (+ GPU thì nhanh, CPU vẫn chạy được với 10–100 paper)
- Đánh đổi: chậm hơn khi index lớn, chất lượng nhỉnh hơn/kém hơn tùy domain — golden set (P2) sẽ cho câu trả lời khách quan

Vẫn cần `ANTHROPIC_API_KEY` cho phần generation.

## 4. Dữ liệu khởi đầu

- **10 paper bạn đã đọc kỹ**, cùng hướng nghiên cứu (robotics / human augmentation / SRL...).
  - Vì sao phải là paper đã đọc kỹ: golden set ở P2 cần bạn biết đáp án đúng nằm ở paper nào, section nào.
- Ghi list arXiv id vào một file text (VD `data/seed_papers.txt`) — script 1.1 sẽ đọc từ đây.

## 5. Chi phí ước lượng

> Giá tham khảo thời điểm viết — kiểm tra lại trang giá của từng nhà cung cấp trước khi chạy lớn.

| Khoản | Ước lượng | Ghi chú |
|-------|-----------|---------|
| Embedding 100 paper (~1.5M token) | < $0.5 | voyage-3; chỉ tốn 1 lần khi index. Bản local-free: $0 |
| Re-rank | không đáng kể | tính theo token cặp query-document |
| 1 câu hỏi thường (6–8 section context, ~15K token in) | ~$0.08–0.15 | claude-opus-5 ($5/M in, $25/M out) |
| 1 câu so sánh multi-paper (map-reduce) | ~$0.3–0.5 | nhiều call hơn |
| **Cả tháng dùng cá nhân (~10 câu/ngày)** | **~$25–45** | giảm mạnh nếu bật prompt caching + dùng sonnet-5 cho câu đơn giản |

Mẹo giảm chi phí khi dev: làm việc trên bộ 10 paper, bật prompt caching sớm (task 5.3 có thể kéo lên làm ngay ở P2 nếu muốn), dùng `claude-sonnet-5` ($3/$15) hoặc `claude-haiku-4-5` ($1/$5) khi thử pipeline — chỉ chuyển opus khi đánh giá chất lượng thật.

## 6. Thứ tự khởi động lại từ đầu (mỗi phiên làm việc)

```bash
cd plan-03-paper-assistant
docker compose up -d          # GROBID + Qdrant
source .venv/bin/activate
# làm việc theo task đang mở trong PLAN.md
```

## 7. Checklist Phase 0 hoàn tất

- [ ] `docker compose up -d` chạy, 2 sanity check pass
- [ ] `.env` điền xong, `python -c "import anthropic, voyageai"` không lỗi
- [ ] Đã quyết định: Voyage hay local-free (ghi vào decision log trong PLAN.md nếu đổi)
- [ ] `data/seed_papers.txt` có 10 arXiv id
- [ ] Đọc mục 6 (bẫy đã biết) trong [README.md](README.md) một lần
