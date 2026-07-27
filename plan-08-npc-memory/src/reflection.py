"""Tuần 5-6 — Reflection worker: nén ký ức vụn thành nhận định cấp cao.

Chạy nền, trigger khi tổng importance ký ức mới vượt ngưỡng (~150 theo
paper gốc) hoặc cuối mỗi "ngày" trong game. Dùng Claude Sonnet 5
(claude-sonnet-5) — không cần latency thấp vì không chặn hội thoại.
"""

REFLECTION_THRESHOLD = 150
MODEL = "claude-sonnet-5"


def should_reflect(npc_id: str) -> bool:
    """TODO(tuần 5): tổng importance của ký ức mới kể từ lần reflect trước."""
    raise NotImplementedError


def reflect(npc_id: str) -> None:
    """TODO(tuần 5-6): 3 bước theo README mục 4.4:

    1. Lấy ~100 ký ức gần nhất -> hỏi Sonnet: "3 câu hỏi cấp cao nhất
       có thể trả lời từ những ký ức này?"
    2. Với mỗi câu hỏi: retrieve ký ức liên quan -> sinh nhận định.
    3. Ghi record type=reflection, importance cao, BẮT BUỘC kèm source_ids
       (không có source_ids thì không debug được nhận định bịa).

    Sau khi nén, ký ức vụn cũ có thể hạ cấp/xóa -> stream không phình vô hạn.
    """
    raise NotImplementedError
