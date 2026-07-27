# Rag-Learning — Danh sách các Plan sử dụng RAG nhiều

Tài liệu này liệt kê các dự án/plan mà **hệ thống RAG (Retrieval-Augmented Generation) là trái tim của sản phẩm** — không phải tính năng phụ. Mỗi plan đều ghi rõ: vì sao RAG được dùng nặng, kỹ thuật RAG nào sẽ học được, stack gợi ý và độ khó. Sắp xếp từ dễ đến khó để có thể dùng luôn làm lộ trình học.

## Bảng tổng quan

| # | Plan | Mức độ dùng RAG | Độ khó | Kỹ thuật chính |
|---|------|-----------------|--------|----------------|
| 1 | Chatbot hỏi đáp tài liệu cá nhân (PDF/notes) | ★★★☆☆ | Dễ | Chunking, embedding, vector search |
| 2 | Trợ lý wiki/tài liệu nội bộ công ty | ★★★★☆ | Dễ–Vừa | Hybrid search, metadata filtering |
| 3 | Trợ lý đọc & tra cứu paper nghiên cứu | ★★★★☆ | Vừa | Citation, chunking văn bản học thuật |
| 4 | Code assistant trên codebase riêng | ★★★★☆ | Vừa | Code chunking (AST), re-ranking |
| 5 | Customer support bot với knowledge base | ★★★★☆ | Vừa | Query rewriting, feedback loop |
| 6 | Trợ lý pháp lý / quy định / hợp đồng | ★★★★★ | Vừa–Khó | Grounding, citation bắt buộc, chống hallucination |
| 7 | Second brain cá nhân (Obsidian/Notion) | ★★★★☆ | Vừa | Incremental indexing, temporal retrieval |
| 8 | NPC game có trí nhớ dài hạn | ★★★★★ | Khó | Memory RAG, retrieval theo thời gian + độ quan trọng |
| 9 | GraphRAG / Multi-hop QA trên kho tri thức | ★★★★★ | Khó | Knowledge graph, multi-hop reasoning |
| 10 | Agentic RAG — agent tự quyết định khi nào retrieve | ★★★★★ | Khó | Tool use, self-RAG, query planning |
| 11 | RAG đa phương thức (ảnh + text + bảng biểu) | ★★★★★ | Khó | Multimodal embedding, table/figure retrieval |
| 12 | RAG Evaluation Harness (đánh giá chất lượng RAG) | ★★★★★ | Khó | RAGAS, LLM-as-judge, benchmark |

---

## Nhóm 1 — Cơ bản (nắm pipeline RAG chuẩn)

### 1. Chatbot hỏi đáp tài liệu cá nhân (PDF/notes)

- **Mô tả:** Upload PDF/markdown, đặt câu hỏi và nhận câu trả lời kèm trích dẫn đúng đoạn trong tài liệu.
- **Vì sao RAG nặng:** Toàn bộ giá trị nằm ở retrieval — LLM không biết gì về tài liệu của bạn, mọi câu trả lời đều phải đi qua pipeline ingest → chunk → embed → search.
- **Kỹ thuật học được:** Chunking (fixed-size vs semantic), embedding, cosine similarity, prompt template "trả lời dựa trên context".
- **Stack gợi ý:** Python + Chroma (vector DB nhúng, không cần server) + embedding của Voyage AI hoặc `bge-m3` (tốt cho đa ngôn ngữ Việt/Nhật/Anh) + Claude API.
- **Thời gian ước lượng:** 1–2 tuần.

### 2. Trợ lý wiki/tài liệu nội bộ công ty

- **Mô tả:** Index toàn bộ Confluence/Notion/Google Docs của team, trả lời câu hỏi kiểu "quy trình xin nghỉ phép thế nào", "config service X ở đâu".
- **Vì sao RAG nặng:** Dữ liệu lớn, cập nhật liên tục, nhiều nguồn khác nhau — phải xử lý sync định kỳ, phân quyền truy cập theo user, và search phải đủ tốt để không trả về tài liệu lỗi thời.
- **Kỹ thuật học được:** **Hybrid search** (BM25 + vector), metadata filtering (theo team, ngày cập nhật, độ tin cậy), pipeline ingest tự động.
- **Stack gợi ý:** Qdrant hoặc pgvector + BM25 (qua Elasticsearch hoặc `rank_bm25`) + cron job sync.
- **Thời gian ước lượng:** 2–4 tuần.

