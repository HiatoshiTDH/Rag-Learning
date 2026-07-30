# Plan 8 — Những thứ cần chuẩn bị (SETUP)

## 1. Phần mềm

| Thứ | Ghi chú |
|-----|---------|
| Python 3.11+ | venv |
| Docker (tùy chọn) | Chỉ cho Qdrant server — bỏ trống `QDRANT_URL` thì dùng embedded mode, không cần docker |
| Game engine (P5) | Unity hoặc Roblox Studio — chỉ cần khi tích hợp, toàn bộ P1–P4 không đụng engine |

Không cần GROBID (khác Plan 3 — không có PDF).

## 2. Services

```bash
docker compose up -d      # chỉ Qdrant; hoặc bỏ qua nếu dùng embedded mode
```

## 3. Backend — cùng hệ với Plan 3

| Tầng | Backend | `.env` |
|------|---------|--------|
| Embedding ký ức | voyage / **local (bge-m3, $0)** / fake | `EMBED_BACKEND` |
| LLM thoại | anthropic (claude-haiku-4-5) / **openai_compat (Ollama...)** | `LLM_BACKEND` |
| LLM reflection | anthropic (claude-sonnet-5) / cùng endpoint openai_compat | tự theo `LLM_BACKEND` |

**Với 32GB RAM + RTX 4070:** tổ hợp $0 chạy tốt — `qwen2.5:14b` cho thoại lẫn reflection,
bge-m3 trên CPU. Thoại NPC cần nhanh: nếu 14B chậm quá so với cảm nhận (mục tiêu <2s
tới token đầu) thì hạ `qwen2.5:7b`. Nhớ cạm bẫy context Ollama (Plan 3 SETUP.md mục 3b):

```bash
OLLAMA_CONTEXT_LENGTH=16384 ollama serve
```

Copy `.env.example` → `.env` và điền theo tổ hợp chọn.

## 4. Chi phí (nếu dùng Claude)

| Khoản | Ước lượng |
|-------|-----------|
| 1 lượt thoại NPC (haiku, ~2K in / 200 out) | ~$0.003 |
| Importance batch 20 sự kiện (haiku) | ~$0.002 |
| 1 lần reflection (sonnet, ~10K in) | ~$0.05 |
| Chơi thử 1 giờ (~50 lượt thoại + 2 reflection) | **~$0.3** |

Prompt caching cho persona (đã bật sẵn trong code) giảm thêm phần lặp lại.

## 5. Checklist Phase 0

- [ ] `pip install -r requirements.txt`
- [ ] `.env` điền xong theo tổ hợp
- [ ] `EMBED_BACKEND=fake LLM_BACKEND=fake python -m pytest tests/ -q` → pass
- [ ] `python -m src.demo` nói chuyện thử được với NPC mẫu (cần LLM thật hoặc Ollama)
