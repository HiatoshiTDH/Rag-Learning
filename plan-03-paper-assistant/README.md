# Plan 3 — Trợ lý đọc & tra cứu paper nghiên cứu (chi tiết)

> 🗂 **Bộ tài liệu của plan này:**
> - README.md (file này) — kiến trúc & lý do thiết kế
> - [PLAN.md](PLAN.md) — kế hoạch thực thi full: phase, task, DoD, ước lượng giờ, rủi ro, decision log
> - [SETUP.md](SETUP.md) — mọi thứ cần chuẩn bị: phần mềm, API key, chi phí, checklist Phase 0
> - [TEST_AT_HOME.md](TEST_AT_HOME.md) — **bài test tổng thể khi về máy nhà** (7 bước + troubleshooting)
> - [scripts/smoke_test.sh](scripts/smoke_test.sh) — bản tự động của bài test trên
> - [docker-compose.yml](docker-compose.yml) + [.env.example](.env.example) — chạy GROBID/Qdrant ngay

> Mức độ dùng RAG: ★★★★☆ · Độ khó: Vừa · Thời gian: 3–4 tuần
> Phù hợp nếu bạn đang theo hướng nghiên cứu (robotics, human augmentation, SRL…) và muốn một công cụ dùng thật hằng ngày, không chỉ là bài tập.

## 1. Mục tiêu & User stories

Hệ thống index paper theo hướng nghiên cứu của bạn và trả lời được các dạng câu hỏi:

| # | User story | Đòi hỏi kỹ thuật |
|---|-----------|------------------|
| U1 | "Paper X dùng phương pháp gì để giải quyết vấn đề Y?" | Retrieval trong 1 paper, đúng section Method |
| U2 | "So sánh cách paper A và paper B đo lường Z" | Retrieval xuyên nhiều paper + tổng hợp |
| U3 | "Những paper nào trong kho của tôi dùng dataset D?" | Metadata + full-text search kết hợp |
| U4 | "Tóm tắt các hướng tiếp cận chính cho bài toán P trong kho paper" | Map-reduce summarization trên nhiều paper |
| U5 | "Câu trả lời này lấy từ đâu?" | Citation về đúng paper, đúng section/trang |

**Nguyên tắc vàng:** câu trả lời không có citation = câu trả lời vô dụng cho nghiên cứu. Mọi thiết kế đều xoay quanh việc giữ được nguồn gốc thông tin.

## 2. Kiến trúc tổng thể

```
┌────────────── INGEST ──────────────┐   ┌───────── QUERY ─────────┐
│ arXiv API / Semantic Scholar API   │   │ Câu hỏi người dùng       │
│        ↓                           │   │        ↓                 │
│ PDF → GROBID → TEI XML             │   │ Query expansion          │
│        ↓                           │   │ (thuật ngữ chuyên ngành) │
│ Structure-aware chunking           │   │        ↓                 │
│ (theo section, giữ metadata)       │   │ Hybrid search            │
│        ↓                           │   │ (vector + BM25 + filter) │
│ Embedding → Qdrant                 │   │        ↓                 │
│ Metadata → SQLite                  │   │ Re-rank → Parent-doc     │
└────────────────────────────────────┘   │        ↓                 │
                                         │ Claude + citations       │
                                         └──────────────────────────┘
```

## 3. Ingest pipeline — nơi 60% công sức nằm ở đây

### 3.1 Nguồn dữ liệu
- **arXiv API**: tải PDF + metadata (title, authors, abstract, categories) theo từ khóa/category (VD `cs.RO`, `cs.AI`).
- **Semantic Scholar API**: bổ sung citation count, references, paperId — dùng cho tính năng "paper nào cite paper nào" về sau.
- Kho local: thư mục PDF bạn đã tải sẵn.

### 3.2 Parse PDF học thuật — đừng dùng PDF-to-text thường
PDF paper 2 cột, có công thức, bảng, header/footer — extract text ngây thơ sẽ trộn 2 cột vào nhau và phá hỏng mọi thứ phía sau. Dùng **GROBID** (chạy bằng Docker): nó trả về TEI XML có cấu trúc đầy đủ — title, abstract, từng section có tên, từng đoạn văn, danh mục references đã parse sẵn.

```
docker run -p 8070:8070 lfoppiano/grobid:0.8.0
```

### 3.3 Structure-aware chunking
Đây là kỹ thuật trung tâm của plan này. Quy tắc:

- **Đơn vị chunk = đoạn văn trong một section**, không cắt ngang đoạn. Đoạn quá dài (>800 token) mới cắt tiếp theo câu.
- Mỗi chunk mang metadata đầy đủ:

```json
{
  "chunk_id": "2309.12345#method#3",
  "paper_id": "arXiv:2309.12345",
  "title": "...",
  "authors": ["..."],
  "year": 2023,
  "section": "3. Method",
  "section_type": "method",
  "text": "...",
  "parent_section_text_ref": "2309.12345#method"
}
```