---

## Nhóm 2 — Trung cấp (xử lý dữ liệu khó, retrieval thông minh hơn)

### 3. Trợ lý đọc & tra cứu paper nghiên cứu

- **Mô tả:** Index paper từ arXiv/Semantic Scholar theo hướng nghiên cứu (VD: robotics, human augmentation, SRL), hỏi đáp xuyên nhiều paper, so sánh phương pháp giữa các paper, tìm related work.
- **Vì sao RAG nặng:** Paper có cấu trúc đặc thù (abstract, method, equation, reference) — chunking ngây thơ sẽ phá hỏng ngữ cảnh. Câu trả lời phải trích dẫn đúng paper, đúng section, nếu không thì vô dụng cho việc nghiên cứu.
- **Kỹ thuật học được:** Structure-aware chunking, citation tracking, parent-document retrieval (retrieve chunk nhỏ nhưng đưa cả section vào context), query expansion theo thuật ngữ chuyên ngành.
- **Stack gợi ý:** GROBID (parse PDF học thuật) + Qdrant + citations API của Claude (bật `citations: {enabled: true}` trên document block).
- **Thời gian ước lượng:** 3–4 tuần.

### 4. Code assistant trên codebase riêng

- **Mô tả:** Hỏi đáp về codebase của chính mình: "hàm xử lý input buffer nằm ở đâu", "flow save game chạy thế nào", "viết test cho module X theo style hiện tại".
- **Vì sao RAG nặng:** Code không thể chunk theo ký tự — phải chunk theo cấu trúc (function, class) bằng AST. Retrieval phải kết hợp semantic search + exact symbol match, và phải trả về đủ ngữ cảnh (imports, type definitions liên quan).
- **Kỹ thuật học được:** AST-based chunking (tree-sitter), hybrid retrieval cho code, re-ranking, repo-map/context stuffing.
- **Stack gợi ý:** tree-sitter + embedding chuyên code (Voyage `voyage-code-3`) + Qdrant.
- **Thời gian ước lượng:** 3–5 tuần.

### 5. Customer support bot với knowledge base

- **Mô tả:** Bot trả lời khách hàng dựa trên FAQ + docs + lịch sử ticket; escalate cho người thật khi không đủ tự tin.
- **Vì sao RAG nặng:** Câu hỏi của user thật rất "bẩn" (viết tắt, sai chính tả, mô tả mơ hồ) — phải có query rewriting trước khi search. Sai một câu trả lời là mất khách, nên cần confidence threshold + fallback.
- **Kỹ thuật học được:** Query rewriting/decomposition, confidence scoring, feedback loop (câu trả lời bị đánh giá kém → cải thiện index), A/B testing retrieval.
- **Thời gian ước lượng:** 3–5 tuần.

### 6. Trợ lý pháp lý / quy định / hợp đồng

- **Mô tả:** Hỏi đáp trên bộ luật, quy định nội bộ, hoặc hợp đồng — mọi câu trả lời **bắt buộc** kèm điều khoản gốc.
- **Vì sao RAG nặng:** Đây là domain mà hallucination = thảm họa. Toàn bộ hệ thống phải xây quanh nguyên tắc "chỉ nói những gì retrieve được": citation bắt buộc, refuse khi không tìm thấy căn cứ, xử lý các điều khoản tham chiếu chéo lẫn nhau.
- **Kỹ thuật học được:** Grounded generation, citation enforcement, cross-reference resolution, "I don't know" behavior, đánh giá faithfulness.
- **Thời gian ước lượng:** 4–6 tuần.

### 7. Second brain cá nhân (Obsidian/Notion)

