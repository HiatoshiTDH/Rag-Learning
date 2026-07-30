# Plan 8 — Full Plan thực thi (NPC Memory)

> Kế hoạch thực thi chi tiết. Kiến trúc & lý do thiết kế: [README.md](README.md).
> Chuẩn bị môi trường: [SETUP.md](SETUP.md). Test khi về máy: [TEST_AT_HOME.md](TEST_AT_HOME.md).

> **📍 TRẠNG THÁI HIỆN TẠI: code P0→P4 đã viết xong offline-first (memory service,
> retrieval 3 trục, importance, reflection, dialogue chống injection, FastAPI, demo CLI).**
> Việc còn lại cần máy thật: chạy live với LLM thật (TEST_AT_HOME.md) và tích hợp
> vào game engine (P5 — cần project Unity/Roblox của bạn).

## Nguyên tắc thực thi

1. **Memory service phát triển và test độc lập với game** — engine chỉ là client HTTP.
2. Trọng số retrieval (α/β/γ) và ngưỡng reflection là **tham số config**, tune bằng
   test harness chứ không sửa code.
3. **LLM không bao giờ quyết định hệ quả gameplay** — mọi action qua schema + server validate.

## Tổng quan các phase

| Phase | Tên | Tương ứng tuần trong README | Kết quả chạy được |
|-------|-----|------------------------------|-------------------|
| P0 | Môi trường + hạ tầng backend | — | Qdrant + .env + embedding/llm đa backend |
| P1 | Memory store + retrieval 3 trục | Tuần 1–2 | Ghi 50 ký ức, retrieve đúng theo 3 trục (test) |
| P2 | Importance + reflection | Tuần 4–6 | B2, B3 pass trong test harness |
| P3 | Dialogue + action validation + server | Tuần 3 + 7–8 (phần hardening) | Demo CLI nói chuyện được, injection bị chặn |
| P4 | Test harness B1–B5 + demo | Tuần 7–8 | Toàn bộ kịch bản pass offline |
| P5 | Tích hợp game engine | Tuần 3 | NPC trong game < 2s độ trễ cảm nhận |

Khác thứ tự tuần trong README: dialogue+server (P3) làm **trước** khi tích hợp game,
vì bạn đang thiết kế trước — mọi thứ phải verify được bằng demo CLI không cần engine.

## P1 — Memory store + retrieval (tuần 1–2)

| # | Task | File | DoD |
|---|------|------|-----|
| 1.1 | Schema MemoryRecord + SQLite + Qdrant (embedded fallback) | `src/memory_store.py` | Ghi/đọc record, vector search scope theo npc_id |
| 1.2 | `candidates()` vector top-50 + `touch()` cập nhật last_accessed | `src/memory_store.py` | Test pass |
| 1.3 | Retrieval 3 trục: α·recency + β·importance + γ·relevance | `src/scoring.py` | "Quan trọng thắng vặt vãnh", "nhớ qua nhiễu" pass |

## P2 — Importance + reflection (tuần 4–6 gộp lên)

| # | Task | File | DoD |
|---|------|------|-----|
| 2.1 | Bảng FIXED_IMPORTANCE + LLM batch scoring (inject được) | `src/scoring.py` | Sự kiện có loại → không tốn LLM call; batch parse bền |
| 2.2 | `should_reflect` theo tổng importance từ lần reflect trước | `src/reflection.py` | Ngưỡng config được |
| 2.3 | `reflect()` 3 bước, record type=reflection BẮT BUỘC có source_ids | `src/reflection.py` | B3 pass với fake LLM |

## P3 — Dialogue + server (tuần 3 + hardening tuần 7–8)

| # | Task | File | DoD |
|---|------|------|-----|
| 3.1 | System prompt: persona + luật chống injection + cache_control | `src/dialogue.py` | Test cấu trúc prompt |
| 3.2 | Tool `propose_game_action` + **server-side validate** theo luật game | `src/dialogue.py` | "9999 vàng" bị chặn ở validate, không tới game |
| 3.3 | `respond()` đa backend (Claude haiku / openai_compat cho Ollama) | `src/dialogue.py` | Demo CLI chạy với cả 2 backend |
| 3.4 | FastAPI: POST event / prefetch / talk / reflect | `src/server.py` | TestClient pass; game engine chỉ cần gọi HTTP |
| 3.5 | Demo CLI: hội thoại + xem ký ức, không cần game | `src/demo.py` | Chạy được ở nhà ngay sau `.env` |

## P4 — Test harness B1–B5 (offline, fake backend)

| Kịch bản (README mục 1) | Test |
|--------------------------|------|
| B1 nhớ lời hứa qua 30 sự kiện nhiễu | `test_remembers_promise_after_noise` |
| B2 quan trọng thắng chuyện vặt gần | `test_important_beats_recent_trivia` |
| B3 reflection ra nhận định có nguồn | `test_reflection_forms_opinion` |
| B5 recency decay hoạt động | `test_recency_decay` |
| Không leak giữa NPC | `test_no_leak_across_npcs` |
| Injection không cho đồ | `test_injection_does_not_grant_items` |

## P5 — Tích hợp game (làm khi có project engine, xem README mục 5)

- Unity: UnityWebRequest POST tới server, coroutine/async — KHÔNG gọi trên main thread sync.
- Roblox: HttpService, server-side script (client không bao giờ giữ endpoint).
- Prefetch khi player vào trigger radius; fallback thoại canned khi timeout.
- Streaming (SSE/WS) nâng cấp sau khi HTTP thường chạy ổn — đo độ trễ cảm nhận trước.

## Rủi ro & phương án

| Rủi ro | Phương án |
|--------|-----------|
| Trọng số α/β/γ sai làm NPC "ngớ ngẩn" | Tune bằng test harness + demo CLI, không tune trong game |
| LLM local (Qwen) tuân thủ tool schema kém hơn Claude | validate là chốt chặn cuối — action sai schema bị từ chối, NPC chỉ nói không làm |
| Reflection chạy tốn tiền/chậm | Trigger theo ngưỡng importance, không theo thời gian thực; batch |
| Stream memory phình | Reflection nén + hạ cấp ký ức vụn đã nén (P2.3) |

## Quyết định kỹ thuật (decision log)

| Quyết định | Chọn | Lý do |
|-----------|------|-------|
| Giao tiếp game↔service | HTTP JSON (v1), streaming sau | Testable bằng curl/TestClient, engine nào cũng gọi được |
| Vector DB | Qdrant (embedded fallback) | Đồng bộ với Plan 3, filter npc_id |
| Model thoại | claude-haiku-4-5 / Ollama qwen2.5 | Latency; đổi qua env |
| Model reflection | claude-sonnet-5 / cùng model local | Chạy nền, không cần nhanh |
| Action gameplay | Tool schema + validate server-side | LLM đề xuất, luật game quyết định |
