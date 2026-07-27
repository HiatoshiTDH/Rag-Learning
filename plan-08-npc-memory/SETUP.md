# Plan 8 — Chuẩn bị môi trường

Nhẹ hơn Plan 3: **không cần docker** (Qdrant chạy embedded mode ngay trong
process, lưu ở `data/qdrant`). Chỉ cần Python 3.11+ và (khi chạy live) 2 API key.

## 1. Python

```bash
cd plan-08-npc-memory
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Chạy offline (không key) — verify ngay

```bash
python -m pytest tests/ -q        # kỳ vọng: 30 passed
```

Bộ test tự ép `EMBED_BACKEND=fake` + `LLM_BACKEND=none`, không gọi mạng.

Muốn chạy **server** offline (NPC chỉ trả canned line, nhưng ghi/đọc ký ức đầy đủ):

```bash
EMBED_BACKEND=fake LLM_BACKEND=none uvicorn src.server:app --port 8080
```

## 3. API key (khi chạy live)

```bash
cp .env.example .env   # rồi điền:
```

| Key | Lấy ở đâu | Dùng cho |
|-----|-----------|----------|
| `ANTHROPIC_API_KEY` | console.anthropic.com | Thoại (Haiku), chấm importance (Haiku), reflection (Sonnet), judge |
| `VOYAGE_API_KEY` | dash.voyageai.com | Embedding ký ức + câu hỏi (voyage-3, đa ngôn ngữ) |

**Chi phí ước lượng khi dev** (vài trăm lượt thoại/ngày): Haiku 4.5 $1/$5 per MTok,
mỗi lượt thoại ~1–2K token vào + ~100 token ra → cỡ vài cent/ngày. Reflection
(Sonnet 5) chỉ chạy khi tích đủ importance ≥ 150 — vài lần/ngày chơi. Embedding
voyage-3 rẻ không đáng kể ở quy mô này. Prompt caching: xem lưu ý Haiku trong
TEST_AT_HOME mục 5.

## 4. Qdrant server (tùy chọn, chưa cần)

Embedded mode đủ cho toàn bộ plan. Chỉ khi muốn nhiều process dùng chung index:

```bash
docker run -p 6333:6333 -v $(pwd)/data/qdrant-server:/qdrant/storage qdrant/qdrant
# .env: QDRANT_URL=http://localhost:6333
```

**Lưu ý:** đổi `EMBED_BACKEND` (fake ↔ voyage) là đổi số chiều vector —
xóa `data/qdrant/` để index lại, đừng trộn hai loại vector trong một collection.

## 5. Cấu trúc thư mục sau khi chạy

```
data/
├── personas.example.json  # 2 NPC mẫu (commit) — copy thành personas.json để sửa
├── personas.json          # persona game của bạn (gitignore; chưa có thì dùng file mẫu)
├── memories.sqlite        # record ký ức + quan hệ (tự tạo)
├── qdrant/                # vector index embedded (tự tạo)
└── dialogue_log.jsonl     # log toàn bộ hội thoại (tự tạo — soi khai thác/injection)
```
