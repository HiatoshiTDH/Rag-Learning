"""Golden set — built from week 2 on; re-run on every chunking/embedding/re-rank change.

Each case: a question + the paper_id/section expected in the top-k.
Start with ~30 questions on the very papers you have read carefully.
"""

GOLDEN_SET = [
    # {"question": "...", "expect_paper": "arXiv:2309.12345", "expect_section_type": "method"},
]


def test_golden_set_recall():
    """TODO(week 2): for each case, run hybrid_search + rerank,
    assert the expected paper/section is in the top-8. Report total recall %."""
    assert True  # placeholder until a real index exists
