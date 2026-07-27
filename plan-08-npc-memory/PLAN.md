# Plan 8 — Full Plan thực thi (NPC Memory RAG)

> Tài liệu này là **kế hoạch thực thi chi tiết** — chia phase, task, definition of done.
> Kiến trúc & lý do thiết kế: xem [README.md](README.md). Chuẩn bị môi trường: [SETUP.md](SETUP.md).

> **📍 TRẠNG THÁI HIỆN TẠI: code P1→P5 đã viết xong, 30 test offline pass.**
> Việc còn lại làm trên máy nhà (cần API key + mạng):
> chạy theo **[TEST_AT_HOME.md](TEST_AT_HOME.md)** — bài B1 live có sẵn `python -m scripts.demo_b1`.
> Phần chưa code: nối vào game thật (P6 — cần project Unity/Roblox) và memory chia sẻ giữa NPC (B4, xem Ngoài phạm vi).

## Nguyên tắc thực thi

1. **Offline-first** — mọi cơ chế lõi test được bằng `pytest` không cần key/docker/game
   (HashEmbedder + Qdrant in-memory + ScriptedLLM). Key thật chỉ cần khi đo *chất lượng*.
2. **Test trí nhớ như test code** (README mục 7) — 4 kịch bản B1/B2/B3 + injection nằm trong
   `tests/test_memory.py`; đổi trọng số α/β/γ hay ngưỡng reflection thì chạy lại bộ này.
3. **LLM không bao giờ quyết định gameplay** — mọi hệ quả qua `propose_game_action` +
   `validate_action` phía server, mặc định DENY.

## Tổng quan các phase

| Phase | Tuần (README) | Tên | Trạng thái | Kết quả chạy được |
|-------|---------------|-----|------------|-------------------|
| P0 | — | Chuẩn bị môi trường | ✅ (xem SETUP.md) | `pytest` xanh trên máy trần, không cần docker |
| P1 | 1 | Memory stream: schema + ghi/đọc + vector search | ✅ code + test | Ghi 31 ký ức, retrieve đúng, scope theo npc_id |
| P2 | 2 | Retrieval 3 trục + test harness B1 | ✅ code + test | B1 pass: lời hứa thắng 30 sự kiện nhiễu |
| P3 | 3 | Memory service (FastAPI) + streaming + prefetch + fallback | ✅ code + test | WS `/talk` stream từng mẩu; timeout → canned line |
| P4 | 4 | Importance scoring + trạng thái quan hệ | ✅ code + test | B2: trộm đồ → affinity âm → giá nhân 1.15–1.3 |
| P5 | 5–6 | Reflection worker | ✅ code + test | B3 pass; nhận định bắt buộc có source_ids |
| P6 | 7–8 | Nối game thật + hardening live + tune | ⬜ máy nhà / project game | Xem TEST_AT_HOME.md |

---

## P1 — Memory stream (tuần 1)

| # | Task | File | DoD | Trạng thái |
|---|------|------|-----|-----------|
| 1.1 | Schema `MemoryRecord` + helper `MemoryRecord.new` | `src/memory_store.py` | id/timestamp tự sinh, participants + source_ids | ✅ |
| 1.2 | `MemoryStore.add`: embed + SQLite + Qdrant upsert, idempotent | `src/memory_store.py` | chạy 2 lần không duplicate | ✅ |
| 1.3 | `candidates()`: vector search top-50, **scope theo npc_id** | `src/memory_store.py` | test no-leak pass | ✅ |
| 1.4 | `touch()`: ký ức được retrieve thì last_accessed tươi lại | `src/memory_store.py` | `test_retrieval_refreshes_memory` | ✅ |
| 1.5 | Embedder 2 backend: voyage (thật) / hash (offline) | `src/embedding.py` | đổi qua env `EMBED_BACKEND` | ✅ |

## P2 — Retrieval 3 trục (tuần 2)

