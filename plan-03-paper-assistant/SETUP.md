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

### 3b. Phương án local / free API — chọn tổ hợp trong `.env`

Cả 3 tầng đều có backend thay thế đã code sẵn. Ba tổ hợp khuyên dùng:

| Tổ hợp | `.env` | Chi phí | Chất lượng |
|--------|--------|---------|------------|
| **A. Chất lượng cao** (mặc định) | `EMBED_BACKEND=voyage`, `RERANK_BACKEND=voyage`, `LLM_BACKEND=anthropic` | ~$25-45/tháng | Tốt nhất, citations có cấu trúc |
| **B. Hybrid tiết kiệm** | `EMBED_BACKEND=local`, `RERANK_BACKEND=local`, `LLM_BACKEND=anthropic` | chỉ trả tiền generation | Retrieval gần như không mất gì — **khuyên dùng khi bắt đầu** |
| **C. $0 toàn phần** | như B + `LLM_BACKEND=openai_compat` | $0 | Retrieval tốt; câu trả lời phụ thuộc model local/free — đủ để học RAG, yếu hơn rõ khi tổng hợp/so sánh nhiều paper |

**Backend `local` (tổ hợp B, C):** `bge-m3` (embedding) + `bge-reranker-v2-m3` (rerank) qua sentence-transformers — đa ngôn ngữ Việt/Nhật/Anh tốt, chạy được trên CPU với 10–100 paper (GPU thì nhanh). Lần đầu tải ~2.3GB model/cái về `~/.cache/huggingface`:

```bash
pip install sentence-transformers
```

**Backend `openai_compat` (tổ hợp C):** một endpoint chuẩn OpenAI cho mọi call LLM. Các lựa chọn (giá/giới hạn thay đổi — kiểm tra lại trang của họ):

| Nguồn | `.env` | Ghi chú |
|-------|--------|---------|
| **Ollama** (local, $0) | `OPENAI_COMPAT_BASE_URL=http://localhost:11434/v1`<br>`OPENAI_COMPAT_API_KEY=ollama`<br>`OPENAI_COMPAT_MODEL=qwen2.5:14b` | `ollama pull qwen2.5:14b` trước. 14B cần ~10GB RAM/VRAM (Q4); máy yếu dùng `qwen2.5:7b` (~5GB). Qwen mạnh tiếng Việt hơn Llama cùng cỡ |
| **Groq** (free tier) | `OPENAI_COMPAT_BASE_URL=https://api.groq.com/openai/v1`<br>`OPENAI_COMPAT_API_KEY=gsk_...`<br>`OPENAI_COMPAT_MODEL=llama-3.3-70b-versatile` | Nhanh, 70B free — chất lượng khá; rate limit theo phút |
| **Gemini** (free tier) | `OPENAI_COMPAT_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/`<br>`OPENAI_COMPAT_API_KEY=<key AI Studio>`<br>`OPENAI_COMPAT_MODEL=gemini-2.5-flash` | Free tier rộng rãi; lưu ý free tier có thể dùng data để train — đừng đưa dữ liệu nhạy cảm |
| **LM Studio** (local, $0) | `OPENAI_COMPAT_BASE_URL=http://localhost:1234/v1` | GUI dễ dùng nếu ngại terminal |

#### Sizing phần cứng cho tổ hợp C (tham chiếu: 32GB RAM + RTX 4070 12GB — đủ thoải mái)

| Thành phần | VRAM/RAM | Ghi chú |
|------------|----------|---------|
| `qwen2.5:14b` Q4 | ~9GB VRAM | ~30-40 tok/s trên 4070 — cấu hình chất lượng |
| `qwen2.5:7b` Q4 | ~4.7GB VRAM | 60+ tok/s — cấu hình tốc độ, bge cùng nằm GPU vẫn dư |
| `bge-m3` + `bge-reranker` | ~1.2GB mỗi cái | Chạy CPU cũng đủ nhanh (embed 10-100 paper, rerank 40 đoạn/query) |
| GROBID + Qdrant + hệ thống | ~7GB RAM | CPU |

- GPU ≤ 8GB (VD 4070 laptop): dùng 7B, phần còn lại giữ nguyên.
- Khi 14B + bge tranh GPU: ép bge sang CPU bằng `CUDA_VISIBLE_DEVICES=""` cho process Python, hoặc chấp nhận Ollama tự offload vài layer sang RAM (chậm hơn chút, vẫn chạy).

> ⚠️ **Cạm bẫy Ollama phải né:** mặc định Ollama giới hạn context ~4K token và **cắt phần thừa trong im lặng**. Prompt RAG ở đây dài 10-20K token (6-8 section paper) — không chỉnh thì model không thấy phần lớn nguồn mà không báo lỗi gì, triệu chứng là "trả lời chung chung, lơ nguồn". Khởi động bằng:
> ```bash
> OLLAMA_CONTEXT_LENGTH=16384 ollama serve
> ```
> (14B Q4 + 16K context ≈ 10.5-11GB VRAM — vừa 4070 12GB.)

**Trade-off phải biết khi rời Anthropic backend:** citations API là tính năng riêng của Claude. Với `openai_compat`, hệ thống tự chuyển sang **citation qua prompt** (nguồn đánh số [1][2], trích số từ câu trả lời) — hoạt động được nhưng model có thể ghi nhầm số nguồn, và không có `cited_text` chỉ đúng đoạn được trích. Golden set + eval vẫn chạy bình thường vì chúng đo tầng retrieval (không phụ thuộc LLM backend).

**Mẹo thực dụng:** dev/thử nghiệm bằng tổ hợp C, khi cần câu trả lời chất lượng cho nghiên cứu thật thì chỉ cần đổi `LLM_BACKEND=anthropic` — không phải index lại gì cả (embedding vẫn là bge-m3). Chỉ khi đổi `EMBED_BACKEND` mới phải xóa index (dimension khác nhau) và ingest lại.

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
