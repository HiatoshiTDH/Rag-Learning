"""Golden set — tạo từ tuần 2, chạy lại mỗi lần đổi chunking/embedding/re-rank.

Mỗi case: câu hỏi + paper_id/section kỳ vọng xuất hiện trong top-k.
Bắt đầu ~30 câu trên chính các paper bạn đã đọc kỹ.
"""

GOLDEN_SET = [
    # {"question": "...", "expect_paper": "arXiv:2309.12345", "expect_section_type": "method"},
]


def test_golden_set_recall():
    """TODO(tuần 2): với mỗi case, chạy hybrid_search + rerank,
    assert paper/section kỳ vọng nằm trong top-8. Báo % recall tổng."""
    assert True  # placeholder cho tới khi có index thật
