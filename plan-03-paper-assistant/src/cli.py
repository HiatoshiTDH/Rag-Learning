"""P5 (5.1) — CLI: python -m src.cli <lệnh>

  ask "câu hỏi" [--paper ID] [--section-type method] [--no-expand] [--lang en|vi|auto]
  compare "câu hỏi" ID1 ID2 [...] [--lang en|vi|auto]
  ingest                    # đọc data/seed_papers.txt, chạy trọn pipeline
  watch                     # quét arXiv theo data/watch_keywords.txt, ingest paper mới
  list                      # paper đã index
  eval [--stage v1|hybrid|rerank|full] [--note "..."]

--lang tách biệt NGÔN NGỮ TRẢ LỜI khỏi ngôn ngữ câu hỏi — VD hỏi tiếng Việt
nhưng muốn nhận lại tiếng Anh (giữ thuật ngữ gốc): --lang en. Mặc định "auto"
(trả lời theo đúng ngôn ngữ câu hỏi), hoặc đặt cố định qua .env ANSWER_LANGUAGE.
"""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="paper-assistant", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ask = sub.add_parser("ask", help="Hỏi trên toàn kho (router tự nhận diện paper trong câu)")
    p_ask.add_argument("question")
    p_ask.add_argument("--paper", help="Giới hạn trong 1 paper (arXiv id)")
    p_ask.add_argument("--section-type", choices=["abstract", "intro", "related_work",
                                                  "method", "experiment", "result", "conclusion"])
    p_ask.add_argument("--no-expand", action="store_true", help="Tắt query expansion (nhanh/rẻ hơn)")
    p_ask.add_argument("--lang", choices=["auto", "en", "vi"], default=None,
                       help="Ngôn ngữ TRẢ LỜI, tách biệt với ngôn ngữ câu hỏi (mặc định: auto)")

    p_cmp = sub.add_parser("compare", help="So sánh 2+ paper theo một câu hỏi")
    p_cmp.add_argument("question")
    p_cmp.add_argument("paper_ids", nargs="+")
    p_cmp.add_argument("--lang", choices=["auto", "en", "vi"], default=None,
                       help="Ngôn ngữ TRẢ LỜI, tách biệt với ngôn ngữ câu hỏi (mặc định: auto)")

    sub.add_parser("ingest", help="Ingest toàn bộ data/seed_papers.txt")
    sub.add_parser("watch", help="Quét arXiv theo keyword, ingest paper mới")
    sub.add_parser("list", help="Danh sách paper đã index")

    p_eval = sub.add_parser("eval", help="Đo recall trên golden set")
    p_eval.add_argument("--stage", default="full", choices=["v1", "hybrid", "rerank", "full"])
    p_eval.add_argument("--note", default="", help="Ghi chú cho dòng EXPERIMENTS.md")
    p_eval.add_argument("--no-log", action="store_true", help="Chỉ in, không ghi EXPERIMENTS.md")

    args = parser.parse_args()

    if args.cmd == "ingest":
        from src.ingest_all import main as ingest_main
        ingest_main()

    elif args.cmd == "watch":
        from src.watch_arxiv import main as watch_main
        watch_main()

    elif args.cmd == "list":
        from src.index import list_papers
        papers = list_papers()
        if not papers:
            print("Chưa có paper nào — chạy `python -m src.cli ingest` trước.")
        for p in papers:
            print(f'{p["paper_id"]:>16}  ({p["year"]})  {p["title"]}')

    elif args.cmd == "ask":
        from src.answer import answer, compare_papers, format_answer, route
        from src.index import list_papers

        filters = {}
        if args.paper:
            filters["paper_id"] = args.paper
        if args.section_type:
            filters["section_type"] = args.section_type

        if not filters:  # router chỉ can thiệp khi user không tự chỉ định
            decision = route(args.question, [p["paper_id"] for p in list_papers()])
            if decision["kind"] == "compare":
                print(compare_papers(args.question, decision["paper_ids"], language=args.lang)["text"])
                return
            if decision["kind"] == "single":
                filters["paper_id"] = decision["paper_ids"][0]

        result = answer(args.question, filters=filters or None, expand=not args.no_expand,
                        language=args.lang)
        print(format_answer(result))

    elif args.cmd == "compare":
        from src.answer import compare_papers
        print(compare_papers(args.question, args.paper_ids, language=args.lang)["text"])

    elif args.cmd == "eval":
        from src.eval import log_experiment, print_report, run_eval
        result = run_eval(stage=args.stage)
        print_report(result)
        if not args.no_log:
            log_experiment(result, note=args.note)
            print(f"\nĐã ghi vào EXPERIMENTS.md")


if __name__ == "__main__":
    main()