| # | Task | File | DoD | Trạng thái |
|---|------|------|-----|-----------|
| 2.1 | `score = α·recency + β·importance + γ·relevance`, decay 0.995^giờ | `src/scoring.py` | unit test số học pass | ✅ |
| 2.2 | `retrieve()`: chấm 3 trục trên top-50, trả 8–15, tự touch | `src/scoring.py` | `test_retrieve_ranks_and_touches_only_top` | ✅ |
| 2.3 | Kịch bản B1 trong test harness | `tests/test_memory.py` | lời hứa (5h, imp 8) thắng 30 nhiễu (0.5h, imp 2) | ✅ |
| 2.4 | Kịch bản quan-trọng-thắng-vặt-vãnh | `tests/test_memory.py` | imp 9 (72h trước) thắng imp 1 (3 phút trước) | ✅ |
| 2.5 | Tune α/β/γ theo game feel với embedding thật | — | làm ở P6, có số ghi lại | ⬜ |

## P3 — Memory service + dialogue (tuần 3)

| # | Task | File | DoD | Trạng thái |
|---|------|------|-----|-----------|
| 3.1 | System prompt: persona + luật chống injection, `cache_control` block cuối | `src/dialogue.py` | test prompt caching + rules | ✅ |
| 3.2 | `respond()`: stream từng mẩu text, tool_use qua validate | `src/dialogue.py` | generator event `text`/`action`/`fallback` | ✅ |
| 3.3 | Canned fallback theo quan hệ khi API lỗi/timeout | `src/dialogue.py` | `test_timeout_falls_back...`; NPC không bao giờ đơ | ✅ |
| 3.4 | `validate_action`: whitelist item/quest, giới hạn ±giá, DENY mặc định | `src/dialogue.py` | test injection: 9999 vàng bị chặn | ✅ |
| 3.5 | FastAPI: `POST /event`, `POST /prefetch`, `WS /talk`, log hội thoại | `src/server.py` | TestClient + websocket test pass | ✅ |
| 3.6 | Wrapper LLM inject được + `ScriptedLLM` cho test | `src/llm.py` | mọi test offline không gọi mạng | ✅ |

## P4 — Importance + quan hệ (tuần 4)

| # | Task | File | DoD | Trạng thái |
|---|------|------|-----|-----------|
| 4.1 | Bảng `FIXED_IMPORTANCE` cho event có loại rõ — khỏi gọi LLM | `src/scoring.py` | gift=7, attack=9 không có LLM call | ✅ |
| 4.2 | Chấm batch 10–20 event/call bằng Haiku + structured output, kẹp 1–10 | `src/scoring.py` | 1 call cho cả batch, 42 → 10 | ✅ |
| 4.3 | `RelationshipTracker`: affinity cộng dồn từ bảng delta cứng | `src/relationship.py` | B2: gift +2, attack −6 → cold | ✅ |
| 4.4 | Nhãn quan hệ vào prompt thoại + hệ số giá cho game server | `src/relationship.py`, `src/dialogue.py` | `PRICE_MULTIPLIER[cold] = 1.15` | ✅ |

## P5 — Reflection worker (tuần 5–6)

| # | Task | File | DoD | Trạng thái |
|---|------|------|-----|-----------|
| 5.1 | Trigger: tổng importance ký ức mới ≥ 150 (watermark = reflection cuối) | `src/reflection.py` | 144 → False, 152 → True; reflect xong reset | ✅ |
| 5.2 | 3 bước: câu hỏi cấp cao → retrieve → nhận định (Sonnet) | `src/reflection.py` | B3 pass trong harness | ✅ |
| 5.3 | Chống bịa: LLM trả **chỉ số** nguồn, mình map sang id; không nguồn → bỏ | `src/reflection.py` | `test_insight_without_sources_is_dropped` | ✅ |
| 5.4 | Endpoint `POST /reflect` (worker/cron gọi định kỳ) | `src/server.py` | test forced reflect pass | ✅ |

## P6 — Máy nhà + game thật (tuần 7–8) — CÒN LẠI