- **Mô tả:** Index toàn bộ note cá nhân, hỏi kiểu "tháng trước mình đã kết luận gì về đề tài X", "tổng hợp mọi ghi chú liên quan đến lab Y".
- **Vì sao RAG nặng:** Note thay đổi hằng ngày → cần **incremental indexing** (chỉ re-embed note đã sửa). Câu hỏi thường có yếu tố thời gian → retrieval phải kết hợp semantic + temporal ("gần đây", "hồi tháng 3").
- **Kỹ thuật học được:** Incremental/delta indexing, temporal-aware retrieval, backlink-aware context (đưa cả note được link tới vào context).
- **Stack gợi ý:** Watchdog theo dõi file thay đổi + SQLite-vec hoặc Chroma (chạy local, dữ liệu cá nhân không rời máy).
- **Thời gian ước lượng:** 2–4 tuần.

---

## Nhóm 3 — Nâng cao (RAG là cả một hệ thống, không chỉ một pipeline)

### 8. NPC game có trí nhớ dài hạn (Memory RAG)

- **Mô tả:** NPC nhớ mọi tương tác với người chơi qua nhiều session — "lần trước cậu hứa mang thuốc cho tôi", "cậu từng phản bội làng này". Rất hợp nếu đang làm game Unity/Roblox.
- **Vì sao RAG nặng:** Trí nhớ NPC chính là một hệ RAG hoàn chỉnh: mỗi sự kiện được lưu thành memory record, khi hội thoại thì retrieve theo **3 trục cùng lúc: liên quan (semantic) + gần đây (recency) + quan trọng (importance)** — đúng kiến trúc của paper Generative Agents (Stanford). Còn thêm bài toán reflection: định kỳ nén các memory vụn thành nhận định cấp cao.
- **Kỹ thuật học được:** Memory stream, scoring function đa tiêu chí, reflection/summarization định kỳ, retrieval trong ràng buộc latency của game.
- **Stack gợi ý:** Vector DB nhẹ chạy cạnh game server + Claude Haiku 4.5 cho hội thoại latency thấp, Claude Sonnet 5 cho reflection.
- **Thời gian ước lượng:** 4–8 tuần.

### 9. GraphRAG / Multi-hop QA trên kho tri thức

- **Mô tả:** Trả lời câu hỏi cần **nối nhiều mảnh thông tin**: "Giáo sư nào từng làm ở lab X và hiện nghiên cứu topic Y?" — không chunk đơn lẻ nào chứa đủ câu trả lời.
- **Vì sao RAG nặng:** Vector search thuần thất bại với câu hỏi multi-hop. Phải xây knowledge graph (entity + relation trích từ tài liệu), rồi retrieval đi theo cạnh của graph, kết hợp community summarization cho câu hỏi tổng quan ("chủ đề chính của toàn bộ kho tài liệu là gì").
- **Kỹ thuật học được:** Entity/relation extraction bằng LLM, graph traversal retrieval, community detection + hierarchical summarization (kiến trúc GraphRAG của Microsoft), query routing (câu nào đi graph, câu nào đi vector).
- **Stack gợi ý:** Neo4j hoặc NetworkX + vector DB song song.
- **Thời gian ước lượng:** 6–10 tuần.

### 10. Agentic RAG — agent tự quyết định khi nào retrieve

- **Mô tả:** Thay vì "mọi câu hỏi đều search", agent tự đánh giá: câu này cần retrieve không? Retrieve từ nguồn nào (docs nội bộ / web / database)? Kết quả đủ chưa hay cần search lại với query khác?
- **Vì sao RAG nặng:** Retrieval trở thành **tool trong vòng lặp agent** — agent có thể gọi search nhiều lần, tự viết lại query, tự chấm điểm kết quả (self-RAG), và tổng hợp từ nhiều nguồn. Đây là kiến trúc của các hệ RAG production hiện đại.
- **Kỹ thuật học được:** Tool use với Claude API (tool runner), query planning & decomposition, self-reflection trên kết quả retrieval, multi-source routing, corrective RAG (CRAG).
- **Stack gợi ý:** Claude API tool use (model `claude-opus-5`, adaptive thinking) + 2–3 retrieval tool khác nhau (vector search, BM25, web search).
- **Thời gian ước lượng:** 6–10 tuần.