- **`section_type`** chuẩn hóa (abstract / intro / related_work / method / experiment / result / conclusion) — cho phép filter kiểu "chỉ tìm trong Method".
- **Abstract luôn được index như một chunk riêng** với trọng số ưu tiên — nó là bản tóm tắt tốt nhất của paper.
- Công thức toán: giữ nguyên dạng LaTeX trong text chunk (GROBID giữ được), không cố "dịch" ra lời.

### 3.4 Embedding & index
- Embedding: `voyage-3` (đa ngôn ngữ, hiểu văn bản học thuật tốt) hoặc `bge-m3` nếu muốn chạy local miễn phí.
- Vector DB: **Qdrant** — cần payload filtering (theo `paper_id`, `section_type`, `year`) mà Chroma làm yếu hơn.
- Metadata + full text các section: SQLite — dùng cho parent-document retrieval và BM25.

## 4. Query pipeline

### 4.1 Query expansion theo thuật ngữ chuyên ngành
Người hỏi dùng từ khác paper: hỏi "exoskeleton điều khiển bằng EMG" nhưng paper viết "sEMG-driven assistive device". Trước khi search, cho Claude sinh 2–3 cách diễn đạt khác của câu hỏi (kể cả bản dịch tiếng Anh nếu hỏi bằng tiếng Việt — paper hầu hết là tiếng Anh), rồi search với tất cả biến thể và gộp kết quả.

### 4.2 Hybrid search + filter
- Vector search (top 20) + BM25 (top 20) → gộp bằng Reciprocal Rank Fusion.
- Áp filter nếu câu hỏi nêu rõ: tên paper cụ thể → filter `paper_id`; "phương pháp" → ưu tiên `section_type: method`.

### 4.3 Re-ranking
Đưa ~40 ứng viên qua reranker (`voyage-rerank-2` hoặc `bge-reranker-v2-m3` local) → lấy top 6–8. Bước này cải thiện chất lượng rõ rệt nhất so với công sức bỏ ra.

### 4.4 Parent-document retrieval
Chunk nhỏ giúp search chính xác, nhưng context cho LLM cần rộng hơn: sau khi chọn được top chunks, **thay mỗi chunk bằng toàn bộ section chứa nó** (đã lưu trong SQLite). Dedupe nếu nhiều chunk cùng section.

### 4.5 Generation với citations
Dùng citations API của Claude — đưa mỗi section vào như một `document` block với `citations: {enabled: true}` và `title` là "Tên paper — Tên section". Response trả về các đoạn text kèm mảng `citations` trỏ đúng document nào, vị trí nào → render thành footnote/link được. Không cần tự prompt "hãy trích dẫn" rồi parse tay — API làm việc đó có cấu trúc.

Với câu hỏi so sánh nhiều paper (U2, U4): chạy **map-reduce** — retrieve riêng cho từng paper, tóm tắt góc nhìn từng paper (map), rồi một call cuối tổng hợp so sánh (reduce).

## 5. Milestones

| Tuần | Việc | Definition of done |
|------|------|--------------------|
| 1 | GROBID pipeline + chunking + index 10 paper | Xem được chunks đúng section trong Qdrant |
| 2 | Query pipeline cơ bản (vector search → Claude + citations) | U1 chạy được, câu trả lời có citation đúng |
| 2–3 | Hybrid + re-rank + parent-document | Đo được cải thiện trên bộ 20 câu hỏi tự tạo |
| 3 | Query expansion + multi-paper (map-reduce) | U2, U4 chạy được |
| 4 | CLI/UI đơn giản + ingest tự động từ arXiv theo keyword | Dùng được hằng ngày |

## 6. Những cái bẫy đã biết

- **Đừng chunk theo ký tự cố định** — mất ranh giới section là mất luôn khả năng citation đúng chỗ.
- **References section**: đừng index như văn bản thường (nó sẽ nhiễu retrieval khủng khiếp vì chứa mọi từ khóa). Tách riêng, chỉ dùng cho citation graph.
- **Bảng số liệu**: GROBID parse bảng khá yếu. Chấp nhận bỏ qua ở v1; nâng cấp sau bằng vision model (giao với Plan 11).
- **Hỏi tiếng Việt trên paper tiếng Anh**: bắt buộc có bước dịch/expansion query, nếu không recall rất thấp dù embedding "đa ngôn ngữ".
- **Đánh giá bằng cảm tính**: tạo golden set ~30 câu hỏi có đáp án + nguồn đúng ngay từ tuần 2. Mỗi lần đổi chunking/embedding, chạy lại và so số (nối sang Plan 12).

## 7. Hướng mở rộng

- **Citation graph** (Semantic Scholar references) → trả lời "paper nào xây trên paper nào" → bước đệm tự nhiên sang Plan 9 (GraphRAG).
- **Radar paper mới**: cron hằng tuần quét arXiv theo keyword, tự ingest và tóm tắt cái mới so với kho hiện có.
- **Hỗ trợ viết related work**: retrieve các paper liên quan đến đề tài + sinh draft có citation — hữu ích trực tiếp cho 研究計画書/proposal.
