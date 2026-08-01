"""Test offline cho eval: hit logic, faithfulness judge (LLM-as-judge inject được)."""

from src.eval import hit, judge_faithfulness, run_faithfulness_eval

SECTIONS = [
    {"paper_title": "Paper A", "section": "3. Method", "text": "X works by doing Y." * 20,
     "paper_id": "a", "section_type": "method"},
]


# ------------------------------------------------------------------------ hit

def test_hit_matches_paper_and_section():
    case = {"question": "q", "expect_paper": "a", "expect_section_type": "method"}
    assert hit(case, [{"paper_id": "a", "section_type": "method"}])
    assert not hit(case, [{"paper_id": "a", "section_type": "intro"}])
    assert not hit(case, [{"paper_id": "b", "section_type": "method"}])


def test_hit_without_section_type():
    case = {"question": "q", "expect_paper": "a"}
    assert hit(case, [{"paper_id": "a", "section_type": "intro"}])


# ------------------------------------------------------------ faithfulness judge

def test_judge_parses_pass():
    v = judge_faithfulness("q?", "trả lời", SECTIONS,
                           llm=lambda p: "PHÁN QUYẾT: PASS\nLÝ DO: mọi ý đều có nguồn")
    assert v["faithful"] is True and "nguồn" in v["reason"]


def test_judge_parses_fail():
    v = judge_faithfulness("q?", "trả lời bịa", SECTIONS,
                           llm=lambda p: "PHÁN QUYẾT: FAIL\nLÝ DO: số liệu 95% không có trong nguồn")
    assert v["faithful"] is False and "95%" in v["reason"]


def test_judge_garbage_output_fails_safe():
    """Judge trả sai định dạng, không rõ PASS -> FAIL an toàn (không cho qua bừa)."""
    v = judge_faithfulness("q?", "x", SECTIONS, llm=lambda p: "tôi không chắc lắm...")
    assert v["faithful"] is False


def test_judge_prompt_contains_all_pieces():
    seen = {}
    judge_faithfulness("câu hỏi kiểm tra?", "câu trả lời kiểm tra", SECTIONS,
                       llm=lambda p: seen.update(p=p) or "PHÁN QUYẾT: PASS\nLÝ DO: ok")
    assert "câu hỏi kiểm tra?" in seen["p"]
    assert "câu trả lời kiểm tra" in seen["p"]
    assert "Paper A — 3. Method" in seen["p"]


# ------------------------------------------------------- run_faithfulness_eval

def test_run_faithfulness_eval_with_fakes():
    cases = [{"question": f"q{i}?", "expect_paper": "a"} for i in range(3)]

    def fake_answer(q):
        return {"text": f"trả lời {q}", "sections": SECTIONS}

    # q1 fail, còn lại pass
    def fake_judge(prompt):
        return ("PHÁN QUYẾT: FAIL\nLÝ DO: bịa" if "q1?" in prompt
                else "PHÁN QUYẾT: PASS\nLÝ DO: ok")

    result = run_faithfulness_eval(n=3, cases=cases, answer_fn=fake_answer,
                                   judge_llm=fake_judge)
    assert result["stage"] == "faithfulness"
    assert result["n"] == 3 and abs(result["recall"] - 2 / 3) < 1e-9
    assert len(result["failures"]) == 1 and "q1?" in result["failures"][0]


def test_run_faithfulness_eval_respects_n():
    cases = [{"question": f"q{i}?", "expect_paper": "a"} for i in range(10)]
    counted = []

    def fake_answer(q):
        counted.append(q)
        return {"text": "x", "sections": SECTIONS}

    run_faithfulness_eval(n=4, cases=cases, answer_fn=fake_answer,
                          judge_llm=lambda p: "PHÁN QUYẾT: PASS\nLÝ DO: ok")
    assert len(counted) == 4    # chỉ chạy n case đầu — kiểm soát chi phí