### 11. RAG đa phương thức (ảnh + text + bảng biểu)

- **Mô tả:** Hỏi đáp trên tài liệu kỹ thuật có hình vẽ, sơ đồ, bảng số liệu — "sơ đồ mạch ở chương 3 nối chân nào với chân nào", "bảng so sánh hiệu năng nói gì".
- **Vì sao RAG nặng:** Phải index và retrieve được cả nội dung không phải text: ảnh cần multimodal embedding hoặc caption hóa bằng vision model trước khi index, bảng cần giữ nguyên cấu trúc, và khi trả lời phải đưa đúng ảnh/bảng vào context của model vision.
- **Kỹ thuật học được:** Multimodal embedding (CLIP-family / voyage-multimodal), image captioning để index, table extraction & serialization, layout-aware parsing.
- **Thời gian ước lượng:** 6–10 tuần.

### 12. RAG Evaluation Harness

- **Mô tả:** Xây hệ thống đánh giá tự động cho chính các RAG pipeline ở trên: đo retrieval precision/recall, faithfulness, answer relevancy — chạy như CI mỗi khi đổi chunking strategy hay embedding model.
- **Vì sao RAG nặng:** Không đo được thì không cải thiện được. Plan này buộc bạn hiểu sâu **mọi khâu** của RAG vì phải đo từng khâu một: chunk tốt chưa, retrieve trúng chưa, câu trả lời có bám context không.
- **Kỹ thuật học được:** RAGAS metrics, LLM-as-judge, xây golden dataset, regression testing cho RAG, phân tích lỗi theo từng tầng (chunking → retrieval → generation).
- **Stack gợi ý:** RAGAS hoặc tự viết judge bằng Claude + structured outputs (`output_config.format`) để chấm điểm có schema.
- **Thời gian ước lượng:** 3–5 tuần (dùng lại được cho mọi project khác).

---

## Lộ trình gợi ý

```
Plan 1 (chatbot PDF)          ← nắm pipeline chuẩn
   ↓
Plan 2 hoặc 7                 ← hybrid search + incremental indexing
   ↓
Plan 3 hoặc 4                 ← chunking khó (paper / code) + re-ranking
   ↓
Plan 12 (evaluation)          ← học đo lường TRƯỚC khi làm hệ phức tạp
   ↓
Plan 8 / 9 / 10               ← chọn theo hứng thú: game / graph / agent
```

Gợi ý riêng: nếu mục tiêu là game dev → ưu tiên **Plan 8 (NPC memory)**; nếu mục tiêu là nghiên cứu/cao học → ưu tiên **Plan 3 (paper assistant)** rồi **Plan 9 (GraphRAG)**.

## Ghi chú về stack chung

- **Embedding:** Anthropic không có embeddings API — dùng Voyage AI (đối tác của Anthropic, có `voyage-3` đa ngôn ngữ và `voyage-code-3` cho code) hoặc open-source `bge-m3` (mạnh cho tiếng Việt/Nhật, chạy local được).
- **Vector DB:** bắt đầu với Chroma (nhúng, zero-config) → chuyển Qdrant hoặc pgvector khi cần production/filtering phức tạp.
- **LLM:** mặc định `claude-opus-5` cho chất lượng; `claude-sonnet-5` cho khối lượng lớn; `claude-haiku-4-5` cho tác vụ latency thấp (VD: hội thoại NPC in-game). Bật prompt caching cho phần context/document lặp lại giữa các request để giảm ~90% chi phí phần cache.
- **Nguyên tắc xuyên suốt:** làm Plan 12 (evaluation) càng sớm càng tốt — mọi quyết định chunking/embedding/re-ranking đều nên có số liệu chứng minh thay vì cảm tính.