| # | Task | DoD |
|---|------|-----|
| 6.1 | Chạy [TEST_AT_HOME.md](TEST_AT_HOME.md): offline suite → server live → `scripts/demo_b1` | B1 live PASS với embedding + LLM thật |
| 6.2 | Tune α/β/γ + top_k với voyage-3 thật (HashEmbedder không nói lên chất lượng) | Ghi bảng số vào `EXPERIMENTS.md` như Plan 3 |
| 6.3 | Nối 1 NPC vào game (Unity: UnityWebRequest/WebSocket; Roblox: HttpService) | Nói chuyện trong game < 2s độ trễ cảm nhận |
| 6.4 | Prefetch theo trigger radius + đo cache_read_input_tokens > 0 từ turn 2 | Xem lưu ý Haiku 4096 token trong TEST_AT_HOME |
| 6.5 | Kiểm thử phá hoại bằng tay (injection đủ kiểu) trên LLM thật | Không action nào được chấp nhận; log đầy đủ |

---

## Rủi ro & phương án

| Rủi ro | Xác suất | Ảnh hưởng | Phương án |
|--------|----------|-----------|-----------|
| Thoại > 2s làm hỏng game feel | Vừa | Cao | Streaming + prefetch đã code; đo thật ở 6.3, cần nữa thì rút top_k, rút persona |
| Retrieval tune bằng HashEmbedder không phản ánh voyage thật | Chắc chắn | Vừa | HashEmbedder chỉ để test cơ chế; tune chất lượng bắt buộc làm ở 6.2 với key thật |
| LLM bị dụ đề xuất action bậy | Cao | Thấp | validate DENY mặc định đã chặn hệ quả; còn lại là vấn đề thoại — hardening 6.5 |
| Stream phình vô hạn | Vừa | Vừa | Reflection đã nén; việc hạ cấp/xóa ký ức vụn cũ để mở rộng sau (chưa cần ở quy mô test) |
| Chi phí API khi nhiều NPC | Vừa | Vừa | Bảng FIXED_IMPORTANCE + batch scoring + chỉ 3–10 NPC chủ chốt dùng RAG (README 5.2) |

## Quyết định kỹ thuật đã chốt (decision log)

| Quyết định | Chọn | Lý do | Xem lại khi |
|-----------|------|-------|-------------|
| Vector DB | Qdrant embedded (không docker) | Đủ cho 1 máy dev; cùng hệ Plan 3 | Nhiều game server → Qdrant server (`QDRANT_URL`) |
| Record store | SQLite cạnh Qdrant | Update `last_accessed` + query reflection dễ | Nhiều instance service → Postgres |
| Embedding | voyage-3 (fake: hash) | Đa ngôn ngữ — ký ức ghi tiếng Việt | Cost → bge-m3 local |
| LLM thoại + chấm điểm | claude-haiku-4-5 | Nhanh nhất, đủ cho thoại NPC ngắn | Thoại nhạt → thử sonnet cho NPC chủ chốt |
| LLM reflection | claude-sonnet-5 | Chạy nền, cần chất lượng nhận định | Cost → hạ tần suất reflect trước khi hạ model |
| Importance khi thiếu LLM | Bảng cứng + mặc định 3 | Service không chết khi LLM_BACKEND=none | — |
| Nguồn của reflection | LLM trả chỉ số, code map sang id | LLM echo id dài hay sai; chỉ số + tự map chắc hơn | — |
| Validate action | Whitelist + DENY mặc định | Người chơi chắc chắn sẽ dụ NPC tặng đồ | — |

## Ngoài phạm vi (chốt để không phình)

- **B4 — memory chia sẻ giữa NPC** (tin đồn lan truyền): làm sau khi B1–B3 chạy tốt trong game thật
- Planning layer (lịch trình ngày của NPC) — README mục 9
- Hạ cấp/xóa ký ức vụn đã nén (cần khi stream thật sự phình)
- Code phía game engine (Unity C#/Roblox Lua) — repo này chỉ có memory service
- Multi-tenant / nhiều game server dùng chung service
